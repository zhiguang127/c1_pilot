"""Original acronym domain, exact author classes, explicitly changed API backend.

Run only after the comparison process exits: the persistent ledger is protected
across threads, not across simultaneous independent Python processes.
"""
from types import SimpleNamespace
from typing import Dict, List
import pandas as pd
from .core import *


def main():
    root = LOCAL / "upstream/self_refine"
    client = Client()
    events = []
    class Wrapper:
        @staticmethod
        def call(**kw):
            text, meta = client.call(kw["prompt"], tag="native-domain:self-refine-acronym", limit=512, stop=kw.get("stop_token"),
                system="Continue the author's acronym few-shot format. Include explicit Title:, Acronym: or Scores: prefixes as in the examples; no Markdown fences.")
            events.append(meta)
            return text
        @staticmethod
        def get_first_response(text):
            return text
    base = definitions(root / "src/utils.py", ["Prompt"], {})
    env = {"Prompt": base["Prompt"], "pd": pd, "Dict": Dict, "List": List,
           "openai_api": SimpleNamespace(OpenaiAPIWrapper=Wrapper)}
    for path, name in [("task_init.py", "AcronymGenTaskInit"), ("feedback.py", "AcronymGenFeedback"),
                       ("task_iterate.py", "AcronymGenTaskIterate")]:
        definitions(root / "src/acronym" / path, [name], env)
    target = LOCAL / "native-model-smoke"
    target.mkdir(exist_ok=True)
    title = "Using language models of code for few-shot commonsense"
    initial = feedback = revised = None
    try:
        initial = env["AcronymGenTaskInit"](str(root / "data/prompt/acronym/init.jsonl"), MODEL)(title)
        feedback = env["AcronymGenFeedback"](MODEL, str(root / "data/prompt/acronym/feedback.jsonl"), max_tokens=512)(title, initial)
        # The official Iterate class writes a prompt transcript in its CWD.
        previous = Path.cwd()
        try:
            os.chdir(target)
            revised = env["AcronymGenTaskIterate"](MODEL, str(root / "data/prompt/acronym/feedback.jsonl"))({initial: (title, feedback)})
        finally:
            os.chdir(previous)
        status = "TASK_ADAPTED_NATIVE_DOMAIN_BACKEND_CHANGED"
        error = None
    except Exception as exc:
        status = "FAILED"
        error = type(exc).__name__ + ": " + str(exc)
    private = {"status": status, "initial": initial, "feedback": feedback, "revised": revised,
               "events": events, "error": error, "at": now()}
    write(target / "self_refine_acronym.json", private)
    public = {"status": status, "model": MODEL, "actual_requests": sum(not e["cache_hit"] for e in events),
              "log_sha256": sha(target / "self_refine_acronym.json"), "error": error,
              "deviations": ["Qwen-Max instead of original API model", "temperature=0", "512-token cap", "explicit completion-format system wrapper"],
              "official_classes": ["AcronymGenTaskInit", "AcronymGenFeedback", "AcronymGenTaskIterate"],
              "paper_result_reproduced": False}
    write(ROOT / "results/self_refine_native_domain.json", public)
    print(packed(public))


if __name__ == "__main__":
    main()
