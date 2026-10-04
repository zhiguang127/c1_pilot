"""Seal pre-output inputs; refuse silent edits on subsequent runs."""
import argparse
import hashlib

from io_utils import ROOT, fingerprint, read_json, read_jsonl, write_json

FILES = [
    "data/wearable_cases.jsonl", "data/knowledge_items.jsonl",
    "data/corpus_seed.json", "data/independent_corpus_review.json",
    "data/source_manifest.json", "data/corpus_verification.json",
    "config/experiment.json", "config/retrieval.json", "requirements.lock.txt",
    "docs/benchmark_design.md", "docs/data_dictionary.md",
    "docs/annotation_guideline.md", "docs/knowledge_taxonomy.md",
    "docs/EXECUTION_PROTOCOL.md", "src/build_corpus.py", "src/review_corpus.py",
    "src/case_statistics.py", "src/generate_cases.py", "src/validate_cases.py",
    "src/generate_representations.py", "src/annotate_relevance.py", "src/llm_client.py", "src/api_llm_client.py",
    "src/retrieval.py", "src/evaluate.py", "src/audit_representations.py",
    "src/failure_analysis.py",
]


def run():
    review=read_json(ROOT/"data/independent_corpus_review.json")
    if review["requires_correction"]:
        raise ValueError("Unresolved independent source review corrections")
    if review["corpus_sha256"] != fingerprint(read_jsonl(ROOT/"data/knowledge_items.jsonl")):
        raise ValueError("Source review does not cover the current corpus")
    names = FILES + sorted(str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "data/source_snapshots").glob("*.*"))
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    path=ROOT/"data/input_freeze.json"
    if path.exists():
        old=read_json(path)
        if old["file_sha256"]!=hashes:
            changed=[name for name in set(hashes)|set(old["file_sha256"]) if hashes.get(name)!=old["file_sha256"].get(name)]
            raise ValueError("Frozen inputs changed: "+str(changed))
        print("Frozen input hashes verified",flush=True)
        return old
    experiment=read_json(ROOT/"config/experiment.json")
    result={"design_revision":"design-v1","execution_revision":experiment["revision"],"freeze_date":"2026-10-03","file_sha256":hashes,"label_name":"PROVISIONAL_LLM_GOLD","no_benchmark_changes_after_results":True,"representation_generation_started_before_corpus_freeze":"Allowed because representation generation never reads corpus or labels; generation prompts were fixed before any output inspection."}
    write_json(path,result)
    print("Inputs frozen before annotation/retrieval",flush=True)
    return result


if __name__=="__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
