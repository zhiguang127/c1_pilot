"""Versioned artifacts and a strict local boundary for personal records."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
P1 = ROOT.parent / "p1/data/releases/p1-v2"
LOCAL = ROOT / "local"
LABELS = ("applicable", "not_applicable", "insufficient_information")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8-sig").splitlines() if s.strip()]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def private_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(LOCAL.resolve()):
        raise ValueError("Personal records, predictions, prompts and human submissions must stay under experiment_a/local")
    return path


def write(path, value, *, overwrite=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental revision replacement.
    with path.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def write_rows(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def freeze(directory, names, metadata):
    directory = Path(directory)
    manifest = {**metadata, "files": {name: sha(directory / name) for name in sorted(names)}}
    manifest["release_id"] = digest(manifest)
    write(directory / "freeze.json", manifest)
    return manifest


def verify(directory):
    directory = Path(directory)
    manifest = read(directory / "freeze.json")
    content = {k: v for k, v in manifest.items() if k != "release_id"}
    if digest(content) != manifest["release_id"]:
        raise ValueError("Manifest identity changed")
    for name, expected in manifest["files"].items():
        target = (directory / name).resolve()
        if not target.is_relative_to(directory.resolve()) or sha(target) != expected:
            raise ValueError("Frozen file changed: " + name)
    return manifest


def credential_available():
    # Never return or serialize credential values.
    return bool(os.environ.get("C1_PILOT_API_KEY"))
