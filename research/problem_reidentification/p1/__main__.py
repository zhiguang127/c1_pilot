"""P1 CLI, stdlib only. Run python -m research.problem_reidentification.p1 --help."""
import argparse
import json
from pathlib import Path

from .annotations import adjudication_queue, analyze
from .dataset import jsonl, prepare, read_json, verify_release, write_json, write_jsonl
from .download_pmdata import download
from .packets import generate_packets, verify_packets


def main():
    parser = argparse.ArgumentParser(description="P1 real-data and independent human-review workflow")
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("download", help="Download prespecified files from original OSF")
    p.add_argument("--raw-dir", required=True)
    p = subs.add_parser("prepare", help="Import, pseudonymize and freeze a new real-data release")
    p.add_argument("--raw-dir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--key-file")
    p = subs.add_parser("verify", help="Verify release and optional blind packets")
    p.add_argument("--release", required=True)
    p.add_argument("--packets")
    p = subs.add_parser("packets", help="Generate two independent blind-review folders")
    p.add_argument("--release", required=True)
    p.add_argument("--output", required=True)
    p = subs.add_parser("collect", help="Combine one-reviewer's exported JSON cards without silently dropping duplicates")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output", required=True)
    for command in ("validate", "analyze", "adjudication-queue"):
        p = subs.add_parser(command)
        p.add_argument("--release", required=True)
        p.add_argument("--packets")
        p.add_argument("--roster")
        p.add_argument("--a")
        p.add_argument("--b")
        p.add_argument("--adjudications")
        p.add_argument("--output", required=command == "adjudication-queue")
    args = vars(parser.parse_args())
    command = args.pop("command")
    try:
        if command == "download": result = download(args["raw_dir"])
        elif command == "prepare": result = prepare(**args)
        elif command == "packets": result = generate_packets(**args)
        elif command == "collect":
            rows = []
            for path in sorted(Path(args["input_dir"]).glob("*.json")):
                record = read_json(path)
                if not isinstance(record, dict) or "case_ref" not in record:
                    raise ValueError("Input directory must contain exported case JSON files only")
                rows.append(record)
            if not rows or len({r["reviewer_id"] for r in rows}) != 1 or len({r["case_ref"] for r in rows}) != len(rows):
                raise ValueError("No exports, mixed reviewers or duplicate case exports")
            output = Path(args["output"])
            if output.exists(): raise ValueError("Collected output exists")
            output.parent.mkdir(parents=True, exist_ok=True)
            write_jsonl(output, rows)
            result = {"collected_cases": len(rows), "note": "Run validate with the real human roster next"}
        elif command == "verify":
            result = verify_packets(args["release"], args["packets"]) if args["packets"] else verify_release(args["release"])
            result = {"valid": True, "release_id": result["release_id"]}
        else:
            output = args.pop("output")
            if command == "adjudication-queue":
                args.pop("adjudications")
                result = adjudication_queue(**args, output=output)
            else:
                result = analyze(**args)
                if output:
                    path = Path(output)
                    if path.exists(): raise ValueError("Analysis output exists; choose a new version path")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    write_json(path, result)
        # Download manifests contain raw identifiers; display aggregate only.
        if command == "download": result = {"downloaded_files": sum(x["status"] == "downloaded" for x in result["files"]), "participants": len(result["participants"])}
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, "P1 validation failed: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
