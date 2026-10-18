"""Limited deterministic condition-ID repair probe; never a clinical repair claim."""
from copy import deepcopy
import json
import re

from ..src.common import ROOT, digest, read, rows, sha, write
from ..src.data import candidates
from ..src.matching import validate_item
from ..src.trialgpt import condition_spec
from .api import SILVER


def format_probe():
    plan=read(SILVER/'plan.json');cases,knowledge,_=candidates();bycase={c['case_id']:c for c in cases}
    results=[]
    for method,name in plan['baseline_runs'].items():
        run=ROOT/'local/runs'/name
        keys={e['request_sha256'] for e in read(run/'transport/events.json')}
        for p in rows(run/'predictions.jsonl'):
            aliases=[r for r in p['conditions'] if re.fullmatch(r'condition_index\.\d+',r)]
            if not aliases:
                continue
            proofs=[]
            for path in (ROOT/'local/runs').glob('*/transport/requests/*.json'):
                request=read(path)
                if digest(request) not in keys:
                    continue
                for m in request.get('messages',[]):
                    try:payload=json.loads(m.get('content',''))
                    except (ValueError,TypeError):continue
                    if not isinstance(payload,dict):continue
                    k=payload.get('knowledge',{})
                    if isinstance(k,dict) and k.get('id')==p['knowledge_id'] and payload.get('condition_index')==condition_spec(knowledge[p['knowledge_id']]):
                        proofs.append((path,payload['condition_index']))
            if not proofs:
                results.append({'status':'UNRESOLVED_NO_EXACT_REQUEST_INDEX_PROOF'});continue
            request_path,index=proofs[0]
            mapping={f'condition_index.{i}':c['id'] for i,c in enumerate(index)}
            item={'applicability':p['predicted_applicability'],**{k:deepcopy(p[k]) for k in ['observations','conditions','missing_information','rationale','condition_judgments']}}
            before=deepcopy(item)
            item['conditions']=[mapping.get(ref,ref) for ref in item['conditions']]
            for c in item['condition_judgments'] or []:
                c['condition_id']=mapping.get(c['condition_id'],c['condition_id'])
            errors=[]
            for record in (before,item):
                try:validate_item(record,bycase[p['case_id']],knowledge[p['knowledge_id']],condition_mode=True);errors.append(None)
                except (ValueError,KeyError,TypeError) as exc:errors.append(str(exc))
            results.append({'label_provenance':'QWEN_MAX_SILVER','case_id':p['case_id'],'knowledge_id':p['knowledge_id'],
                            'method':method,'mapping':mapping,'before':before,'after':item,
                            'original_validation_error':errors[0],'after_validation_error':errors[1],
                            'exact_request_sha256':sha(request_path),'original_prediction_sha256':sha(run/'predictions.jsonl'),
                            'label_changed':False,'clinical_correctness_established':False})
    out={'label_provenance':'QWEN_MAX_SILVER','probe':'Deterministic aliases from exact original serialized request index',
         'model_calls':0,'original_files_modified':False,'items':results,
         'pairs_with_exact_request_proof':sum('before' in r for r in results),
         'old_validator_pass_after_id_mapping':sum('after_validation_error' in r and r['after_validation_error'] is None for r in results),
         'clinical_repair_established':False}
    write(SILVER/'format_probe.json',out,overwrite=True)
    return {k:v for k,v in out.items() if k!='items'}
