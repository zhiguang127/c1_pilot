"""Snapshot original primary sources; freeze selection before Silver predictions."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import re

from ..src.common import ROOT, digest, now, read, rows, sha, verify, write
from ..src.data import audit, candidates
from ..src.continuation import SELECTED
from .api import SILVER


def knowledge_union():
    _, a0, _ = candidates()
    verify(ROOT / "data/releases/a1-v1")
    a1 = {k['id']: k for k in rows(ROOT / 'data/releases/a1-v1/knowledge.jsonl')}
    for kid, k in a0.items():
        assert a1[kid]['applicability'] == k['applicability']
        assert a1[kid]['content'] == k['content']
    return {**a1, **a0}


def extract(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('main') or soup.select_one('article') or soup.select_one('[role=main]') or soup.body
    if body is None:
        return []
    for node in body.select('script,style,nav,footer,header,form,aside'):
        node.decompose()
    parts, seen, heading = [], set(), ''
    for node in body.select('h1,h2,h3,h4,p,li,tr'):
        if node.find_parent(['li','tr']) is not None:
            continue
        text = ' '.join(node.get_text(' ', strip=True).split())
        if node.name.startswith('h'):
            heading = text
        if len(text) < 12 or text in seen:
            continue
        seen.add(text)
        parts.append({'paragraph_id': f'P{len(parts)+1:04d}', 'heading': heading, 'text': text})
    return parts


def fetch_one(url):
    import requests
    target = SILVER / 'sources' / (digest(url)[:16] + '.json')
    if target.exists():
        return read(target)
    item = {'requested_url': url, 'accessed_at': now(), 'method': 'HTTPS GET; verified TLS; no credentials',
            'status': 'UNAVAILABLE', 'paragraphs': []}
    try:
        response = requests.get(url, timeout=(15,45), headers={'User-Agent':'ExperimentA-SourceAudit/1.0 (+research)'})
        item.update(http_status=response.status_code, final_url=response.url)
        if response.status_code == 200:
            html = response.text
            paragraphs = extract(html)
            text = ' '.join(p['text'] for p in paragraphs)
            blocked = any(s in text.lower() for s in ['access denied','verify you are human','enable javascript and cookies'])
            if len(text) > 400 and not blocked:
                item.update(status='FETCHED_PRIMARY_TEXT', paragraphs=paragraphs,
                            html_sha256=__import__('hashlib').sha256(response.content).hexdigest(), text_sha256=digest(paragraphs))
                (target.parent).mkdir(exist_ok=True,parents=True)
                (target.with_suffix('.html')).write_bytes(response.content)
    except Exception as exc:
        item['error_type'] = type(exc).__name__
    write(target, item)
    return item


def prepare():
    path = SILVER / 'plan.json'
    if path.exists():
        return read(path)
    a = audit()
    cases, _, _ = candidates()
    knowledge = knowledge_union()
    # Only prior LLM debugging exposure excludes participants. E1 retrieval ran
    # all windows; it is explicitly not an unexposed population for retrieval.
    case_map = {c['case_id']:c for c in cases}
    exposures = []
    for f in (ROOT/'local/runs').glob('*/predictions.jsonl'):
        ps = rows(f)
        for p in ps:
            exposures.append(p['case_id'])
    used = {case_map[c]['subject_id'] for c in exposures if c in case_map}
    selected_case = sorted(cases,key=lambda c:c['case_id'])[0]
    held = defaultdict(list)
    for c in cases:
        if c['subject_id'] not in used:
            held[c['subject_id']].append(c)
    selected = [sorted(v,key=lambda c:(c['block'], c['case_id']))[0]['case_id'] for _,v in sorted(held.items())]
    urls = sorted({k['source_url'] for k in knowledge.values()})
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(fetch_one,urls))
    p = {'version':'qwen-max-silver-v1','created_at':now(),'label_provenance':'QWEN_MAX_SILVER',
         'input_integrity':a,'a1_release_id':verify(ROOT/'data/releases/a1-v1')['release_id'],
         'source_urls':urls,'source_snapshots':{s['requested_url']:digest(s['requested_url'])[:16]+'.json' for s in sources},
         'knowledge_ids':sorted(knowledge),'smoke_case_ids':[selected_case['case_id']],
         'prior_llm_debug_participants':sorted(used),'heldout_case_ids':selected,
         'selection_rule':'Exclude participants present in any prior LLM predictions.jsonl, choose earliest block then case_id; no label/quality selection',
         'retrieval_exposure_note':'All 48 windows were used for E1; held-out here means prior applicability-LLM engineering exposure only',
         'order_seeds':{'A':73181,'B':99107,'evidence':51217},
         'baseline_runs':SELECTED,'batch_executed':False,'human_gold':False}
    p['plan_id']=digest(p)
    write(path,p)
    return p


def source_packet(knowledge):
    source=read(SILVER/'sources'/(digest(knowledge['source_url'])[:16]+'.json'))
    if source['status']=='UNAVAILABLE':
        for f in (SILVER/'sources').glob('web_*.json'):
            recovered=read(f)
            if recovered['requested_url']==knowledge['source_url']:
                source=recovered
                source['text_sha256']=digest(source['paragraphs'])
                break
    # Deterministic extraction window, not a finding that omitted text is absent.
    terms=set(re.findall(r'[a-z]{4,}', ' '.join([knowledge['title'], knowledge['content'],
                    *knowledge.get('support_anchors',[]), knowledge.get('source_locator','')]).lower()))
    scored=sorted(enumerate(source['paragraphs']),key=lambda pair:(-len(terms & set(re.findall(r'[a-z]{4,}',pair[1]['text'].lower()))),pair[0]))
    chosen, size=[],0
    for index,part in scored:
        if size+len(part['text'].encode())>10500:
            continue
        chosen.append((index,part));size+=len(part['text'].encode())
    return {k:source.get(k) for k in ['requested_url','final_url','accessed_at','status','text_sha256']} | {
        'paragraphs':[p for _,p in sorted(chosen)], 'extraction_scope':'Deterministic lexical evidence packet; not guaranteed exhaustive source coverage',
        'paragraph_count_whole_snapshot':len(source['paragraphs'])}
