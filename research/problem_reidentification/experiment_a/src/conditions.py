"""Three-valued condition logic; no automatic conversion of source prose to AND."""
STATES = {"satisfied", "violated", "unknown", "not_applicable_to_condition"}


def aggregate(expression, judgments):
    """Evaluate a predeclared expression using Kleene logic.

    Optional conditions are retained for auditing and never gate applicability.
    A conditional rule with unknown premise stays unknown. N/A is accepted only
    for an explicitly declared optional leaf or inactive conditional branch.
    """
    op = expression.get("op")
    if op == "condition":
        state = judgments[expression["id"]]
        if state not in STATES:
            raise ValueError("Unknown condition state")
        if state == "not_applicable_to_condition":
            raise ValueError("N/A cannot bypass a required condition")
        return state
    if op == "optional":
        if judgments[expression["id"]] not in STATES:
            raise ValueError("Unknown optional condition state")
        return "satisfied"
    if op == "not":
        return {"satisfied": "violated", "violated": "satisfied", "unknown": "unknown"}[aggregate(expression["arg"], judgments)]
    if op == "if":
        premise = aggregate(expression["premise"], judgments)
        if premise == "violated":
            return "satisfied"
        if premise == "unknown":
            return "unknown"
        return aggregate(expression["then"], judgments)
    if op not in ("all", "any") or not expression.get("args"):
        raise ValueError("Nonempty all/any or explicit condition/optional/not/if required")
    values = [aggregate(arg, judgments) for arg in expression["args"]]
    if op == "all":
        return "violated" if "violated" in values else "unknown" if "unknown" in values else "satisfied"
    return "satisfied" if "satisfied" in values else "unknown" if "unknown" in values else "violated"


def applicability(expression, judgments):
    return {"satisfied": "applicable", "violated": "not_applicable", "unknown": "insufficient_information"}[aggregate(expression, judgments)]
