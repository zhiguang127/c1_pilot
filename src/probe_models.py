"""Verify configured model identifiers and structured, tool-free execution."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from io_utils import ROOT, read_json, write_json
from llm_client import call_model, object_schema


def main():
    settings=read_json(ROOT/"config/experiment.json")["llm"]
    models=sorted({settings[k] for k in ("generator_model","judge_a_model","judge_b_model","adjudicator_model")})
    schema=object_schema({"availability":{"type":"string","enum":["ok"]}})
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending={pool.submit(call_model,"Do not use tools. Return {\"availability\":\"ok\"}. Authorized structured model availability check.",schema,model,"probe_"+model,settings):model for model in models}
        for future in as_completed(pending):
            result,metadata=future.result()
            results.append(metadata)
            print(pending[future]+": structured model call passed",flush=True)
    write_json(ROOT/"outputs/model_availability.json",results)


if __name__=="__main__": main()
