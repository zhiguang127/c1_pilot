"""Attempt official entry points without launching unauthorised new training."""
import os
import subprocess
import sys
from .core import ROOT, LOCAL, read, write, sha, now


def main():
    commands = {
        "self_refine": ["src/acronym/run.py", "Using language models of code for few-shot commonsense"],
        "critic": ["-m", "src.program.critic", "--help"],
        "rarr": ["run_editor_sequential.py", "--help"],
        "re2": ["run_eval/run_eval_one_phase_my.py", "--help"],
        "rerec": ["scripts/predict.py", "--help"],
        "rankingshap": ["generate_feature_attribution_explanations.py", "--help"],
        "trace": ["run_explain.py", "--help"],
        "pex_dpo": ["compute_pex_score.py", "--help"],
    }
    result = {}
    for name, args in commands.items():
        target = LOCAL / "upstream" / name
        log = LOCAL / ("entrypoint-" + name + ".log")
        env = dict(os.environ, PYTHONUTF8="1", MPLBACKEND="Agg")
        # No secrets are passed to original entry points. Backend-adapted actual
        # model executions are separate, explicitly metered runs.
        for key in ("OPENAI_API_KEY", "C1_PILOT_API_KEY", "AZURE_SEARCH_KEY"):
            env.pop(key, None)
        with log.open("x", encoding="utf-8") as f:
            try:
                p = subprocess.run([sys.executable, *args], cwd=target, env=env, stdout=f, stderr=f, timeout=30)
                code = p.returncode
            except subprocess.TimeoutExpired:
                code = "TIMEOUT"
        result[name] = {"command": ["python", *args], "exit_code": code, "log_sha256": sha(log),
                        "kind": "ENTRYPOINT_ONLY_NOT_ALGORITHM_REPRODUCTION", "at": now()}
        print(name, code, flush=True)
    write(ROOT / "results/native_entrypoints.json", result)


if __name__ == "__main__":
    main()
