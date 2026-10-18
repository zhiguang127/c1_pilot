"""Reviewable recipes for original-domain CPU algorithm smoke runs."""
import argparse
import subprocess
import sys
from .core import *


def main():
    p = argparse.ArgumentParser()
    p.add_argument("project", choices=["rankingshap", "trace", "trace-data"])
    p.add_argument("--run-id", required=True)
    a = p.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", a.run_id):
        raise ValueError("Simple run ID required")
    source = LOCAL / "upstream" / ("trace" if a.project.startswith("trace") else "rankingshap")
    dest = LOCAL / "native-replays" / a.run_id
    dest.mkdir(parents=True, exist_ok=False)
    if a.project == "rankingshap":
        nb = read(source / "synthetic_talent_search_case_study.ipynb")
        code = "import sys,random\nimport numpy as np\nrandom.seed(0);np.random.seed(0)\nsys.path.insert(0," + repr(str(source)) + ")\n"
        code += "\n".join("".join(c["source"]) for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code" and i <= 22)
        code += '\nfor e in explainers:\n if type(e).__name__ == "RankingShap":\n  a,b=e.get_query_explanation(queries["average"],"average")\n  print("NATIVE_RESULT",b.explanation)\n'
        script = dest / "official_notebook_cells.py"
        script.write_text(code, encoding="utf-8", newline="\n")
        command = [sys.executable, str(script)]
    elif a.project == "trace-data":
        command = [sys.executable, "-m", "data.preprocess", "--dataset", "ml-100k"]
    else:
        command = [sys.executable, "run_explain.py", "model.name=sasrec", "data.dataset=ml-100k", "training.device=cpu",
            "explainer.name=beam", "targeted.enabled=true", "targeted.constraint=bring_in", "targeted.rank_min=2", "targeted.rank_max=50",
            "evaluation.n_users=3", "evaluation.n_seeds=1", "explainer.query_budget=10000", "explainer.max_edits=5",
            "beam.candidate_strategy=pacer_lite", "beam.position_strategy=influence", "beam.beam_width=5", "beam.k_context=6",
            "beam.k_target_nn=3", "beam.k_local_nn=3", "beam.pacer_shortlist_size=12", "--tag", a.run_id]
    with (dest / "execution.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=source, stdout=log, stderr=log,
                     env=dict(os.environ, PYTHONUTF8="1", MPLBACKEND="Agg"), timeout=600)
    write(dest / "metadata.json", {"command": command, "exit": result.returncode, "log_sha256": sha(dest / "execution.log"), "at": now()})
    print(a.project, result.returncode, str(dest))


if __name__ == "__main__":
    main()
