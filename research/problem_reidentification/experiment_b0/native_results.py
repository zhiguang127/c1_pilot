"""Extract native results directly from immutable logs and author outputs."""
import ast
import re
import subprocess
from .core import *


def main():
    up = LOCAL / "upstream"
    trace = up / "trace"
    path = LOCAL / "rankingshap-native-v1.log"
    match = re.search(r"NATIVE_RESULT (\[.*\])", path.read_text(encoding="utf-8"))
    attribution = ast.literal_eval(match[1])
    runs = {}
    for tag, budget, edits, log in [("b0-native-smoke", 100, 2, "trace-native-v3.log"),
                                    ("b0-native-author-budget", 10000, 5, "trace-native-author-budget.log")]:
        p = trace / ("results/explain_sasrec_ml-100k_beam_targeted_r2_50_" + tag + "_seed42.json")
        x = read(p)
        runs[tag] = {"users_executed": len(x["per_user"]), "valid_counterfactuals": sum(u["valid"] for u in x["per_user"]),
                     "query_counts": [u["queries_used"] for u in x["per_user"]], "edit_counts": [u["edits"] for u in x["per_user"]],
                     "query_budget_per_user": budget, "max_edits": edits, "log_sha256": sha(LOCAL / log),
                     "native_output_sha256": sha(p), "seed": 42,
                     "metrics": {k: v if not isinstance(v, float) or math.isfinite(v) else None for k, v in x["metrics"].items()}}
    result = {"native_algorithm_scope": "minimal official original-domain execution, not full paper reproduction",
        "rankingshap": {"native_status": "NATIVE_REPRODUCED", "domain": "author synthetic talent-search notebook",
            "query": "average", "seed": 0, "log_sha256": sha(path), "feature_attributions": attribution,
            "health_status": "BLOCKED_NO_FROZEN_PRIORITY_SCORER"},
        "trace": {"native_status": "NATIVE_REPRODUCED", "dataset": "MovieLens-100K", "model": "official SASRec checkpoint",
            "checkpoint_sha256": sha(trace / "checkpoints/sasrec_ml-100k.pt"),
            "raw_zip_sha256": sha(trace / "data/raw/ml-100k.zip"), "runs": runs,
            "target": "bring-in, original rank 2..50", "health_status": "BLOCKED_NO_HEALTH_INTERACTION_MODEL",
            "scope_limit": "Same three randomly selected users, one seed, CPU instead of paper GPU; no health ranking claim"},
        "tracked_upstream_code_changes": {name: subprocess.check_output(["git", "-C", str(up / name), "diff", "--name-only"], text=True).splitlines()
            for name in read(ROOT / "results/upstream_pins.json")}}
    write(ROOT / "results/native_algorithm_runs.json", result, True)
    print(packed({"trace_author_budget": runs["b0-native-author-budget"], "rankingshap_executed": True}))


if __name__ == "__main__":
    main()
