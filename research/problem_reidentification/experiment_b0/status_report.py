"""Machine-readable separation of native reproduction and health adaptation."""
from .core import *


def main():
    x = read(ROOT / "results/comparison.json")
    pins = read(ROOT / "results/upstream_pins.json")
    mapping = {"self_refine": "B3_self_refine", "critic": "B4_critic", "rarr": "B5_rarr_explanation_only", "re2": "B2_re2_style"}
    rows = {}
    for name, pin in pins.items():
        native = "NATIVE_REPRODUCED" if name in ("rankingshap", "trace") else "BLOCKED"
        if name == "self_refine" and (ROOT / "results/self_refine_native_domain.json").exists():
            sr = read(ROOT / "results/self_refine_native_domain.json")
            if sr["status"] == "TASK_ADAPTED_NATIVE_DOMAIN_BACKEND_CHANGED":
                native = "TASK_ADAPTED"
        method = mapping.get(name)
        v = x["panels"]["main"].get(method, {})
        health = "PAPER_INSPIRED" if name == "re2" else "TASK_ADAPTED" if method and v.get("valid_output_windows", 0) else "BLOCKED"
        rows[name] = {"repository": pin["url"], "commit": pin["commit"], "native_status": native,
            "health_status": health, "health_arm": method, "planned_health_windows": 16 if method else 0,
            "health_accepted_windows": v.get("valid_output_windows", 0), "health_execution_status_counts": v.get("status_counts", {}),
            "complete_paper_result_reproduction": False, "health_decision_accuracy": None}
    value = {"methods": rows, "execution_status": x["status"], "human_gold": False,
        "native_scope": "NATIVE_REPRODUCED means official minimal original-domain algorithm executed; not paper metrics across datasets",
        "re2_warning": "B2 is RE2-style Reason-then-Recommend Prompting; original SFT/GRPO model not executed",
        "rarr_warning": "Original author generation/gate/editor functions executed with task/backend/source adapter and explanation-only decision lock; original web/passageranker not reproduced",
        "recpie": {"status": "BLOCKED", "role": "RELATED_WORK_AND_FUTURE_TRAINING_CANDIDATE", "credible_official_code_located": False, "reproduced": False}}
    write(ROOT / "results/baseline_status.json", value, True)
    print(packed({name: [r["native_status"], r["health_status"]] for name, r in rows.items()}))


if __name__ == "__main__":
    main()
