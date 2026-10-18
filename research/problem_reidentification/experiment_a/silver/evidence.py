"""Blind method identities before mechanical and model semantic evidence audit."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import random
import re

from ..src.common import ROOT, digest, read, rows, sha, write
from ..src.data import candidates, evidence_value
from ..src.trialgpt import condition_spec
from .api import SILVER, SilverClient, estimate, request_options
from .pipeline import array_value, case_payload, checkpoint, messages, resolve, source_label_view
from . import prompts
from . import schemas

STATUSES={'VALID_EVIDENCE','INVALID_REFERENCE','INVALID_VALUE','TEMPORAL_MISMATCH',
          'UNSUPPORTED_INFERENCE','INSUFFICIENT_INFORMATION','UNRESOLVED'}


def hide_identity(value):
    if isinstance(value,str):
        return re.sub(r'\b(?:PHA|PHIA|TrialGPT(?:-style)?|DataScienceAgent|qwen3\.8-max|qwen-max)\b',
                      '[prior analysis]',value,flags=re.I)
    if isinstance(value,list):return [hide_identity(v) for v in value]
    if isinstance(value,dict):return {k:hide_identity(v) for k,v in value.items()}
    return value


def mechanical(prediction,case,k):
    """Separate reference contracts from physiological misuse; do not guess semantics."""
    findings=[]
    refs=prediction.get('observations',[])
    for ref in refs:
        candidate=ref
        normalized=False
        match=re.fullmatch(r'(d\d+\.[a-z_]+|context\.[a-z_]+)\s*:\s*.+',ref)
        if match:
            candidate=match[1];normalized=True
        try:
            value,phase=resolve(case,candidate)
            findings.append({'reference':ref,'resolved_reference':candidate,'value':value,'phase':phase,
                             'kind':'FORMAT_ONLY_CANDIDATE' if normalized else 'UNUSABLE_REFERENCE_NEEDS_PURPOSE_REVIEW' if value is None or (candidate.endswith('resting_heart_rate_bpm') and value==0) else 'REFERENCE_EXISTS',
                             'physiological_use_proven':False})
        except (ValueError,KeyError,TypeError):
            findings.append({'reference':ref,'kind':'INVALID_REFERENCE'})
    known={c['id'] for c in condition_spec(k)}
    for ref in prediction.get('conditions',[]):
        if ref not in known:
            findings.append({'reference':ref,'kind':'UNKNOWN_CONDITION_REFERENCE',
                             'format_issue_candidate':bool(re.fullmatch(r'condition_index\.\d+',ref))})
    if not refs:
        findings.append({'kind':'NO_STRUCTURED_OBSERVATIONS','explanation':'Output contract issue; prose evidence may still exist'})
    text=prediction.get('rationale','')
    # Only explicit unambiguous day.field=value assertions, not free-text
    # clinical claims. All other numerics remain for the blinded semantic stage.
    claims=[(m[1],float(m[2]),m[0]) for m in re.finditer(r'(d\d+\.[a-z_]+)\s*(?:=|is|at)\s*(\d+(?:\.\d+)?)',text)]
    claims.extend((f'd{m[1]}.{m[2]}',float(m[3]),m[0]) for m in re.finditer(r'\b(?:d|day\s*)(\d+)\s*,?\s+(?:where\s+)?([a-z_]+)\s+(?:is|=)\s*(\d+(?:\.\d+)?)',text))
    for ref,number,excerpt in claims:
        try:
            actual,_=resolve(case,ref)
            if actual is None or not isinstance(actual,(int,float)) or abs(actual-number)>.11:
                finding={'kind':'INVALID_VALUE','reference':ref,'claimed':number,'actual':actual,'claim_excerpt':excerpt,
                         'same_value_other_days':[f"d{d['day']}.{ref.split('.')[1]}" for d in case['days'] if isinstance(d['metrics'].get(ref.split('.')[1]),(int,float)) and abs(d['metrics'][ref.split('.')[1]]-number)<.11]}
                findings.append(finding)
        except (ValueError,KeyError,TypeError):
            findings.append({'kind':'INVALID_REFERENCE','reference':ref,'claim_excerpt':excerpt})
    return {'legacy_reference_failed':prediction.get('evidence_validation_status')=='invalid',
            'legacy_error':prediction.get('evidence_validation_error'),'findings':findings,
            'semantic_error_inferred_from_legacy_failure':False}


def prepare_evidence():
    path=SILVER/'evidence/blinded_input_v3.json'
    if path.exists():
        return read(path)
    plan=read(SILVER/'plan.json'); cases,knowledge,_=candidates(); bycase={c['case_id']:c for c in cases}
    originals=[]
    for method,name in plan['baseline_runs'].items():
        f=ROOT/'local/runs'/name/'predictions.jsonl'
        for index,p in enumerate(rows(f)):
            originals.append((method,name,f,index,p))
    random.Random(plan['order_seeds']['evidence']).shuffle(originals)
    blind,mapping=[],{}
    for i,(method,name,source_path,index,p) in enumerate(originals):
        key=f'E{i+1:03d}'
        clean={k:p.get(k) for k in ['knowledge_id','case_id','predicted_applicability','observations','conditions',
                                  'condition_judgments','missing_information','rationale']}
        clean=hide_identity(clean)
        # Case/knowledge IDs are study-local; no method, model or raw trace paths.
        item={'audit_id':key,'prediction':clean,'mechanical':mechanical(p,bycase[p['case_id']],knowledge[p['knowledge_id']])}
        blind.append(item)
        mapping[key]={'method':method,'run':name,'index':index,'prediction_file_sha256':sha(source_path),
                      'case_id':p['case_id'],'knowledge_id':p['knowledge_id']}
    if len(blind)!=30 or sum(b['mechanical']['legacy_reference_failed'] for b in blind)!=23:
        raise ValueError('Expected exactly the frozen selected 30 predictions and 23 legacy failures')
    mapping_path=SILVER/'evidence/private_mapping_v2.json'
    if mapping_path.exists():
        if read(mapping_path)!=mapping:
            raise ValueError('Existing blind mapping differs; retain the original and declare a new version')
    else:
        write(mapping_path,mapping)
    result={'label_provenance':'QWEN_MAX_SILVER','items':blind,'methods_removed_before_audit':True,
            'baseline_file_hashes':{k:v['prediction_file_sha256'] for k,v in mapping.items()},'plan_id':plan['plan_id']}
    write(path,result)
    return result


def audit_evidence():
    blind=prepare_evidence(); cases,_,_=candidates(); bycase={c['case_id']:c for c in cases}; client=SilverClient()
    def payload_for(items):
        cids={p['prediction']['case_id'] for p in items};kids={p['prediction']['knowledge_id'] for p in items}
        return {'records':{c:case_payload(bycase[c]) for c in sorted(cids)},
                'knowledge':{k:source_label_view(k) for k in sorted(kids)},'blinded_predictions':items}
    batches=[]
    def add(items):
        try:
            request_options(messages(prompts.EVIDENCE,payload_for(items)),4096,schemas.EVIDENCE)
            batches.append(items)
        except ValueError:
            if len(items)==1:raise
            midpoint=len(items)//2;add(items[:midpoint]);add(items[midpoint:])
    for offset in range(0,len(blind['items']),3):add(blind['items'][offset:offset+3])
    def perform(task):
        batch,items=task
        def run(items=items):
            payload=payload_for(items)
            output,meta=client.call(messages(prompts.EVIDENCE,payload),tag='evidence:'+str(batch),max_tokens=4096,schema=schemas.EVIDENCE)
            expected={p['audit_id'] for p in items}
            actual=array_value(output.get('items',[]))
            if len(actual)!=len(expected) or {p['audit_id'] for p in actual}!=expected:
                raise ValueError('Evidence audit set mismatch')
            for p in actual:
                errors=[]
                for field in ('statuses','findings'):
                    p[field]=array_value(p.get(field)) or []
                statuses=p.get('statuses',[])
                if not statuses or not set(statuses)<=STATUSES:
                    errors.append('invalid_status_set')
                if 'VALID_EVIDENCE' in statuses and len(statuses)>1:
                    errors.append('contradictory_valid_status')
                if p.get('applicability_error_established') is not False:
                    errors.append('evidence_audit_cannot_establish_applicability_error')
                pred=next(x['prediction'] for x in items if x['audit_id']==p['audit_id'])
                for finding in p.get('findings',[]):
                    finding['observation_references']=array_value(finding.get('observation_references')) or []
                    for ref in finding.get('observation_references',[]):
                        try: resolve(bycase[pred['case_id']],ref)
                        except (ValueError,KeyError,TypeError): errors.append('unresolved_auditor_reference:'+str(ref))
                p['validation_errors']=errors
                p['review_required']=p.get('review_required',True) or bool(errors)
            return {'label_provenance':'QWEN_MAX_SILVER','items':actual,'metadata':meta,'prompt_version':prompts.VERSION,
                    'input_sha256':digest(payload),'method_identity_shown':False,'silver_labels_shown':False}
        record=checkpoint(f'evidence/semantic/batch-{batch:02d}.json',run)
        print('evidence_checkpoint '+str(batch+1)+'/'+str(len(batches)),flush=True)
        return record
    with ThreadPoolExecutor(max_workers=3) as pool:
        result=list(pool.map(perform,enumerate(batches)))
    return {'predictions_reviewed':sum(len(r['items']) for r in result),'auditor_reference_errors':sum(bool(p['validation_errors']) for r in result for p in r['items'])}


def revalidate_evidence():
    """Check auditor consistency, allowing it to identify a bad INPUT reference."""
    blind={p['audit_id']:p for p in prepare_evidence()['items']}
    cases,_,_=candidates();bycase={c['case_id']:c for c in cases};count=0;valid=0
    for path in sorted((SILVER/'evidence/semantic').glob('*.json')):
        original=read(path);checked=[]
        for raw in original['items']:
            p=dict(raw);errors=[];reported_invalid=[]
            item=blind[p['audit_id']];pred=item['prediction']
            if item['mechanical']['legacy_reference_failed'] and p['legacy_failure_interpretation']=='no_legacy_failure':
                errors.append('legacy_failure_classification_contradicts_input')
            if not p.get('statuses') or not set(p['statuses'])<=STATUSES:
                errors.append('invalid_status_set')
            if 'VALID_EVIDENCE' in p['statuses'] and len(p['statuses'])>1:
                errors.append('contradictory_valid_status')
            for finding in p.get('findings',[]):
                for ref in finding.get('observation_references',[]):
                    try:resolve(bycase[pred['case_id']],ref)
                    except (ValueError,KeyError,TypeError):
                        if finding.get('status')=='INVALID_REFERENCE' and ref in pred.get('conditions',[])+pred.get('observations',[]):
                            reported_invalid.append(ref)
                        else:errors.append('unresolved_auditor_reference:'+ref)
            p.update(validation_errors=errors,reported_invalid_input_references=reported_invalid,
                     review_required=p.get('review_required',True) or bool(errors),audit_usable=not errors)
            checked.append(p);count+=1;valid+=not errors
        write(SILVER/'evidence/revalidated'/path.name,{**original,'items':checked,
              'validation_source_sha256':sha(path),'model_judgments_changed':False,
              'validator_code_sha256':sha(__file__)},overwrite=True)
    return {'audits_rechecked':count,'consistent_audits':valid,'model_requests':0}
