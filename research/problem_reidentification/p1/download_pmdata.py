"""Fetch only the prespecified PMData files from the original OSF repository.

Run with python -m research.problem_reidentification.p1.download_pmdata.
Raw participant IDs, API metadata and downloaded records stay in ignored local/.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
API = "https://api.osf.io/v2/nodes/vx4bk/files/osfstorage/"


def fetch(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "P1Research/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def listing(url):
    rows = []
    while url:
        data = json.loads(fetch(url))
        rows.extend(data["data"])
        url = data["links"]["next"]
    return rows


def folder(entry):
    return entry["relationships"]["files"]["links"]["related"]["href"]


def download(destination=ROOT / "local" / "pmdata"):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    existing = destination / "source_manifest.json"
    if existing.exists():
        manifest = json.loads(existing.read_text(encoding="utf-8"))
        for record in manifest["files"]:
            path = (destination / record["path"]).resolve()
            if not path.is_relative_to(destination.resolve()):
                raise ValueError("Unsafe cached source path")
            if record["status"] == "downloaded" and hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("Cached raw data changed; preserve it and use a new download directory")
            if record["status"] == "absent_at_source" and path.exists():
                raise ValueError("Previously absent source file appeared locally")
        return manifest  # Preserve the original download time and manifest bytes.
    plan = json.loads((ROOT / "sampling_plan.json").read_text(encoding="utf-8"))
    root = listing(API)
    dataset = next(x for x in root if x["attributes"]["name"] == "pmdata")
    participants = sorted((x for x in listing(folder(dataset))
                           if x["attributes"]["kind"] == "folder"
                           and x["attributes"]["name"].startswith("p")),
                          key=lambda x: x["attributes"]["name"])

    def participant(entry):
        name = entry["attributes"]["name"]
        dirs = listing(folder(entry))
        fitbit = next(x for x in dirs if x["attributes"]["name"] == "fitbit")
        files = {x["attributes"]["name"]: x for x in listing(folder(fitbit))}
        result = []
        for filename in plan["metrics"]:
            if filename not in files:
                result.append({"path": name + "/fitbit/" + filename, "status": "absent_at_source"})
                continue
            source = files[filename]
            target = destination / name / "fitbit" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = source["attributes"].get("extra", {}).get("hashes", {}).get("sha256")
            data = target.read_bytes() if target.exists() else fetch(source["links"]["download"])
            digest = hashlib.sha256(data).hexdigest()
            if len(data) != source["attributes"]["size"] or (expected and digest != expected):
                raise ValueError("OSF size/hash mismatch: " + name + "/" + filename)
            json.loads(data)  # reject HTML/error documents before caching
            if not target.exists():
                target.write_bytes(data)
            result.append({"path": target.relative_to(destination).as_posix(),
                           "status": "downloaded", "sha256": digest, "bytes": len(data),
                           "url": source["links"]["download"], "osf_id": source["id"],
                           "source_modified": source["attributes"]["date_modified"]})
        print(name + ": " + str(len(result)) + " source files checked", flush=True)
        return result

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = [row for group in pool.map(participant, participants) for row in group]
    license_entry = next(x for x in root if x["attributes"]["name"] == "license.txt")
    license_bytes = fetch(license_entry["links"]["download"])
    (destination / "license.txt").write_bytes(license_bytes)
    manifest = {"dataset": "PMData", "real_records": True,
                "source": "https://osf.io/vx4bk/", "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "license_text": license_bytes.decode("utf-8"),
                "sampling_plan_sha256": hashlib.sha256((ROOT / "sampling_plan.json").read_bytes()).hexdigest(),
                "participants": [x["attributes"]["name"] for x in participants], "files": files}
    (destination / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    download()
