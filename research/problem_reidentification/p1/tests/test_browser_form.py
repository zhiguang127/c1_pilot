"""Optional browser acceptance test; FABRICATED FIXTURE ONLY, never human data."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from research.problem_reidentification.p1 import annotations as ann
from research.problem_reidentification.p1 import dataset as ds
from research.problem_reidentification.p1.packets import generate_packets, verify_packets
from research.problem_reidentification.p1.tests.test_p1 import fixture_case, fixture_knowledge, fixture_release


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional Playwright package is not installed")
class BrowserFormTest(unittest.TestCase):
    def test_offline_form_exports_a_valid_annotation(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True, channel="msedge" if os.name == "nt" else None)
            except Exception as exc:
                self.skipTest("Optional browser unavailable: " + str(exc).splitlines()[0])
            try:
                root = Path(tmp); release = root / "release"; fixture_release(release)
                packets = root / "packets"; generate_packets(release, packets)
                assignments = verify_packets(release, packets)
                page = browser.new_page(accept_downloads=True)
                errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto((packets / "A/CASE-001.html").as_uri())
                self.assertEqual(42, page.locator("tbody tr").count())
                self.assertIn("context.symptoms: 未知（null）", page.locator("body").inner_text())
                refs = ["C1", "C2", "C3"]
                for ref in refs:
                    page.locator("#" + ref + "-applicability").select_option("applicable")
                    page.locator("#" + ref + "-observations").fill("d29.sleep_minutes")
                    page.locator("#" + ref + "-conditions").fill(ref + ".observable_conditions.0")
                    page.locator("#" + ref + "-rationale").fill("FABRICATED TEST FIXTURE ONLY")
                self.assertEqual(3, page.locator("#pairs-form fieldset:visible").count())
                for left, right in (("C1", "C2"), ("C1", "C3"), ("C2", "C3")):
                    prefix = "#pair-" + left + "-" + right
                    page.locator(prefix + "-relation").select_option("tie")
                    page.locator(prefix + "-observations").fill("d29.sleep_minutes")
                    page.locator(prefix + "-conditions").fill(left + ".observable_conditions.0,\n" + right + ".observable_conditions.0")
                    page.locator(prefix + "-rationale").fill("FABRICATED TEST FIXTURE ONLY")
                page.locator("#decision-priority").select_option("none")
                page.locator("#decision-top").select_option("tied_best")
                for ref in refs: page.locator('#decision-best input[value="' + ref + '"]').check()
                page.locator("#decision-observations").fill("d29.sleep_minutes")
                page.locator("#decision-conditions").fill("C1.observable_conditions.0")
                page.locator("#decision-rationale").fill("FABRICATED TEST FIXTURE ONLY")
                page.locator('#decision-reasons input[value="reasonable_tie"]').check()
                page.locator("#human-attestation").check()
                with page.expect_download() as saved:
                    page.locator("#export-annotation").click()
                path = root / "test-only-export.json"; saved.value.save_as(path)
                record = json.loads(path.read_text(encoding="utf-8"))
                mapping = assignments["reviewers"]["A"]["CASE-001"]["candidates"]
                ann.validate_record(record, fixture_case(), mapping, fixture_knowledge(), assignments["release_id"], "A")
                self.assertEqual([], errors)
            finally:
                browser.close()


if __name__ == "__main__": unittest.main()
