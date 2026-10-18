"""Source audit precedes isolated A/B annotation; all row-level artifacts private."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import random

from ..src.common import LABELS, ROOT, digest, now, read, rows, sha, write
from ..src.data import candidates, evidence_value, representation
from ..src.trialgpt import condition_spec
from .api import SILVER, IncompleteOutput, SilverClient, estimate, packed, request_options
from . import prompts
from . import schemas
from .sources import knowledge_union, prepare, source_packet


def messages(prompt,payload):
    return [{'role':'system','content':prompt},{'role':'user','content':packed(payload)}]


def array_value(value):
    """Decode a JSON array serialized inside a JSON string; no inference/repair."""
    if isinstance(value,str) and value.strip().startswith('['):
        try:
            decoded=__import__('json').loads(value)
        except (ValueError,TypeError):
            return value
        if isinstance(decoded,list):
            return decoded
    return value


def canonical_source(record):
    r=deepcopy(record)
    changes=[]
    schema_errors=[]
    defaults={'knowledge_id':r['knowledge_id'],'core_claim_support':'UNVERIFIABLE','source_scope_disputed':True,
              'proposed_core_scope':'No scope proposal returned; original source still requires review.'}
    for name,default in defaults.items():
        if name not in r['audit']:
            schema_errors.append('missing_source_field:'+name)
            r['audit'][name]=default
    r['audit']['conditions']=array_value(r['audit'].get('conditions')) or []
    if not isinstance(r['audit']['conditions'],list):
        r['audit']['conditions']=[]
        changes.append('malformed_condition_array_retained_in_raw')
    if any(not isinstance(c,dict) for c in r['audit']['conditions']):
        r['audit']['conditions']=[c for c in r['audit']['conditions'] if isinstance(c,dict)]
        changes.append('non_object_condition_entries_retained_in_raw')
    for c in r['audit']['conditions']:
        old=c.get('evidence')
        value=array_value(old)
        if value is None or value=='':
            value=[]
        if not isinstance(value,list):
            value=[]
            changes.append(c['condition_id']+':unparseable_evidence_retained_in_raw_not_verified')
        if type(old) is not type(value):
            changes.append(c['condition_id']+':decode_json_array_or_empty')
        c['evidence']=value
    r['structural_normalizations']=changes
    paragraphs={p['paragraph_id']:p['text'] for p in r['source_evidence']['paragraphs']}
    r['quote_locator_diagnostics']=[]
    for c in r['audit']['conditions']:
        for e in c.get('evidence') or []:
            if isinstance(e,dict) and e.get('quote') and e['quote'] not in paragraphs.get(e.get('paragraph_id'),''):
                alternatives=[pid for pid,text in paragraphs.items() if e['quote'] in text]
                r['quote_locator_diagnostics'].append({'condition_id':c['condition_id'],
                     'original_paragraph_id':e.get('paragraph_id'),'exact_quote_other_paragraph_ids':alternatives,
                     'kind':'WRONG_PARAGRAPH_ID' if alternatives else 'QUOTE_UNVERIFIED_IN_PACKET'})
    r['validation_errors']=schema_errors+validate_source(r['audit'],r['original_knowledge'],r['source_evidence'])
    actual={c.get('condition_id') for c in r['audit']['conditions']}
    r['model_omitted_conditions']=[]
    for c in condition_spec(r['original_knowledge']):
        if c['id'] not in actual:
            r['model_omitted_conditions'].append(c['id'])
            r['audit']['conditions'].append({'condition_id':c['id'],'original_text':c['text'],
                'role':'disputed','support':'UNVERIFIABLE','evidence':[],
                'rationale':'The source-audit response omitted this original condition. No model judgment or verified source evidence is available.',
                'proposed_revision':'Independent review required; do not impose this draft as a confirmed prerequisite.',
                'judgment_origin':'SOFTWARE_UNRESOLVED_OMISSION_NOT_A_MODEL_JUDGMENT'})
    r['status']='SOURCE_AUDIT_MACHINE_REVIEW_REQUIRED' if r['validation_errors'] else 'SOURCE_AUDIT_MACHINE_COMPLETE'
    return r


def checkpoint(relative, producer):
    path=SILVER/relative
    if path.exists():
        return read(path)
    value=producer()
    write(path,value)
    return value


def case_payload(case):
    columns=['day','weekday','phase',*case['days'][0]['metrics']]
    flag_dictionary=list(dict.fromkeys(flag for d in case['days'] for flag in d['quality_flags']))
    metric_dictionary=columns[3:]
    table=[]
    for d in case['days']:
        table.append([d['day'],d['weekday'],d['phase'],*[d['metrics'][m] for m in columns[3:]]])
    summary=representation(case,'statistics')['statistics']
    stats={}
    for phase,entry in summary.items():
        stats[phase]={'day_range':entry['day_range'],'metrics':{}}
        for metric,values in entry['metrics'].items():
            stats[phase]['metrics'][metric]={k:round(v,3) if isinstance(v,float) else v for k,v in values.items() if k not in ('observations','value_counts','interpretation')}
    return {'case_id':case['case_id'],'context':case['context'],'quality_notes':case['quality_notes'],
            'baseline_days':[1,28],'current_days':[29,42], 'daily_columns':columns,'daily_rows':table,
            'quality_flag_dictionary':flag_dictionary,'missing_metric_dictionary':metric_dictionary,
            'daily_quality_columns':['day','quality_flag_ids','missing_metric_ids'],
            'daily_quality_rows':[[d['day'],[flag_dictionary.index(f) for f in d['quality_flags']],
                [metric_dictionary.index(m) for m in d['missing_metrics']]] for d in case['days'] if d['quality_flags'] or d['missing_metrics']],
            'stats':stats,'statistics_policy':'Derived floats rounded to 3 decimals; raw daily values unchanged. Population SD; OLS daily slope; RHR 0/null excluded; circular clocks, timezone unknown; original units'}


def resolve(case,ref):
    if ref.startswith('stats.'):
        parts=ref.split('.')
        if len(parts)!=4 or parts[1] not in ('baseline','current'):
            raise ValueError('Unknown statistic reference')
        p=case_payload(case)['stats'][parts[1]]['metrics']
        if parts[2] not in p or parts[3] not in p[parts[2]]:
            raise ValueError('Unknown statistic reference')
        return p[parts[2]][parts[3]],parts[1]
    value=evidence_value(case,ref)
    phase='context' if ref.startswith('context.') else 'baseline' if int(ref.split('.')[0][1:])<=28 else 'current'
    return value,phase


def validate_source(result,k,packet):
    expected={c['id']:c['text'] for c in condition_spec(k)}
    checks=array_value(result.get('conditions',[])) or []
    errors=[]
    if not isinstance(checks,list):
        checks=[];errors.append('malformed_source_condition_array')
    if any(not isinstance(c,dict) for c in checks):
        checks=[c for c in checks if isinstance(c,dict)];errors.append('malformed_source_condition_items')
    if len(checks)!=len(expected) or {c['condition_id'] for c in checks}!=set(expected):
        errors.append('source_condition_set_mismatch')
    paragraphs={p['paragraph_id']:p['text'] for p in packet['paragraphs']}
    for c in checks:
        if c.get('original_text')!=expected.get(c['condition_id']):
            errors.append('condition_text_changed:'+c['condition_id'])
        if c.get('role') not in ('necessary_prerequisite','optional_background','claim_scope_restriction','disputed'):
            errors.append('invalid_role:'+c['condition_id'])
        if c.get('support') not in ('EXPLICIT_SUPPORT','GENERAL_ADVICE_ONLY','OVERINTERPRETED','UNVERIFIABLE'):
            errors.append('invalid_support:'+c['condition_id'])
        if c.get('support')!='UNVERIFIABLE' and not c.get('evidence'):
            errors.append('no_source_evidence:'+c['condition_id'])
        evidence=c.get('evidence') or []
        if not isinstance(evidence,list):
            errors.append('invalid_evidence_shape:'+c['condition_id'])
            continue
        for e in evidence:
            if not isinstance(e,dict):
                errors.append('invalid_evidence_shape:'+c['condition_id'])
                continue
            if not e.get('quote') or e.get('paragraph_id') not in paragraphs or e['quote'] not in paragraphs.get(e.get('paragraph_id'),''):
                errors.append('quote_not_in_snapshot:'+c['condition_id'])
    return errors


def source_audit():
    plan=read(SILVER/'plan.json'); client=SilverClient()
    def perform(pair):
        kid,k=pair
        def run(k=k,kid=kid):
            packet=source_packet(k)
            payload={'knowledge':k,'original_conditions':condition_spec(k),'source_evidence':packet}
            expanded=False
            try:
                result,meta=client.call(messages(prompts.SOURCE,payload),tag='source:'+kid,max_tokens=4096)
            except IncompleteOutput:
                # Explicit source-only retry after a recorded length stop; no
                # partial source result or personal label is silently repaired.
                result,meta=client.call(messages(prompts.SOURCE,payload),tag='source-expanded:'+kid,max_tokens=8192)
                expanded=True
            errors=validate_source(result,k,packet)
            return {'label_provenance':'QWEN_MAX_SILVER','knowledge_id':kid,'original_knowledge':k,
                    'source_evidence':packet,'audit':result,'validation_errors':errors,
                    'status':'SOURCE_AUDIT_MACHINE_REVIEW_REQUIRED' if errors else 'SOURCE_AUDIT_MACHINE_COMPLETE',
                    'metadata':meta,'expanded_after_truncation':expanded,'prompt_version':prompts.VERSION,'plan_id':plan['plan_id'],'at':now()}
        raw_record=checkpoint('source_audit/'+kid+'.json',run)
        canonical=canonical_source(raw_record)
        write(SILVER/'source_audit_canonical'/(kid+'.json'),canonical,overwrite=True)
        print('source_audit_checkpoint '+kid+' validation_errors='+str(len(canonical['validation_errors'])),flush=True)
        return canonical
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(perform,sorted(knowledge_union().items())))
    return {'items':len(results),'validation_errors':sum(bool(r['validation_errors']) for r in results)}


def source_label_view(kid):
    r=canonical_source(read(SILVER/'source_audit'/(kid+'.json')))
    a={k:deepcopy(r['audit'][k]) for k in ['knowledge_id','core_claim_support','source_scope_disputed','proposed_core_scope']}
    a['conditions']=[{key:c.get(key) for key in ['condition_id','original_text','role','support','evidence']}
                     for c in r['audit']['conditions']]
    k=r['original_knowledge']
    # Original condition text/IDs appear once in source_audit.conditions.
    compact_knowledge={name:k[name] for name in ['id','title','content','source','source_url']}
    return {'knowledge':compact_knowledge,'source_audit':a,
            'source_accessed_at':r['source_evidence']['accessed_at'],
            'audit_validation_errors':r['validation_errors'],
            'audit_verification_note':'Any flagged quote or unsupported condition remains unverified; do not impose it as a confirmed prerequisite',
            'source_audit_sha256':sha(SILVER/'source_audit'/(kid+'.json')),
            'audit_status':'QWEN_MAX_SILVER_MACHINE_SCOPE_PROPOSALS_NOT_HUMAN_CONFIRMED'}


def label_payload(case,round_name):
    plan=read(SILVER/'plan.json')
    ids=list(case['candidate_ids'])
    random.Random(plan['order_seeds']['A']).shuffle(ids)
    if round_name=='B':
        ids.reverse()  # Guaranteed altered order, even if seeded shuffles coincide.
    return {'independent_round':round_name,'personal_records':case_payload(case),
            'required_output_knowledge_ids':ids,'required_output_item_count':len(ids),
            'candidates':[source_label_view(k) for k in ids]}


def validate_labels(result,case,knowledge,source_safety=None,source_review=None):
    items=array_value(result.get('items',[]))
    if not isinstance(items,list) or any(not isinstance(p,dict) for p in items):
        raise ValueError('Malformed Silver item array retained in private response cache')
    if len(items)!=len(case['candidate_ids']) or {p['knowledge_id'] for p in items}!=set(case['candidate_ids']):
        raise ValueError('Silver candidate set mismatch')
    out=[]
    for p in items:
        for field in ('condition_judgments','supporting_observations','violated_conditions','missing_information'):
            p[field]=array_value(p.get(field))
        for c in p.get('condition_judgments') or []:
            c['observations']=array_value(c.get('observations')) or []
        errors=[]
        if p.get('case_id')!=case['case_id'] or p.get('label_provenance')!='QWEN_MAX_SILVER' or p.get('annotation_model')!='qwen-max':
            errors.append('identity_or_provenance')
        if p.get('applicability') not in LABELS:
            errors.append('invalid_label')
        if not isinstance(p.get('review_required'),bool) or not isinstance(p.get('source_scope_disputed'),bool):
            errors.append('invalid_review_flags')
        if p.get('source_scope_disputed') and (p.get('applicability')!='insufficient_information' or not p.get('review_required')):
            errors.append('disputed_core_forced_label')
        if source_safety and source_safety.get(p['knowledge_id']) and (not p.get('source_scope_disputed') or p.get('applicability')!='insufficient_information'):
            errors.append('source_dispute_not_propagated')
        expected={c['id'] for c in condition_spec(knowledge[p['knowledge_id']])}
        cs=p.get('condition_judgments') or []
        missingness_refs={o.get('reference') for o in p.get('supporting_observations') or [] if isinstance(o,dict) and o.get('purpose')=='missingness'}
        if len(cs)!=len(expected) or {c.get('condition_id') for c in cs}!=expected:
            errors.append('incomplete_condition_set')
        for c in cs:
            if c.get('status') not in ('satisfied','violated','unknown','not_applicable_to_condition'):
                errors.append('invalid_condition_status')
            for ref in c.get('observations',[]):
                try:
                    v,_=resolve(case,ref)
                    if (v is None or (ref.endswith('resting_heart_rate_bpm') and v==0)) and c.get('status')=='satisfied' and ref not in missingness_refs:
                        errors.append('invalid_value_for_satisfied_condition:'+ref)
                except (ValueError,KeyError,TypeError):
                    errors.append('invalid_condition_observation:'+str(ref))
        for o in p.get('supporting_observations') or []:
            ref=o.get('reference','')
            try:
                v,phase=resolve(case,ref)
                claimed=o.get('value')
                equal=abs(v-claimed)<.0011 if isinstance(v,(int,float)) and isinstance(claimed,(int,float)) else v==claimed
                if not equal:
                    errors.append('value_mismatch:'+ref)
                if o.get('phase')!=phase:
                    errors.append('phase_mismatch:'+ref)
                if (v is None or (ref.endswith('resting_heart_rate_bpm') and v==0)) and o.get('purpose')!='missingness':
                    errors.append('unusable_physiological_evidence:'+ref)
            except (ValueError,KeyError,TypeError):
                errors.append('invalid_observation:'+str(ref))
        for field in ['supporting_observations','violated_conditions','missing_information']:
            if not isinstance(p.get(field),list):
                errors.append('invalid_list:'+field)
        if not p.get('rationale'):
            errors.append('missing_rationale')
        out.append({**p,'validation_errors':sorted(set(errors)),'accepted':not errors,
                    'model_review_required':p.get('review_required',True),
                    'source_audit_review_required':bool(source_review and source_review.get(p['knowledge_id'])),
                    'review_required':p.get('review_required',True) or bool(errors) or bool(source_review and source_review.get(p['knowledge_id']))})
    return out


def annotate(scope='smoke'):
    plan=read(SILVER/'plan.json'); cases,knowledge,_=candidates()
    # Audit ALL requested source conditions before any personal labeling.
    for kid in plan['knowledge_ids']:
        source_label_view(kid)
    if scope=='heldout' and not read(SILVER/'budget.json')['batch_authorized']:
        raise ValueError('Held-out paid batch requires explicit budget authorization')
    if scope=='heldout':
        for cid in plan['smoke_case_ids']:
            for rnd in ('A','B'):
                path=SILVER/f'labels/smoke/{rnd}/{cid}.json'
                if not path.exists() or len(read(path).get('items',[]))!=5 or not any(p.get('accepted') for p in read(path)['items']):
                    raise ValueError('Complete two-round structured Smoke with usable records before held-out batch')
    ids=plan['smoke_case_ids'] if scope=='smoke' else plan['heldout_case_ids']
    client=SilverClient()
    tasks=[(c,rnd) for c in cases if c['case_id'] in ids for rnd in ('A','B')]
    def perform(task):
        c,rnd=task
        def run():
            payload=label_payload(c,rnd)
            raw,meta=client.call(messages(prompts.LABEL,payload),tag=f'label:{scope}:{rnd}',max_tokens=5120,schema=schemas.LABELS,retry_invalid_once=True)
            safety={k['knowledge']['id']:k['source_audit']['source_scope_disputed'] or k['source_audit']['core_claim_support']=='UNVERIFIABLE' for k in payload['candidates']}
            review={k['knowledge']['id']:bool(k['audit_validation_errors']) for k in payload['candidates']}
            items=validate_labels(raw,c,knowledge,safety,review)
            return {'label_provenance':'QWEN_MAX_SILVER','human_gold':False,'round':rnd,'scope':scope,
                    'case_id':c['case_id'],'items':items,'candidate_order':[k['knowledge']['id'] for k in payload['candidates']],
                    'input_sha256':digest(payload),'metadata':meta,'prompt_version':prompts.VERSION,'plan_id':plan['plan_id']}
        try:
            record=checkpoint(f'labels/{scope}/{rnd}/{c["case_id"]}.json',run)
        except Exception as exc:
            failure={'case_id':c['case_id'],'scope':scope,'round':rnd,'items':[],
                     'status':'UNRESOLVED_ANNOTATION_FAILURE','error_type':type(exc).__name__,'at':now(),
                     'label_provenance':'QWEN_MAX_SILVER','no_label_fabricated':True}
            write(SILVER/f'failures/{scope}/{rnd}/{c["case_id"]}-{digest(failure)[:12]}.json',failure)
            print('label_failure scope='+scope+' round='+rnd+' type='+type(exc).__name__,flush=True)
            return failure
        print('label_checkpoint scope='+scope+' round='+rnd,flush=True)
        return record
    with ThreadPoolExecutor(max_workers=3) as pool:
        totals=list(pool.map(perform,tasks))
    return {'round_case_records':len(totals),'label_records':sum(len(r['items']) for r in totals),
            'accepted_records':sum(p['accepted'] for r in totals for p in r['items'])}


def forecast():
    plan=read(SILVER/'plan.json'); cases,_,_=candidates()
    estimates=[]
    for c in cases:
        if c['case_id'] in plan['heldout_case_ids']:
            for rnd in ('A','B'):
                estimates.append(request_options(messages(prompts.LABEL,label_payload(c,rnd)),5120,schemas.LABELS)[1])
    r={'label_provenance':'QWEN_MAX_SILVER','scope':'Held-out prior-applicability-debug participants, one window each, two isolated rounds',
       'participants':len(plan['heldout_case_ids']),'case_windows':len(plan['heldout_case_ids']),
       'distinct_pairs':5*len(plan['heldout_case_ids']),'annotation_records':10*len(plan['heldout_case_ids']),
       'requests':len(estimates),'conservative_cny_reservation':sum(e['reserved_cny'] for e in estimates),
       'actual_invoice_cny':None,'automatic_third_round':False,'budget_authorized':read(SILVER/'budget.json')['batch_authorized'],
       'full_48_case_requests':96,'full_48_case_executed':False,'plan_id':plan['plan_id']}
    write(SILVER/'heldout_forecast.json',r,overwrite=True)
    return r


def revalidate():
    cases,knowledge,_=candidates();byid={c['case_id']:c for c in cases};count=0
    for scope in ('smoke','heldout'):
        for path in sorted((SILVER/'labels'/scope).glob('*/*.json')):
            old=read(path);case=byid[old['case_id']]
            views={k:source_label_view(k) for k in case['candidate_ids']}
            safety={k:v['source_audit']['source_scope_disputed'] or v['source_audit']['core_claim_support']=='UNVERIFIABLE' for k,v in views.items()}
            review={k:bool(v['audit_validation_errors']) for k,v in views.items()}
            cache=read(SILVER/'cache'/(old['metadata']['request_sha256']+'.json'))
            raw=SilverClient.decode(cache['response'])
            items=validate_labels(raw,case,knowledge,safety,review)
            output={**old,'items':items,'validation_source_sha256':sha(path),'revalidated_at':now(),
                    'model_labels_changed':False,'validator_code_sha256':sha(__file__)}
            target=SILVER/'validated_labels'/scope/old['round']/path.name
            write(target,output,overwrite=True);count+=len(items)
    return {'revalidated_label_records':count,'model_requests':0}
