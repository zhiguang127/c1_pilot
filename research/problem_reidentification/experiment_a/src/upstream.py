"""Audit pristine official checkouts and execute the actual MedCPT README examples."""
import contextlib
import importlib.util
import io
import platform
import re
import subprocess
import time
from importlib.metadata import distributions
from pathlib import Path

from .common import ROOT, LOCAL, now, read, sha, write

PROJECTS = {
    "medcpt": {"directory": "MedCPT", "url": "https://github.com/ncbi/MedCPT",
               "commit": "11e129be74102c98d16a11c310b0b5ce74c1db5e", "license": "LICENSE"},
    "trialgpt": {"directory": "TrialGPT", "url": "https://github.com/ncbi-nlp/TrialGPT",
                 "commit": "1b3242cd50c153a9c324661d4a0bd94fc68a4226", "license": "LICENSE"},
    "pha": {"directory": "consumer-health-research", "url": "https://github.com/Google-Health/consumer-health-research",
            "commit": "3e9d1e4877a54cf81ce8ef34085006952dd19601", "license": "personal_health_agent/LICENSE.txt"},
}


def checkout(name):
    spec = PROJECTS[name]
    path = LOCAL / "upstream" / spec["directory"]
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    changed = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    if actual != spec["commit"] or changed:
        raise ValueError("Official source must be pristine and pinned: " + name)
    return path


def inventory():
    output = {}
    for name, spec in PROJECTS.items():
        path = checkout(name)
        output[name] = {**spec, "license_sha256": sha(path / spec["license"]), "source_modified": False}
    return output


def versions():
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": dict(sorted((d.metadata["Name"], d.version) for d in distributions()))}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def download_medcpt():
    from huggingface_hub import HfApi, snapshot_download
    existing = LOCAL / "medcpt-models.json"
    if existing.exists():
        models = read(existing)
        for model in models.values():
            if sha(Path(model["path"]) / model["weight_file"]) != model["weight_sha256"]:
                raise ValueError("Cached official model weight changed")
        return {k: {f: v for f, v in model.items() if f != "path"} for k, model in models.items()}
    models = {}
    for suffix in ("Query-Encoder", "Article-Encoder", "Cross-Encoder"):
        name = "ncbi/MedCPT-" + suffix
        info = HfApi().model_info(name)
        available = {s.rfilename for s in info.siblings}
        weights = "model.safetensors" if "model.safetensors" in available else "pytorch_model.bin"
        path = snapshot_download(name, revision=info.sha, cache_dir=str(LOCAL / "hf"),
                                 allow_patterns=["config.json", "tokenizer*", "vocab.txt", "special_tokens_map.json", weights])
        models[suffix] = {"model": name, "revision": info.sha, "path": str(Path(path).resolve()),
                          "weight_file": weights, "weight_sha256": sha(Path(path) / weights),
                          "license": (info.cardData or {}).get("license", "not_declared_in_card")}
    write(LOCAL / "medcpt-models.json", models)
    return {k: {f: v for f, v in model.items() if f != "path"} for k, model in models.items()}


def medcpt_smoke(output):
    import torch
    from transformers import AutoModel, AutoTokenizer, AutoModelForSequenceClassification
    root = checkout("medcpt")
    text = (root / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```python\s*\n(.*?)```", text, re.S)
    examples = []
    models = read(LOCAL / "medcpt-models.json")
    # Redirect only pretrained loading to the exact downloaded immutable snapshots.
    # Example source and its data stay byte-for-byte unchanged.
    original = {cls: cls.from_pretrained for cls in (AutoModel, AutoTokenizer, AutoModelForSequenceClassification)}
    def loader(fn):
        def load(name, *args, **kwargs):
            suffix = str(name).removeprefix("ncbi/MedCPT-")
            return fn(models[suffix]["path"], *args, **kwargs)
        return load
    started = time.monotonic()
    try:
        for cls, fn in original.items():
            cls.from_pretrained = loader(fn)
        for suffix in models:
            candidates = [b for b in blocks if 'from_pretrained("ncbi/MedCPT-' + suffix + '")' in b]
            # README has query examples in multiple sections: choose the stand-alone encoding example.
            code = next(b for b in candidates if "index.search" not in b)
            namespace, log = {}, io.StringIO()
            with contextlib.redirect_stdout(log):
                exec(compile(code, str(root / "README.md"), "exec"), namespace)
            tensor = namespace["logits"] if "logits" in namespace else namespace["embeds"]
            if not torch.isfinite(tensor).all():
                raise ValueError("Nonfinite official output")
            examples.append({"example": suffix, "source_sha256": __import__("hashlib").sha256(code.encode()).hexdigest(),
                             "input": namespace.get("queries", namespace.get("articles")),
                             "shape": list(tensor.shape), "stdout": log.getvalue(),
                             "values": tensor.tolist() if tensor.ndim == 1 else tensor[:, :8].tolist()})
    finally:
        for cls, fn in original.items():
            cls.from_pretrained = fn
    result = {"status": "OFFICIAL_README_INFERENCE_PASSED_COMPATIBLE_ENV", "at": now(),
              "strict_historical_environment": False, "source": inventory()["medcpt"],
              "runtime": versions(), "examples": examples, "duration_seconds": time.monotonic() - started,
              "models": {k: {f: v for f, v in model.items() if f != "path"} for k, model in models.items()}}
    write(output, result)
    return {"status": result["status"], "examples": len(examples)}
