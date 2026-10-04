"""Resume the complete already-authorized synthetic pilot using frozen inputs."""
import argparse
import os
import subprocess
import sys

from io_utils import ROOT


def command(script, *arguments):
    print("Running "+script,flush=True)
    subprocess.run([sys.executable,str(ROOT/"src"/script),*arguments],cwd=ROOT,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    stages=["source_review","freeze","representations","annotation","retrieval","evaluation","audit","analysis","assessment","reports","validation"]
    parser.add_argument("--from-stage",choices=stages,default="source_review")
    parser.add_argument("--through-stage",choices=stages,default="validation")
    args=parser.parse_args()
    os.environ.setdefault("HF_HOME",str(ROOT/".cache/huggingface"))
    if stages.index(args.from_stage)>stages.index(args.through_stage):
        parser.error("from-stage must not follow through-stage")
    selected=stages[stages.index(args.from_stage):stages.index(args.through_stage)+1]
    if "source_review" in selected:
        command("validate_cases.py")
        command("build_corpus.py","--offline")
        command("review_corpus.py")
    command("freeze_inputs.py")
    common=["--cases","data/wearable_cases.jsonl","--corpus","data/knowledge_items.jsonl","--labels","data/relevance_labels_provisional.csv"]
    if "representations" in selected: command("generate_representations.py")
    if "annotation" in selected: command("annotate_relevance.py")
    if "retrieval" in selected: command("retrieval.py","--corpus","data/knowledge_items.jsonl","--representations","outputs/representations/representations.jsonl","--config","config/retrieval.json","--output-dir","outputs/retrieval")
    if "evaluation" in selected: command("evaluate.py",*common,"--retrieval-dir","outputs/retrieval","--output-dir","outputs/metrics")
    if "audit" in selected: command("audit_representations.py")
    if "analysis" in selected:
        command("failure_analysis.py",*common,"--representations","outputs/representations/representations.jsonl","--retrieval-dir","outputs/retrieval","--output-dir","outputs/case_analysis")
    if "assessment" in selected:
        command("assess_hypothesis.py")
    if "reports" in selected:
        command("build_reports.py")
    if "validation" in selected:
        command("validate_pilot.py")


if __name__=="__main__": main()
