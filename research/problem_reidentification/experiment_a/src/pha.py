"""Official PHA architectures. Native examples and controlled task layer stay separate."""
import contextlib
import dataclasses
import json
import os
from pathlib import Path
import sys
import time

from .common import LOCAL, ROOT, digest, now, read, write
from .transport import GovernedCalls, MODEL
from .upstream import checkout, inventory, versions


def modules():
    root = checkout("pha") / "personal_health_agent"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from pha.agents import DataScienceAgent, DomainExpertAgent, HealthCoachAgent
    from pha.agents import PHIABaseline, ParallelMultiAgentBaseline, MultiAgentOrchestrator
    from pha.agents import is_react_available
    if not is_react_available():
        raise RuntimeError("OneTwo ReAct unavailable; fallback is not an official architecture reproduction")
    return root, {"ds": DataScienceAgent, "de": DomainExpertAgent, "coach": HealthCoachAgent,
                  "phia": PHIABaseline, "pha_parallel": ParallelMultiAgentBaseline, "pha_orchestrator": MultiAgentOrchestrator}


def sample_frames(root):
    import pandas as pd
    return {name: pd.read_csv(root / "data/sample" / filename) for name, filename in
            (("summary", "summary.csv"), ("activities", "activities.csv"),
             ("profile", "profile.csv"), ("population", "population_percentiles.csv"))}


def personal_frames(case):
    """Retain source names and quality alongside conventional PHA aliases.

    No steps, HRV, stage minutes, activity episodes or individual demographics
    are manufactured. The date coordinate is explicitly artificial and preserves
    the published relative weekday; original dates cannot be reconstructed here.
    """
    import pandas as pd
    records = []
    anchor = pd.Timestamp("2000-01-03") + pd.Timedelta(days=case["days"][0]["weekday"]-1)
    for day in case["days"]:
        m = day["metrics"]
        row = {"date": anchor + pd.Timedelta(days=day["day"]-1), "relative_day": day["day"],
               "weekday": day["weekday"], "phase": day["phase"], **m,
               "quality_flags": ";".join(day["quality_flags"]),
               "sleep_duration": m["sleep_minutes"], "sleep_duration_minutes": m["sleep_minutes"],
               "resting_heart_rate": m["resting_heart_rate_bpm"] if m["resting_heart_rate_bpm"] != 0 else None,
               "resting_heart_rate_bpm_usable": m["resting_heart_rate_bpm"] if m["resting_heart_rate_bpm"] != 0 else None}
        row["datetime"] = row["date"]
        for clock_field, column, offset in (("sleep_start_clock", "bed_time", m["sleep_start_day_offset"]),
                                             ("sleep_end_clock", "wake_up_time", 0)):
            row[column] = (row["date"] + pd.Timedelta(days=offset) + pd.to_timedelta(m[clock_field])
                           if m[clock_field] is not None and offset is not None else pd.NaT)
        records.append(row)
    return {"summary": pd.DataFrame(records), "activities": pd.DataFrame(),
            "profile": pd.DataFrame([{k: v for k, v in case["context"].items()}]), "population": pd.DataFrame()}


@contextlib.contextmanager
def trace_tools(events):
    from pha.tools import python_sandbox as sb
    from pha.agents import phia_baseline as ph
    original_execute, original_phia = sb.PythonSandbox.execute, ph.simple_python_executor
    def execute(sandbox, request):
        result = original_execute(sandbox, request)
        events.append({"tool": "official_PythonSandbox.execute", "request": request.request,
                       "result": dataclasses.asdict(result), "at": now()})
        return result
    def phia(code, namespace):
        result = original_phia(code, namespace)
        events.append({"tool": "official_PHIA_python", "request": code, "result": str(result), "at": now()})
        return result
    sb.PythonSandbox.execute, ph.simple_python_executor = execute, phia
    try:
        yield
    finally:
        sb.PythonSandbox.execute, ph.simple_python_executor = original_execute, original_phia


@contextlib.contextmanager
def fixed_sources(knowledge, events):
    """Runtime tool-interface adapter; original agent loops and tools remain official."""
    from onetwo.stdlib.tool_use import llm_tool_use
    from pha.agents import domain_expert_agent as de
    from pha.agents import phia_baseline as ph
    old_search = de.DomainExpertAgent._setup_search_tool
    old_dc = de.DomainExpertAgent._setup_datacommons_tool
    old_phia = ph.tavily_search_func
    def search(query, **kwargs):
        events.append({"tool": "controlled_frozen_source_search", "request": str(query), "at": now(),
                       "source_ids": [k["id"] for k in knowledge]})
        return ([k["source_url"] for k in knowledge], [k["title"] + ": " + k["content"] for k in knowledge])
    def dc(query):
        events.append({"tool": "controlled_datacommons_unavailable", "request": str(query), "at": now()})
        return {"status": "unavailable_in_controlled_setting", "reason": "No population data imported; do not invent a comparison"}
    de.DomainExpertAgent._setup_search_tool = lambda self: llm_tool_use.Tool(
        name="search", function=search, description="Search the fixed supplied source set. No live internet.")
    de.DomainExpertAgent._setup_datacommons_tool = lambda self: llm_tool_use.Tool(
        name="datacommons_natural_language_query", function=dc, description="Population data unavailable in this setting.")
    ph.tavily_search_func = search
    try:
        yield
    finally:
        de.DomainExpertAgent._setup_search_tool, de.DomainExpertAgent._setup_datacommons_tool = old_search, old_dc
        ph.tavily_search_func = old_phia


def architecture(name, frames, *, native=False):
    root, classes = modules()
    key = os.environ.get("C1_PILOT_API_KEY")
    if not key:
        raise ValueError("C1_PILOT_API_KEY missing")
    opts = {"api_key": key, "provider": "openai", "model_name": MODEL}
    if name == "phia":
        agent = classes[name](few_shot_dir=str(root / "few_shots/phia"))
        agent.configure(**opts)
        agent.load_data(frames["summary"], frames["activities"], frames["profile"])
        return agent
    ds = classes["ds"]()
    ds.configure(**opts, temperature=0, max_tokens=2048)
    ds.load_dataframes(frames)
    if name == "pha_ds":
        return ds
    de = classes["de"]()
    de.get_agent(**opts, temperature=0)
    de.set_user_health_data("Profile and daily records:\n" + frames["profile"].to_json() + "\n" + frames["summary"].to_json(date_format="iso"))
    coach = classes["coach"](simple_mode=True)
    coach.configure(**opts)
    agent = classes[name]()
    agent.configure(**opts)
    agent.set_agents(data_science_agent=ds, domain_expert_agent=de, health_coach_agent=coach)
    return agent


def offline_check(output):
    root, classes = modules()
    from pha.agents.phia_baseline import simple_python_executor
    frames = sample_frames(root)
    source = "print(summary_df.select_dtypes(include='number').mean().head(3).to_dict())"
    result = simple_python_executor(source, {"summary_df": frames["summary"]})
    report = {"status": "OFFICIAL_IMPORT_AND_COMPUTATION_PASSED_LLM_NOT_RUN", "source": inventory()["pha"],
              "architectures_imported": ["phia", "pha_parallel", "pha_orchestrator"],
              "actual_tool": "pha.agents.phia_baseline.simple_python_executor", "code": source,
              "result": str(result), "synthetic_official_sample": True,
              "model_inference": False, "tool_calls": 1, "runtime": versions()}
    write(output, report)
    return report


def native_smoke(name, output):
    root, _ = modules()
    question = "How has my sleep been over the past two weeks? Am I getting enough deep sleep?"
    events = []
    started = time.monotonic()
    with GovernedCalls(LOCAL / "official-smoke" / name, max_calls=12, max_output_tokens=2048,
                       shared_cache=LOCAL / "cache/model-responses") as calls, trace_tools(events):
        agent = architecture(name, sample_frames(root), native=True)
        result = agent.respond(question)
    # Native web tools, official synthetic data; never mix this output with controlled P1 evaluation.
    write(LOCAL / "official-smoke" / name / "output.json", {"question": question, "response": result,
          "tools": json.loads(json.dumps(events, default=str))})
    usable = (bool(str(result).strip()) and calls.summary()["llm_calls"] + calls.summary()["cached_calls"] > 0
              and len(events) > 0 and not any(marker in str(result) for marker in
                  ("[Error", "not configured", "system prompt leakage", "API key required")))
    report = {"status": "OFFICIAL_ARCHITECTURE_RETURNED_RESPONSE_PROVIDER_ADAPTED" if usable else "OFFICIAL_SMOKE_UNVALIDATED_OR_FAILED",
              "architecture": name,
              "setting": "native_tools_official_synthetic_sample", "source": inventory()["pha"],
              "source_edits": False, "paper_base_model_reproduced": False, "model": MODEL,
              "question_source": "notebooks/07_phia_baseline.ipynb and 06_parallel_baseline.ipynb",
              "response_sha256": digest(result), "response_is_validated_answer": False,
              "tool_calls": len(events), "duration_seconds": time.monotonic()-started, **calls.summary()}
    write(output, report)
    return report


def controlled_response(name, case, knowledge, question, events):
    with trace_tools(events), fixed_sources(knowledge, events):
        agent = architecture(name, personal_frames(case))
        return agent.query(question) if name == "pha_ds" else agent.respond(question)
