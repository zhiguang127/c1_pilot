import unittest
from ..report import order, relation, normalized_reference_diagnostic
from ..core import Client, decode, selected


class ReportingTests(unittest.TestCase):
    def test_tie_member_order_is_not_a_ranking_change(self):
        self.assertEqual(order({"ranking": [["a", "b"], ["c"]]}), order({"ranking": [["b", "a"], ["c"]]}))
        self.assertEqual(relation({"ranking": [["a", "b"], ["c"]]}, "a", "b"), 0)
        self.assertEqual(relation({"ranking": [["a", "b"], ["c"]]}, "a", "c"), -1)

    def test_typed_transport_does_not_repair_a_model_decision(self):
        text = '{"ranking":[["a"],["b"]]}'
        body = {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"function": {"name": "record_b0", "arguments": text}}]}}]}
        self.assertEqual(Client.content(body), text)
        body["choices"][0]["message"]["tool_calls"].append({"function": {"name": "record_b0", "arguments": text}})
        with self.assertRaises(ValueError):
            Client.content(body)

    def test_multiple_json_objects_are_not_silently_discarded(self):
        with self.assertRaises(ValueError):
            decode('{"items":[]} {"items":[]}')

    def test_format_diagnostic_preserves_values_and_does_not_mutate_output(self):
        from research.problem_reidentification.experiment_a.silver.pipeline import resolve
        case = selected()[0][0]
        ref = "stats.current.sleep_minutes.mean"
        actual, _ = resolve(case, ref)
        output = {"items": [{"evidence": [{"ref": "stats.current.metrics.sleep_minutes.mean", "value": actual + 20, "purpose": "physiology"}]}]}
        result = normalized_reference_diagnostic(output, case)
        self.assertEqual(result["format_only_references_mapped"], 1)
        self.assertEqual(result["invalid_value"], 1)
        self.assertEqual(output["items"][0]["evidence"][0]["ref"], "stats.current.metrics.sleep_minutes.mean")


if __name__ == "__main__":
    unittest.main()
