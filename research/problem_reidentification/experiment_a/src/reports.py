"""Export allowlisted aggregate metadata; never export private prompts or predictions."""
from pathlib import Path
import re

from .common import LOCAL, ROOT, now, read, sha, write
from .data import audit
from .upstream import inventory

SAFE_RUN_FIELDS = ("status", "method", "cases", "participants", "corpus", "information_view",
    "query_lexical_budget", "full_context", "lexically_truncated_cases", "model_truncated_cases",
    "duration_seconds", "seconds_per_case_amortized", "llm_calls", "tool_calls", "api_cost", "formal_metrics",
    "gold_status", "input_fingerprint", "predictions", "parse_failures", "prompt_tokens", "completion_tokens")


def summarize(output):
    runs = []
    for path in sorted((LOCAL / "runs").glob("*/manifest.json")):
        manifest = read(path)
        runs.append({"run": path.parent.name, "manifest_sha256": sha(path),
                     **{k: manifest[k] for k in SAFE_RUN_FIELDS if k in manifest}})
    test_specs = {
        "experiment_a": ("tests-experiment-a-final.log", "-m unittest discover -s research/problem_reidentification/experiment_a/tests -v"),
        "p1": ("tests-p1.log", "-m unittest discover -s research/problem_reidentification/p1/tests -v"),
        "legacy_c1": ("tests-legacy.log", "-m unittest discover -s tests -v"),
    }
    tests = {}
    for name, (filename, command) in test_specs.items():
        path = LOCAL / filename
        text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        count = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
        tests[name] = {"command": command, "tests": int(count[1]) if count else None,
                       "seconds": float(count[2]) if count else None,
                       "passed": bool(count and re.search(r"^OK\s*$", text, re.M)),
                       "log_sha256": sha(path) if path.exists() else None}
    path = LOCAL / "pha-official-tests.log"
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    tests["pha_official_offline"] = {"summary": next((s for s in reversed(text.splitlines()) if "passed" in s), None),
                                      "log_sha256": sha(path) if path.exists() else None,
                                      "is_model_inference": False}
    input_audit = audit()
    report = {"generated_at": now(), "status": "PENDING_HUMAN_ANNOTATION_AND_API_CREDENTIAL",
              "input_integrity": {k: input_audit[k] for k in ("legacy_hashes_verified", "p1_release_id", "cases", "participants", "a0_pairs")},
              "official_sources": inventory(), "executed_local_runs": runs, "tests": tests,
              "formal_metrics": None, "gold_pairs": 0,
              "conclusion": "Insufficient evidence to establish success, stable failure, or need for a new algorithm"}
    write(output, report)
    return {"status": report["status"], "local_runs": len(runs), "tests": tests}
