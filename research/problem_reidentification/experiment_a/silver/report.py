"""Export allowlisted aggregates; retain row-level comparisons and mechanisms privately."""
from collections import Counter
import re

from ..src.common import ROOT, digest, now, read, rows, sha, write
from ..src.data import audit, candidates
from .api import SILVER, PRICE
from .evidence import prepare_evidence
from .pipeline import canonical_source


def tally(values):
    return dict(sorted(Counter(values).items()))


def label_records(scope):
    return {r:{(p['case_id'],p['knowledge_id']):p for f in (SILVER/'labels'/scope/r).glob('*.json')
               for p in read(SILVER/'validated_labels'/scope/r/f.name if (SILVER/'validated_labels'/scope/r/f.name).exists() else f)['items']} for r in ('A','B')}


def agreement(records):
    a,b=records['A'],records['B']; keys=set(a)&set(b)
    accepted=[k for k in keys if a[k]['accepted'] and b[k]['accepted']]
    certain=[k for k in accepted if not a[k]['review_required'] and not b[k]['review_required']]
    same=sum(a[k]['applicability']==b[k]['applicability'] for k in accepted)
    parsed=[k for k in keys if a[k]['applicability'] in ('applicable','not_applicable','insufficient_information') and b[k]['applicability'] in ('applicable','not_applicable','insufficient_information')]
    parsed_same=sum(a[k]['applicability']==b[k]['applicability'] for k in parsed)
    condition_pairs=[]
    for key in keys:
        ca={c['condition_id']:c for c in a[key].get('condition_judgments') or []}
        cb={c['condition_id']:c for c in b[key].get('condition_judgments') or []}
        condition_pairs.extend((ca[c],cb[c]) for c in ca.keys() & cb.keys())
    return {'round_a_records':len(a),'round_b_records':len(b),'paired_records':len(keys),'both_structurally_accepted':len(accepted),
            'accepted_records_by_round':{'A':sum(p['accepted'] for p in a.values()),'B':sum(p['accepted'] for p in b.values())},
            'paired_parseable_labels':len(parsed),'same_parseable_label':parsed_same,
            'raw_label_agreement':parsed_same/len(parsed) if parsed else None,
            'matched_condition_judgments':len(condition_pairs),
            'same_condition_status':sum(x['status']==y['status'] for x,y in condition_pairs),
            'same_condition_role':sum(x['role']==y['role'] for x,y in condition_pairs),
            'same_label_among_both_accepted':same,'label_agreement_among_both_accepted':same/len(accepted) if accepted else None,
            'both_no_review_required':len(certain),'both_rounds_same_model':True,'independent_human_consensus':False,
            'validation_error_categories':tally(e.split(':')[0] for p in [*a.values(),*b.values()] for e in p['validation_errors']),
            'round_label_counts':{r:tally(p['applicability'] for p in ps.values()) for r,ps in records.items()},
            'review_required_by_round':{r:sum(p['review_required'] for p in ps.values()) for r,ps in records.items()},
            'source_scope_disputed_by_round':{r:sum(p['source_scope_disputed'] for p in ps.values()) for r,ps in records.items()}}


def build():
    plan=read(SILVER/'plan.json'); budget=read(SILVER/'budget.json')
    source=[]
    for f in sorted((SILVER/'source_audit').glob('*.json')):
        r=canonical_source(read(f));a=r['audit']
        source.append({'knowledge_id':r['knowledge_id'],'source_url':r['source_evidence']['requested_url'],
                       'source_accessed_at':r['source_evidence']['accessed_at'],
                       'source_fetch_status':r['source_evidence']['status'],'core_claim_support':a['core_claim_support'],
                       'source_scope_disputed':a['source_scope_disputed'],'validation_error_count':len(r['validation_errors']),
                       'model_omitted_condition_count':len(r['model_omitted_conditions']),
                       'quote_locator_diagnostics':r['quote_locator_diagnostics'],
                       'verified_quote_count':sum(1 for c in a['conditions'] for e in c.get('evidence') or []
                           if isinstance(e,dict) and any(p['paragraph_id']==e.get('paragraph_id') and e.get('quote') and e['quote'] in p['text'] for p in r['source_evidence']['paragraphs'])),
                       'validation_error_codes':r['validation_errors'],
                       'conditions':[{'condition_id':c['condition_id'],'role':c['role'],'support':c['support'],
                                      'judgment_origin':c.get('judgment_origin','QWEN_MAX_SILVER'),
                                      'evidence_paragraph_ids':[e.get('paragraph_id') for e in c.get('evidence') or []]} for c in a['conditions']]})
    smoke=label_records('smoke');heldout=label_records('heldout')
    blind=prepare_evidence(); mapping=read(SILVER/'evidence/private_mapping_v2.json')
    audits={p['audit_id']:p for f in (SILVER/'evidence/semantic').glob('*.json')
             for p in read(SILVER/'evidence/revalidated'/f.name if (SILVER/'evidence/revalidated'/f.name).exists() else f)['items']}
    comparison={};private_failures=[];cases,ks,_=candidates();cm={c['case_id']:c for c in cases}
    format_probes=read(SILVER/'format_probe.json')['items'] if (SILVER/'format_probe.json').exists() else []
    for method,name in plan['baseline_runs'].items():
        ps=rows(ROOT/'local/runs'/name/'predictions.jsonl');per_round={}
        for rnd,rs in smoke.items():
            pairs=[(p,rs[(p['case_id'],p['knowledge_id'])]) for p in ps if (p['case_id'],p['knowledge_id']) in rs and rs[(p['case_id'],p['knowledge_id'])]['accepted']]
            equal=sum(p['predicted_applicability']==s['applicability'] for p,s in pairs)
            per_round[rnd]={'compared_pairs':len(pairs),'same_label':equal,'different_label':len(pairs)-equal,
                            'agreement_against_qwen_max_silver':equal/len(pairs) if pairs else None,
                            'silver_review_required_pairs':sum(s['review_required'] for _,s in pairs)}
        comparison[method]=per_round
    for item in blind['items']:
        aid=item['audit_id'];p=item['prediction'];key=(p['case_id'],p['knowledge_id'])
        silver={rnd:rs.get(key) for rnd,rs in smoke.items()}
        private_failures.append({'label_provenance':'QWEN_MAX_SILVER','audit_id':aid,'mapping':mapping[aid],
            'baseline_prediction':p,'longitudinal_evidence':cm[p['case_id']], 'original_knowledge':ks[p['knowledge_id']],
            'source_audit':read(SILVER/'source_audit'/(p['knowledge_id']+'.json')),
            'silver_rounds':silver,'mechanical':item['mechanical'],'blinded_semantic_audit':audits.get(aid),
            'candidate_mechanisms':audits.get(aid,{}).get('findings',[]),
            'repair_checks':{'statistics_supplement':'NOT_RUN','prompt_revision':'NOT_RUN','existing_component_combination':'NOT_RUN'},
            'deterministic_format_probe':next((r for r in format_probes if r.get('case_id')==p['case_id'] and r.get('knowledge_id')==p['knowledge_id'] and r.get('method')==mapping[aid]['method']),None),
            'independent_human_confirmation_required':True,'unrepairable_failure_established':False})
    write(SILVER/'failure_review.json',{'items':private_failures,'human_gold':False},overwrite=True)
    disputes=[]
    for scope,rs in [('smoke',smoke),('heldout',heldout)]:
        for key in rs['A'].keys() & rs['B'].keys():
            a,b=rs['A'][key],rs['B'][key]
            if a['applicability']!=b['applicability'] or a['validation_errors'] or b['validation_errors']:
                cid,kid=key
                disputes.append({'scope':scope,'case_id':cid,'knowledge_id':kid,'longitudinal_evidence':cm[cid],
                  'source_audit':read(SILVER/'source_audit'/(kid+'.json')),'round_A':a,'round_B':b,
                  'label_disagreement':a['applicability']!=b['applicability'],
                  'review_required':True,'independent_human_confirmation':False})
    write(SILVER/'silver_disagreements.json',{'label_provenance':'QWEN_MAX_SILVER','items':disputes},overwrite=True)
    proposed=[{'knowledge_id':f.stem,'label_provenance':'QWEN_MAX_SILVER','frozen_input_changed':False,
                'audit':canonical_source(read(f))['audit'],'validation_errors':canonical_source(read(f))['validation_errors']}
              for f in sorted((SILVER/'source_audit').glob('*.json'))]
    proposal_path=SILVER/'proposed_conditions_v1.json'
    if not proposal_path.exists():
        write(proposal_path,{'label_provenance':'QWEN_MAX_SILVER','items':proposed,'human_approved':False})
    e3={}
    base={(p['case_id'],p['knowledge_id']):p for p in rows(ROOT/'local/runs'/plan['baseline_runs']['direct']/'predictions.jsonl')}
    for view,name in [('current','e3-direct-current-v8'),('statistics','e3-direct-statistics-v8')]:
        ps=rows(ROOT/'local/runs'/name/'predictions.jsonl')
        e3[view]={'pairs':len(ps),'label_changes_vs_full':sum(p['predicted_applicability']!=base[(p['case_id'],p['knowledge_id'])]['predicted_applicability'] for p in ps),
                  'unknown_labels':sum(p['predicted_applicability']=='insufficient_information' for p in ps),
                  'rationale_causal_benefit_established':False}
    attempts=budget['attempts'];metas=[a['metadata'] for a in attempts if a.get('metadata')]
    source_summary={'knowledge_items':len(source),'conditions':sum(len(s['conditions']) for s in source),
            'condition_support_counts':tally(c['support'] for s in source for c in s['conditions']),
            'condition_role_counts':tally(c['role'] for s in source for c in s['conditions']),
            'core_support_counts':tally(s['core_claim_support'] for s in source),
            'scope_disputed_items':sum(s['source_scope_disputed'] for s in source),
            'source_validation_error_count':sum(s['validation_error_count'] for s in source),
            'source_quote_mismatch_count':sum(e.startswith('quote_not_in_snapshot:') for s in source for e in s['validation_error_codes']),
            'model_omitted_conditions':sum(s['model_omitted_condition_count'] for s in source), 'items':source}
    legacy=[p['audit_id'] for p in blind['items'] if p['mechanical']['legacy_reference_failed']]
    costs={'new_request_attempts':len(attempts),'successful_responses':len(metas),
           'requested_model':'qwen-max','returned_models':sorted({m['returned_model'] for m in metas}),
           'server_fingerprint_values':sorted({m['system_fingerprint'] for m in metas if m.get('system_fingerprint')}),
           'server_version_limit':'Rolling alias; snapshot/weights not certified by response model string',
           'prompt_tokens':sum(m['usage'].get('prompt_tokens',0) for m in metas),
           'completion_tokens':sum(m['usage'].get('completion_tokens',0) for m in metas),
           'estimated_cny_no_discount':sum(m.get('estimated_cny_no_discount') or 0 for m in metas),
           'estimated_cny_reported_cache':sum(m.get('estimated_cny_reported_cache') or 0 for m in metas),
           'budget_accounted_cny':sum(a.get('charged_estimate_cny',a['reserved_cny']) for a in attempts),
           'uncertain_attempts':sum(not a.get('metadata') for a in attempts),
           'cap_cny':budget['cap_cny'],'max_calls':budget['max_calls'],'price':PRICE,'actual_invoice_cny':None,
           'parameters':{'model':'qwen-max','temperature':0,'response_format':{'type':'json_object'},'stream':False,
                         'source_response_mode':'JSON Object; one explicit 8192-token source retry after truncation',
                         'final_label_evidence_response_mode':'Forced declarative function argument Schema; no external tool execution',
                         'max_tokens_source_and_evidence':4096,'max_tokens_labels':5120,'max_retries':0},
           'sdk_versions':sorted({m['api_sdk_version'] for m in metas})}
    costs['explicit_format_retries']=len(read(SILVER/'format_retries.json')) if (SILVER/'format_retries.json').exists() else 0
    tests={}
    for suite,filename in [('experiment_a','tests-experiment-final.log'),('p1','tests-p1-final.log'),('c1','tests-c1-final.log')]:
        f=SILVER/filename;text=f.read_text(encoding='utf-8') if f.exists() else ''
        match=re.search(r'Ran (\d+) tests? in ([\d.]+)s',text)
        tests[suite]={'count':int(match[1]) if match else None,'passed':bool(match and re.search(r'^OK\s*$',text,re.M)),
                      'log_sha256':sha(f) if f.exists() else None}
    call_log={'label_provenance':'QWEN_MAX_SILVER','price':PRICE,'actual_invoice_cny':None,
              'attempts':[{k:v for k,v in a.items() if k in ['tag','request_sha256','at','status','model_requested',
                            'input_token_ceiling','output_token_ceiling','reserved_cny','charged_estimate_cny',
                            'error_type','http_status','metadata']} for a in attempts]}
    smoke_aggregate=agreement(smoke)
    smoke_aggregate.pop('round_label_counts',None)
    smoke_aggregate['privacy_note']='Single-case per-class and per-knowledge label distributions remain private'
    result={'version':'silver-analysis-v1','recorded_at':now(),'label_provenance':'QWEN_MAX_SILVER','human_gold':False,
      'plan_id':plan['plan_id'],'input_integrity':{k:v for k,v in audit().items() if k in ['legacy_hashes_verified','p1_release_id','cases','participants','a0_pairs']},
      'source_audit':source_summary,'smoke_double_annotation':smoke_aggregate,'heldout_double_annotation':agreement(heldout),
      'heldout_selection':{'eligible_participants':len(plan['heldout_case_ids']),'one_window_per_participant':True,
                           'participant_overlap_with_prior_applicability_debugging':False,'all_prior_retrieval_exposure':True,
                           'batch_authorized':budget['batch_authorized'],'batch_executed':bool(heldout['A'] or heldout['B'])},
      'heldout_completion':{'expected_round_windows':2*len(plan['heldout_case_ids']),
                             'completed_round_windows':len(list((SILVER/'labels/heldout').glob('*/*.json'))),
                             'expected_annotation_records':10*len(plan['heldout_case_ids']),
                             'complete':len(heldout['A'])==5*len(plan['heldout_case_ids']) and len(heldout['B'])==5*len(plan['heldout_case_ids'])},
      'heldout_disagreements_by_knowledge':tally(d['knowledge_id'] for d in disputes if d['scope']=='heldout' and d['label_disagreement']),
      'evidence_audit':{'existing_predictions':len(blind['items']),'legacy_failures':len(legacy),'blinded_semantically_reviewed':len(audits),
                        'status_counts_nonexclusive':tally(s for a in audits.values() for s in a['statuses']),
                        'validation_clean_reviews':sum(not a['validation_errors'] for a in audits.values()),
                        'auditor_consistency_errors':tally(e.split(':')[0] for a in audits.values() for e in a['validation_errors']),
                        'status_counts_consistent_audits_only':tally(s for a in audits.values() if not a['validation_errors'] for s in a['statuses']),
                        'legacy_23_interpretations':tally(audits[i]['legacy_failure_interpretation'] for i in legacy if i in audits),
                        'legacy_failure_reason_counts':tally(p['mechanical']['legacy_error'] for p in blind['items'] if p['mechanical']['legacy_reference_failed']),
                        'mechanical_finding_counts_nonexclusive':tally(f['kind'] for p in blind['items'] for f in p['mechanical']['findings']),
                        'mechanically_confirmed_explicit_value_error_predictions':sum(any(f['kind']=='INVALID_VALUE' for f in p['mechanical']['findings']) for p in blind['items']),
                        'semantic_statuses_are_same_family_model_judgments':True,'applicability_errors_established':False},
      'exploratory_agreement_against_qwen_max_silver':comparison,'information_view_changes':e3,'costs':costs,
      'tests':tests,
      'deterministic_format_probe':{k:v for k,v in read(SILVER/'format_probe.json').items() if k!='items'} if (SILVER/'format_probe.json').exists() else None,
      'formal_accuracy':None,'stable_unrepairable_failure_established':False,
      'limitations':['Same model family, same-model repeated annotation, source scope proposals not human confirmed',
                     'Existing baseline comparisons cover one previously debugged participant/window only',
                     'No repair intervention was run; evidence faults do not establish an applicability-label error',
                     'Held-out participants are unexposed to prior applicability debugging, not to all E1 retrieval',
                     'Source snapshots are current; historical device documentation equivalence not established']}
    versions=[int(m[1]) for f in (ROOT/'results').glob('silver_summary_v*.json')
              if (m:=re.fullmatch(r'silver_summary_v(\d+)\.json',f.name))]
    output=ROOT/'results'/f'silver_summary_v{1+max(versions,default=0)}.json'
    write(output,result)
    write(output.with_name(output.stem+'_calls.json'),call_log)
    write(ROOT/'results/silver_latest.json',{'path':output.relative_to(ROOT).as_posix(),'sha256':sha(output),'label_provenance':'QWEN_MAX_SILVER'},overwrite=True)
    return {'public_report':output.relative_to(ROOT).as_posix(),'source_conditions':source_summary['conditions'],
            'smoke_agreement':result['smoke_double_annotation'],'heldout_agreement':result['heldout_double_annotation'],
            'evidence_audit':result['evidence_audit'],'costs':costs}
