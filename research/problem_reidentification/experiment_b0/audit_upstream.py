"""Pin official checkouts and keep every acquisition attempt, without credentials."""
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
REPOS = {
    "self_refine": "madaan/self-refine", "critic": "ZethWang/CRITIC",
    "rarr": "anthonywchen/RARR", "re2": "zhiyuanc2001/RE2",
    "rerec": "jiani-huang/ReRec", "rankingshap": "MariaHeuss/RankingShap",
    "trace": "devUuung/TRACE", "pex_dpo": "lingjunzhao/PEX_consistency",
}


def main():
    out = ROOT / "local/upstream"
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, repo in REPOS.items():
        target = out / name
        cmd = ["git", "clone", "--depth", "1", "https://github.com/" + repo + ".git", str(target)]
        log = ROOT / "local" / ("clone-" + name + ".log")
        if not target.exists():
            with log.open("x", encoding="utf-8") as f:
                try:
                    p = subprocess.run(cmd, stdout=f, stderr=f, timeout=240)
                    code = p.returncode
                except subprocess.TimeoutExpired:
                    code = "TIMEOUT"
            if code != 0:
                report[name] = {"repository": repo, "clone_exit": code}
                print(name, code, flush=True)
                continue
        def git(*args):
            return subprocess.check_output(["git", "-C", str(target), *args], text=True, encoding="utf-8").strip()
        files = git("ls-files").splitlines()
        licenses = [p for p in files if Path(p).name.lower().startswith(("license", "copying"))]
        report[name] = {"repository": repo, "url": "https://github.com/" + repo,
                        "commit": git("rev-parse", "HEAD"), "tracked_files": len(files),
                        "license_files": licenses, "working_tree_clean": not git("status", "--porcelain"),
                        "acquired_at": datetime.now(timezone.utc).isoformat()}
        print(name, report[name]["commit"], licenses, flush=True)
    dest = ROOT / "results/upstream_pins.json"
    if dest.exists():
        raise ValueError("Never overwrite an earlier audit snapshot")
    dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
