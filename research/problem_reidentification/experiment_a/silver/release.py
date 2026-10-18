"""Immutable private Silver release; never compatible with the human Gold reader."""
from ..src.common import ROOT, freeze, read, sha, verify, write, write_rows
from .api import SILVER
from .report import label_records
from .pipeline import canonical_source


def freeze_release():
    target=SILVER/'release-v1'
    if target.exists():
        manifest=verify(target)
        return {'release_id':manifest['release_id'],'records':manifest['records'],'human_gold':False}
    plan=read(SILVER/'plan.json');records=[]
    for scope,expected in [('smoke',5),('heldout',5*len(plan['heldout_case_ids']))]:
        rounds=label_records(scope)
        if any(len(ps)!=expected for ps in rounds.values()):
            raise ValueError('Incomplete annotation coverage; do not freeze a complete Silver release')
        for rnd,ps in rounds.items():
            records.extend({**p,'scope':scope,'round':rnd} for _,p in sorted(ps.items()))
    target.mkdir(parents=True)
    write_rows(target/'annotations.jsonl',records)
    source_records=[canonical_source(read(f)) for f in sorted((SILVER/'source_audit').glob('*.json'))]
    write_rows(target/'source_condition_audits.jsonl',source_records)
    provenance={'label_provenance':'QWEN_MAX_SILVER','gold_kind':'QWEN_MAX_SILVER',
                'human_gold':False,'independent_human_review':False,'plan_id':plan['plan_id'],
                'p1_release_id':plan['input_integrity']['p1_release_id'],'a1_release_id':plan['a1_release_id'],
                'model_requested':'qwen-max','records':len(records),
                'reference_schema_accepted_records':sum(p['accepted'] for p in records),
                'semantic_correctness_human_verified':False,
                'budget_ledger_sha256':sha(SILVER/'budget.json'),
                'underlying_label_files':{p.relative_to(SILVER).as_posix():sha(p) for scope in ['smoke','heldout']
                                          for p in sorted((SILVER/'labels'/scope).glob('*/*.json'))},
                'original_baseline_predictions':{m:sha(ROOT/'local/runs'/n/'predictions.jsonl') for m,n in plan['baseline_runs'].items()}}
    write(target/'provenance.json',provenance)
    manifest=freeze(target,['annotations.jsonl','source_condition_audits.jsonl','provenance.json'],
                    {'version':'qwen-max-silver-release-v1','label_provenance':'QWEN_MAX_SILVER','human_gold':False,
                     'records':len(records),'plan_id':plan['plan_id']})
    return {'release_id':manifest['release_id'],'records':len(records),'human_gold':False}
