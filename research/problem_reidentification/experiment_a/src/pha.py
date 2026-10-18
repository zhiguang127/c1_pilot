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


@contextlib.contextmanager
def governed_onetwo():
    """Only bridge provider transport, preserving OneTwo agent/tool execution.

    The pinned current OneTwo backend uses Responses, whereas the authorized
    endpoint and original audit adapter use Chat Completions. There are no
    synthetic model decisions: output_text comes from the actual metered reply.
    """
    from onetwo.backends import openai_api
    from types import SimpleNamespace
    old = openai_api.OpenAIAPI._responses_create
    def create(backend, messages, *, max_tokens=None, temperature=None, top_p=None, reasoning=None, tools=None, **kwargs):
        if reasoning or tools or backend.tools:
            raise ValueError("Transport bridge supports the official text ReAct loop only")
        converted = openai_api._convert_messages_to_input(messages)
        if any(not isinstance(m["content"], str) for m in converted):
            raise ValueError("Only text records are authorized in this experiment")
        options = {"model": MODEL, "messages": converted, "temperature": 0}
        if max_tokens is not None:
            options["max_tokens"] = max_tokens
        if top_p is not None:
            options["top_p"] = top_p
        response = backend._client.chat.completions.create(**options)
        choice = response.choices[0]
        if choice.finish_reason != "stop":
            raise ValueError("Incomplete official-agent model response")
        return SimpleNamespace(output_text=choice.message.content, output=[])
    openai_api.OpenAIAPI._responses_create = create
    try:
        yield
    finally:
        openai_api.OpenAIAPI._responses_create = old


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
    # Empty records still need CSV headers for the official sandbox's read_csv.
    # Column names are the author's schema; no activity/population rows are added.
    activities = ["start_time", "end_time", "activity_name", "distance", "duration", "calories", "steps", "active_zone_minutes"]
    population = ["percentile", "age", "gender", "resting_heart_rate", "heart_rate_variability", "steps",
                  "fatburn_active_zone_minutes", "cardio_active_zone_minutes", "peak_active_zone_minutes",
                  "rem_sleep_minutes", "deep_sleep_minutes", "light_sleep_minutes", "stress_management_score"]
    return {"summary": pd.DataFrame(records), "activities": pd.DataFrame(columns=activities),
            "profile": pd.DataFrame([{k: v for k, v in case["context"].items()}]), "population": pd.DataFrame(columns=population)}


@contextlib.contextmanager
def trace_tools(events):
    from pha.tools import python_sandbox as sb
    from pha.agents import phia_baseline as ph
    from pha.agents import domain_expert_agent as de
    import inspect
    original_execute, original_phia = sb.PythonSandbox.execute, ph.simple_python_executor
    original_search, original_toolbox = ph.tavily_search_func, de.DomainExpertAgent.get_llm_toolbox
    def execute(sandbox, request):
        result = original_execute(sandbox, request)
        events.append({"tool": "official_PythonSandbox.execute", "request": request.request,
                       "result": dataclasses.asdict(result), "at": now()})
        return result
    def phia(code, namespace):
        result = original_phia(code, namespace)
        events.append({"tool": "official_PHIA_python", "request": code, "result": str(result), "at": now()})
        return result
    def search(*args, **kwargs):
        result = original_search(*args, **kwargs)
        events.append({"tool": "official_PHIA_search", "request": {"args": args, "kwargs": {k:v for k,v in kwargs.items() if k != 'api_key'}},
                       "result": result, "at": now()})
        return result
    def toolbox(agent):
        def instrument(tool):
            function = tool.function
            if function is None:
                return tool
            if getattr(function, "_experiment_already_traced", False):
                return tool
            def record(args, kwargs, result):
                events.append({"tool": "official_DomainExpert_" + tool.name,
                               "request": {"args": args, "kwargs": kwargs}, "result": result, "at": now()})
            if inspect.iscoroutinefunction(function):
                async def wrapped(*args, **kwargs):
                    result = await function(*args, **kwargs)
                    record(args, kwargs, result)
                    return result
            else:
                def wrapped(*args, **kwargs):
                    result = function(*args, **kwargs)
                    record(args, kwargs, result)
                    return result
            return dataclasses.replace(tool, function=wrapped)
        return [instrument(tool) for tool in original_toolbox(agent)]
    sb.PythonSandbox.execute, ph.simple_python_executor = execute, phia
    ph.tavily_search_func, de.DomainExpertAgent.get_llm_toolbox = search, toolbox
    try:
        yield
    finally:
        sb.PythonSandbox.execute, ph.simple_python_executor = original_execute, original_phia
        ph.tavily_search_func, de.DomainExpertAgent.get_llm_toolbox = original_search, original_toolbox


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
    search._experiment_already_traced = True
    dc._experiment_already_traced = True
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


@contextlib.contextmanager
def agent_responses(events):
    """Expose partial specialist failures even if synthesis returns normal prose."""
    _, classes = modules()
    originals = []
    for label, method in (("ds", "query"), ("de", "call_agent"), ("coach", "respond")):
        cls, original = classes[label], getattr(classes[label], method)
        def wrapped(agent, *args, _fn=original, _label=label, **kwargs):
            response = _fn(agent, *args, **kwargs)
            events.append({"agent": _label, "response": str(response), "at": now()})
            return response
        originals.append((cls, method, original))
        setattr(cls, method, wrapped)
    try:
        yield
    finally:
        for cls, method, original in originals:
            setattr(cls, method, original)


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
    ds.configure(**opts, temperature=0, max_tokens=8192)
    ds.load_dataframes(frames)
    if name == "pha_ds":
        return ds
    # Official, documented free backend; Controlled mode replaces its tool
    # interface with frozen sources. No dummy Tavily credential is injected.
    de = classes["de"](search_backend="duckduckgo")
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
    events, specialists = [], []
    started = time.monotonic()
    run_name = Path(output).stem
    error_type = None
    with GovernedCalls(LOCAL / "official-smoke" / run_name, max_calls=24, max_output_tokens=8192,
                       shared_cache=LOCAL / "cache/model-responses") as calls, trace_tools(events), governed_onetwo(), agent_responses(specialists):
        try:
            agent = architecture(name, sample_frames(root), native=True)
            result = agent.query(question) if name == "pha_ds" else agent.respond(question)
        except Exception as exc:
            error_type, result = type(exc).__name__, ""
    # Native web tools, official synthetic data; never mix this output with controlled P1 evaluation.
    write(LOCAL / "official-smoke" / run_name / "output.json", {"question": question, "response": result,
          "tools": json.loads(json.dumps(events, default=str)), "specialist_responses": specialists, "error_type": error_type})
    component_errors = [s["agent"] for s in specialists if any(marker in s["response"].lower() for marker in
                       ("could not extract", "[error", "not configured", "budget exhausted"))]
    incomplete_responses = sum(e.get("finish_reason") not in (None, "stop") for e in calls.events)
    framework_error = any(marker in str(result).lower() for marker in
                          ("budget exhausted", "could not extract", "[orchestrator error", "#error#", "[error"))
    usable = (bool(str(result).strip()) and calls.summary()["llm_calls"] + calls.summary()["cached_calls"] > 0
              and len(events) > 0 and not framework_error and not component_errors and not any(marker in str(result) for marker in
                  ("[Error", "not configured", "system prompt leakage", "API key required")))
    report = {"status": "OFFICIAL_ARCHITECTURE_RETURNED_RESPONSE_PROVIDER_ADAPTED" if usable else "OFFICIAL_SMOKE_UNVALIDATED_OR_FAILED",
              "architecture": name,
              "error_type": error_type,
              "component_errors": component_errors, "incomplete_model_responses": incomplete_responses,
              "intermediate_truncation_policy": "Disclosed; passed only if official retry/debug mechanisms return complete specialist and final answers",
              "setting": "native_tools_official_synthetic_sample", "source": inventory()["pha"],
              "source_edits": False, "paper_base_model_reproduced": False, "model": MODEL,
              "question_source": "notebooks/07_phia_baseline.ipynb and 06_parallel_baseline.ipynb",
              "response_sha256": digest(result), "response_is_validated_answer": False,
              "transport_adapter": "OneTwo Responses-to-metered-ChatCompletions text bridge v2",
              "tool_calls": len(events), "duration_seconds": time.monotonic()-started, **calls.summary()}
    write(output, report)
    return report


def controlled_response(name, case, knowledge, question, events):
    modules()
    specialists = []
    with trace_tools(events), fixed_sources(knowledge, events), governed_onetwo(), agent_responses(specialists):
        agent = architecture(name, personal_frames(case))
        result = agent.query(question) if name == "pha_ds" else agent.respond(question)
    events.append({"tool": "audit_specialist_responses", "is_tool_call": False, "responses": specialists})
    return result
