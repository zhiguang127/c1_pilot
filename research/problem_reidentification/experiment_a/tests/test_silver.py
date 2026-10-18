"""Silver software fixtures, never annotations or human evidence."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.problem_reidentification.experiment_a.src.common import LOCAL, digest, read, write, write_rows, freeze
from research.problem_reidentification.experiment_a.src.data import candidates
from research.problem_reidentification.experiment_a.silver.api import SilverClient, MODEL, estimate
from research.problem_reidentification.experiment_a.silver.evidence import mechanical
from research.problem_reidentification.experiment_a.silver.pipeline import array_value, case_payload, resolve, validate_source, validate_labels
from research.problem_reidentification.experiment_a.silver.sources import extract


class SilverTests(unittest.TestCase):
    def test_rounds_change_only_order_and_marker_without_baseline_or_peer_labels(self):
        from research.problem_reidentification.experiment_a.silver.pipeline import label_payload
        cases,_,_=candidates();case=cases[0]
        def view(kid):return {'knowledge':{'id':kid},'source_audit':{'conditions':[]}}
        with patch('research.problem_reidentification.experiment_a.silver.pipeline.read',return_value={'order_seeds':{'A':73181}}),patch('research.problem_reidentification.experiment_a.silver.pipeline.source_label_view',side_effect=view):
            a,b=label_payload(case,'A'),label_payload(case,'B')
        self.assertEqual(a['personal_records'],b['personal_records'])
        self.assertEqual(a['required_output_knowledge_ids'],list(reversed(b['required_output_knowledge_ids'])))
        self.assertNotIn('predicted_applicability',json.dumps(a))
        self.assertNotIn('label_provenance',json.dumps(a))
        self.assertNotIn('baseline_runs',json.dumps(a))

    def test_full_personal_table_preserves_all_original_rows_and_quality(self):
        cases,_,_=candidates();c=cases[0];p=case_payload(c)
        for original,values in zip(c['days'],p['daily_rows']):
            row=dict(zip(p['daily_columns'],values))
            self.assertEqual(row['day'],original['day'])
            self.assertEqual(row['phase'],original['phase'])
            self.assertEqual({k:row[k] for k in original['metrics']},original['metrics'])
        self.assertEqual(len(p['daily_rows']),42)
        quality={d:(flags,missing) for d,flags,missing in p['daily_quality_rows']}
        for d in c['days']:
            flags,missing=quality.get(d['day'],([],[]))
            self.assertEqual([p['quality_flag_dictionary'][i] for i in flags],d['quality_flags'])
            self.assertEqual([p['missing_metric_dictionary'][i] for i in missing],d['missing_metrics'])
        self.assertNotIn('subject_id',p)

    def test_null_and_zero_are_not_automatically_physiological_misuse(self):
        c={'context':{},'days':[{'day':29,'metrics':{'resting_heart_rate_bpm':0,'sleep_minutes':None}}]}
        k={'applicability':{'population':['Adults']}}
        p={'observations':['d29.sleep_minutes','d29.resting_heart_rate_bpm'],'conditions':['population.0'],'rationale':'Both unusable readings are excluded.'}
        r=mechanical(p,c,k)
        self.assertEqual([x['kind'] for x in r['findings']],['UNUSABLE_REFERENCE_NEEDS_PURPOSE_REVIEW']*2)
        self.assertFalse(any(x['physiological_use_proven'] for x in r['findings']))

    def test_explicit_wrong_day_value_is_reproducible(self):
        c={'context':{},'days':[{'day':29,'metrics':{'sleep_minutes':None}},{'day':30,'metrics':{'sleep_minutes':452}}]}
        p={'observations':['d29.sleep_minutes'],'rationale':'d29.sleep_minutes=452','conditions':[]}
        r=mechanical(p,c,{'applicability':{}})
        f=next(x for x in r['findings'] if x['kind']=='INVALID_VALUE')
        self.assertEqual(f['same_value_other_days'],['d30.sleep_minutes'])
        self.assertIsNone(f['actual'])

    def test_spelled_out_day_field_claim_keeps_the_same_temporal_check(self):
        c={'context':{},'days':[{'day':29,'metrics':{'sleep_minutes':None}},{'day':30,'metrics':{'sleep_minutes':452}}]}
        p={'observations':['d29.sleep_minutes'],'rationale':'including d29 where sleep_minutes is 452','conditions':[]}
        self.assertTrue(any(f['kind']=='INVALID_VALUE' for f in mechanical(p,c,{'applicability':{}})['findings']))

    def test_inline_reference_format_is_distinct_from_unknown_identifier(self):
        c={'context':{},'days':[{'day':30,'metrics':{'sleep_minutes':452}}]}
        p={'observations':['d30.sleep_minutes: 452','d999.sleep_minutes'],'rationale':'','conditions':[]}
        fs=mechanical(p,c,{'applicability':{}})['findings']
        self.assertEqual([f['kind'] for f in fs],['FORMAT_ONLY_CANDIDATE','INVALID_REFERENCE'])

    def test_source_quote_must_exist_in_original_snapshot(self):
        k={'applicability':{'population':['Adults']}}
        result={'conditions':[{'condition_id':'population.0','original_text':'Adults','role':'optional_background','support':'EXPLICIT_SUPPORT','evidence':[{'paragraph_id':'P1','quote':'fabricated'}]}]}
        self.assertIn('quote_not_in_snapshot:population.0',validate_source(result,k,{'paragraphs':[{'paragraph_id':'P1','text':'Actual primary source text'}]}))

    def test_source_audit_review_flag_does_not_replace_model_label(self):
        k={'K':{'applicability':{'population':['Adults']}}}
        case={'case_id':'C','candidate_ids':['K'],'days':[],'context':{'population':'Adults'}}
        p={'case_id':'C','knowledge_id':'K','applicability':'applicable','annotation_model':'qwen-max',
           'label_provenance':'QWEN_MAX_SILVER','source_scope_disputed':False,'review_required':False,
           'condition_judgments':[{'condition_id':'population.0','status':'satisfied','role':'optional_background','observations':['context.population']}],
           'supporting_observations':[{'reference':'context.population','value':'Adults','phase':'context','purpose':'context'}],
           'violated_conditions':[],'missing_information':[],'rationale':'Software fixture'}
        checked=validate_labels({'items':[p]},case,k,source_review={'K':True})[0]
        self.assertEqual(checked['applicability'],'applicable')
        self.assertTrue(checked['accepted'])
        self.assertFalse(checked['model_review_required'])
        self.assertTrue(checked['review_required'])

    def test_explicit_missingness_can_support_a_missingness_condition(self):
        k={'K':{'applicability':{'observable_conditions':['Missing value present']}}}
        case={'case_id':'C','candidate_ids':['K'],'days':[{'day':29,'metrics':{'sleep_minutes':None}}],'context':{}}
        p={'case_id':'C','knowledge_id':'K','applicability':'applicable','annotation_model':'qwen-max',
           'label_provenance':'QWEN_MAX_SILVER','source_scope_disputed':False,'review_required':False,
           'condition_judgments':[{'condition_id':'observable_conditions.0','status':'satisfied','observations':['d29.sleep_minutes']}],
           'supporting_observations':[{'reference':'d29.sleep_minutes','value':None,'phase':'current','purpose':'missingness'}],
           'violated_conditions':[],'missing_information':[],'rationale':'Software missingness fixture'}
        self.assertTrue(validate_labels({'items':[p]},case,k)[0]['accepted'])
        p['supporting_observations'][0]['purpose']='physiology'
        self.assertFalse(validate_labels({'items':[p]},case,k)[0]['accepted'])

    def test_bad_input_reference_is_identifiable_without_becoming_bad_auditor_evidence(self):
        from research.problem_reidentification.experiment_a.silver.evidence import revalidate_evidence
        with tempfile.TemporaryDirectory(dir=LOCAL) as name:
            root=Path(name)
            source={'audit_id':'E1','prediction':{'case_id':'C','conditions':['condition_index.0'],'observations':[]},
                    'mechanical':{'legacy_reference_failed':True}}
            audit={'audit_id':'E1','statuses':['INVALID_REFERENCE'],'legacy_failure_interpretation':'format_only',
                   'findings':[{'status':'INVALID_REFERENCE','observation_references':['condition_index.0']}],
                   'review_required':False}
            write(root/'evidence/semantic/batch.json',{'items':[audit]})
            with patch('research.problem_reidentification.experiment_a.silver.evidence.SILVER',root),patch('research.problem_reidentification.experiment_a.silver.evidence.prepare_evidence',return_value={'items':[source]}),patch('research.problem_reidentification.experiment_a.silver.evidence.candidates',return_value=([{'case_id':'C','days':[],'context':{}}],{},'fixture')):
                result=revalidate_evidence()
            self.assertEqual(result['consistent_audits'],1)
            item=read(root/'evidence/revalidated/batch.json')['items'][0]
            self.assertEqual(item['reported_invalid_input_references'],['condition_index.0'])

    def test_source_unavailable_does_not_become_supported(self):
        result={'conditions':[{'condition_id':'population.0','original_text':'Adults','role':'disputed','support':'EXPLICIT_SUPPORT','evidence':[]}]}
        self.assertIn('no_source_evidence:population.0',validate_source(result,{'applicability':{'population':['Adults']}},{'paragraphs':[]}))

    def test_unverifiable_source_may_have_null_evidence_without_invented_quote(self):
        result={'conditions':[{'condition_id':'population.0','original_text':'Adults','role':'disputed','support':'UNVERIFIABLE','evidence':None}]}
        self.assertEqual(validate_source(result,{'applicability':{'population':['Adults']}},{'paragraphs':[]}),[])

    def test_source_extraction_keeps_heading_locator_and_removes_scripts(self):
        p=extract('<main><h2>Habits for sleep</h2><p>Go to bed at the same time.</p><script>invented false claim</script></main>')
        self.assertEqual(p[-1]['heading'],'Habits for sleep')
        self.assertNotIn('invented',str(p))

    def test_stat_reference_has_correct_phase(self):
        cases,_,_=candidates()
        _,phase=resolve(cases[0],'stats.baseline.sleep_minutes.mean')
        self.assertEqual(phase,'baseline')
        with self.assertRaises((ValueError,KeyError)):
            resolve(cases[0],'stats.current.sleep_minutes.nonexistent')

    def test_context_ceiling_refuses_truncation(self):
        with self.assertRaises(ValueError):
            estimate([{'role':'user','content':'x'*40000}],4096)

    def test_nested_json_string_array_is_decoded_without_label_changes(self):
        self.assertEqual(array_value('[{"paragraph_id":"P1","quote":"actual"}]'),[{'paragraph_id':'P1','quote':'actual'}])
        self.assertEqual(array_value('insufficient_information'),'insufficient_information')

    def test_blind_export_never_targets_original_predictions(self):
        from research.problem_reidentification.experiment_a.silver.evidence import prepare_evidence
        with tempfile.TemporaryDirectory(dir=LOCAL) as name:
            root=Path(name);silver=root/'silver';original=root/'local/runs/fixture/predictions.jsonl'
            write(silver/'plan.json',{'baseline_runs':{'method':'fixture'},'order_seeds':{'evidence':1},'plan_id':'fixture'})
            ps=[{'case_id':'C','knowledge_id':'K','observations':[],'conditions':[],'rationale':'fixture','evidence_validation_status':'invalid' if i<23 else 'ok'} for i in range(30)]
            write_rows(original,ps);old=original.read_bytes()
            with patch('research.problem_reidentification.experiment_a.silver.evidence.ROOT',root),patch('research.problem_reidentification.experiment_a.silver.evidence.SILVER',silver),patch('research.problem_reidentification.experiment_a.silver.evidence.candidates',return_value=([{'case_id':'C','days':[],'context':{}}],{'K':{'applicability':{}}},'fixture')):
                result=prepare_evidence()
            self.assertEqual(len(result['items']),30)
            self.assertTrue((silver/'evidence/blinded_input_v3.json').exists())
            self.assertEqual(original.read_bytes(),old)

    def test_method_names_inside_explanations_are_also_hidden(self):
        from research.problem_reidentification.experiment_a.silver.evidence import hide_identity
        raw={'rationale':'The PHA analysis reports no change. TrialGPT-style matching used Qwen3.8-max.'}
        blind=hide_identity(raw)
        self.assertNotIn('PHA',blind['rationale'])
        self.assertNotIn('Qwen',blind['rationale'])
        self.assertIn('no change',blind['rationale'])
        self.assertIn('PHA',raw['rationale'])

    def test_silver_cannot_enter_human_gold_reader(self):
        from research.problem_reidentification.experiment_a.src.evaluation import trusted_gold
        with tempfile.TemporaryDirectory(dir=LOCAL) as name:
            d=Path(name)
            write(d/'provenance.json',{'data_release_id':'fixture','gold_kind':'QWEN_MAX_SILVER'})
            (d/'gold.jsonl').write_text('',encoding='utf-8')
            freeze(d,['provenance.json','gold.jsonl'],{'version':'software-fixture'})
            with self.assertRaises(ValueError):trusted_gold(d,'fixture')

    def test_incomplete_rounds_cannot_be_frozen_as_complete_silver_release(self):
        from research.problem_reidentification.experiment_a.silver.release import freeze_release
        with tempfile.TemporaryDirectory(dir=LOCAL) as name:
            root=Path(name)
            with patch('research.problem_reidentification.experiment_a.silver.release.SILVER',root),patch('research.problem_reidentification.experiment_a.silver.release.read',return_value={'heldout_case_ids':[]}),patch('research.problem_reidentification.experiment_a.silver.release.label_records',return_value={'A':{},'B':{}}):
                with self.assertRaises(ValueError):freeze_release()
            self.assertFalse((root/'release-v1').exists())

    def test_format_probe_requires_actual_request_index_and_preserves_original(self):
        from research.problem_reidentification.experiment_a.silver.probes import format_probe
        with tempfile.TemporaryDirectory(dir=LOCAL) as name:
            root=Path(name);silver=root/'silver';run=root/'local/runs/current'
            k={'id':'K','applicability':{'population':['Adults']}}
            case={'case_id':'C','context':{'population':'Adults'},'days':[]}
            p={'case_id':'C','knowledge_id':'K','predicted_applicability':'applicable','observations':['context.population'],
               'conditions':['condition_index.0'],'missing_information':[],'rationale':'fixture',
               'condition_judgments':[{'condition_id':'condition_index.0','status':'satisfied','role':'necessary','observations':['context.population'],'rationale':'fixture'}]}
            request={'messages':[{'role':'user','content':json.dumps({'knowledge':k,'condition_index':[{'id':'population.0','text':'Adults','source_field':'population'}]})}]}
            write(silver/'plan.json',{'baseline_runs':{'fixture':'current'}})
            write_rows(run/'predictions.jsonl',[p]);old=(run/'predictions.jsonl').read_bytes()
            write(run/'transport/events.json',[{'request_sha256':digest(request)}])
            write(run/'transport/requests/request.json',request)
            with patch('research.problem_reidentification.experiment_a.silver.probes.ROOT',root),patch('research.problem_reidentification.experiment_a.silver.probes.SILVER',silver),patch('research.problem_reidentification.experiment_a.silver.probes.candidates',return_value=([case],{'K':k},'fixture')):
                r=format_probe()
            self.assertEqual(r['old_validator_pass_after_id_mapping'],1)
            self.assertFalse(r['clinical_repair_established'])
            self.assertEqual((run/'predictions.jsonl').read_bytes(),old)


try:
    import httpx
    import openai
    HAS_SDK=True
except ImportError:
    HAS_SDK=False


@unittest.skipUnless(HAS_SDK,'Isolated PHA dependencies required')
class SilverTransportTests(unittest.TestCase):
    def test_parse_failure_retry_is_once_identical_and_preserves_billed_response(self):
        from openai import OpenAI as Actual
        from research.problem_reidentification.experiment_a.silver import schemas
        with tempfile.TemporaryDirectory(dir=LOCAL/'silver_annotations') as name:
            root=Path(name);sc=SilverClient(root);sc.initialize(cap_cny=1,max_calls=3)
            requests=[]
            def handler(request):
                requests.append(json.loads(request.content))
                args='{"items":[]}' if len(requests)>1 else '{invalid'
                return httpx.Response(200,json={'id':'FIXTURE','created':0,'model':'qwen-max-fixture','object':'chat.completion',
                    'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                        'tool_calls':[{'id':'fixture','type':'function','function':{'name':'record_silver_audit','arguments':args}}]}}],
                    'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            def factory(**kwargs):return Actual(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            with patch.dict(os.environ,{'C1_PILOT_API_KEY':'SOFTWARE_ONLY'}),patch('openai.OpenAI',side_effect=factory):
                result,meta=sc.call([{'role':'user','content':'fixture'}],tag='fixture',max_tokens=256,schema=schemas.LABELS,retry_invalid_once=True)
            self.assertEqual(result,{'items':[]})
            self.assertEqual(requests[0],requests[1])
            self.assertIn('explicit_format_retry_from_sha256',meta)
            self.assertEqual(len(list((root/'malformed_cache').glob('*.json'))),1)
            self.assertEqual(len(read(root/'budget.json')['attempts']),2)

    def test_declarative_function_has_no_execution_and_decodes_actual_arguments(self):
        from research.problem_reidentification.experiment_a.silver import schemas
        from research.problem_reidentification.experiment_a.silver.api import request_options
        request,limits=request_options([{'role':'user','content':'software fixture'}],5120,schemas.LABELS)
        self.assertEqual(request['tool_choice']['function']['name'],'record_silver_audit')
        self.assertNotIn('response_format',request)
        self.assertGreater(limits['input_token_ceiling'],len('software fixture'))
        result=SilverClient.decode({'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[
            {'function':{'name':'record_silver_audit','arguments':'{"items":[]}'}}]}}]})
        self.assertEqual(result,{'items':[]})

    def test_concurrent_calls_share_one_persistent_request_ceiling(self):
        from concurrent.futures import ThreadPoolExecutor
        from openai import OpenAI as Actual
        with tempfile.TemporaryDirectory(dir=LOCAL/'silver_annotations') as name:
            sc=SilverClient(Path(name));sc.initialize(cap_cny=1,max_calls=2)
            sent=[]
            def handler(request):
                sent.append(1)
                return httpx.Response(200,json={'id':'FIXTURE','created':0,'model':'qwen-max-fixture','object':'chat.completion',
                    'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}],
                    'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            def factory(**kwargs):return Actual(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            def invoke(i):
                try:sc.call([{'role':'user','content':'fixture '+str(i)}],tag='fixture',max_tokens=128);return True
                except ValueError:return False
            with patch.dict(os.environ,{'C1_PILOT_API_KEY':'SOFTWARE_ONLY'}),patch('openai.OpenAI',side_effect=factory),ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(invoke,range(4)))
            self.assertEqual(sum(results),2)
            self.assertEqual(len(sent),2)
            self.assertEqual(len(read(Path(name)/'budget.json')['attempts']),2)

    def test_actual_sdk_sends_qwen_max_and_enforces_persistent_money_cap(self):
        with tempfile.TemporaryDirectory(dir=LOCAL/'silver_annotations') as name:
            directory=Path(name);sc=SilverClient(directory)
            sc.initialize(cap_cny=.02,max_calls=2)
            sent=[]
            def handler(request):
                sent.append(json.loads(request.content))
                return httpx.Response(200,json={'id':'FIXTURE','created':0,'model':'qwen-max-fixture','object':'chat.completion',
                    'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{"fixture":true}'}}],
                    'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            from openai import OpenAI as Actual
            def factory(**kwargs):return Actual(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            with patch.dict(os.environ,{'C1_PILOT_API_KEY':'SOFTWARE_ONLY'}),patch('openai.OpenAI',side_effect=factory):
                opts=[{'role':'user','content':'fixture'}]
                a,_=sc.call(opts,tag='fixture',max_tokens=128)
                _,meta=sc.call(opts,tag='replay',max_tokens=128)
                self.assertTrue(a['fixture']);self.assertTrue(meta['cache_hit'])
                with self.assertRaises(ValueError):sc.call([{'role':'user','content':'different'}],tag='blocked',max_tokens=8192)
            self.assertEqual(len(sent),1)
            self.assertEqual(sent[0]['model'],'qwen-max')
            self.assertNotIn('enable_thinking',sent[0])
            self.assertEqual(sent[0]['response_format'],{'type':'json_object'})
            for f in directory.rglob('*.json'):self.assertNotIn('SOFTWARE_ONLY',f.read_text(encoding='utf-8'))

    def test_failed_request_reservation_persists_and_is_not_free_retry(self):
        with tempfile.TemporaryDirectory(dir=LOCAL/'silver_annotations') as name:
            sc=SilverClient(Path(name));sc.initialize(cap_cny=1,max_calls=1)
            with patch.dict(os.environ,{'C1_PILOT_API_KEY':'SOFTWARE_ONLY'}),patch('openai.OpenAI',side_effect=RuntimeError('fixture')):
                with self.assertRaises(RuntimeError):sc.call([{'role':'user','content':'fixture'}],tag='failed',max_tokens=32)
                with self.assertRaises(ValueError):sc.call([{'role':'user','content':'fixture'}],tag='retry',max_tokens=32)
            self.assertEqual(len(read(Path(name)/'budget.json')['attempts']),1)
