"""Build the source-grounded pilot corpus; fail closed on unsupported anchors.

Source snapshots and support anchors establish reproducible source access. They
do not constitute clinical expert review or demonstrate that advice is correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
ACCESS_DATE = "2026-10-03"
SOURCES = {
    "cdc_sleep": ("CDC", "About Sleep", "https://www.cdc.gov/sleep/about/", "2024-05-15"),
    "nhlbi_habits": ("NIH / NHLBI", "Healthy Sleep Habits", "https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits", "2022-03-24"),
    "nhlbi_enough": ("NIH / NHLBI", "How Much Sleep Is Enough", "https://www.nhlbi.nih.gov/health/sleep-deprivation/how-much-sleep", "2022-03-24"),
    "nhlbi_definition": ("NIH / NHLBI", "What Are Sleep Deprivation and Deficiency?", "https://www.nhlbi.nih.gov/health/sleep-deprivation", "2022-03-24"),
    "nhlbi_effects": ("NIH / NHLBI", "How Sleep Affects Your Health", "https://www.nhlbi.nih.gov/health/sleep-deprivation/health-effects", "2022-06-15"),
    "nhlbi_diagnosis": ("NIH / NHLBI", "Diagnosis", "https://www.nhlbi.nih.gov/health/sleep-deprivation/diagnosis", None),
    "nhs_insomnia": ("NHS", "Insomnia", "https://www.nhs.uk/conditions/insomnia/", "2024-03-19"),
    "nhs_jetlag": ("NHS", "Jet lag", "https://www.nhs.uk/conditions/jet-lag/", "2023-05-31"),
    "cdc_adults": ("CDC", "Adult Activity: An Overview", "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html", "2023-12-20"),
    "cdc_intensity": ("CDC", "How to Measure Physical Activity Intensity", "https://www.cdc.gov/physical-activity-basics/measuring/index.html", "2025-12-04"),
    "cdc_adding": ("CDC", "Adding Physical Activity as an Adult", "https://www.cdc.gov/physical-activity-basics/adding-adults/index.html", "2025-12-04"),
    "cdc_start": ("CDC", "Steps for Getting Started With Physical Activity", "https://www.cdc.gov/healthy-weight-growth/physical-activity/getting-started.html", None),
    "cdc_benefits": ("CDC", "Benefits of Physical Activity", "https://www.cdc.gov/physical-activity-basics/benefits/index.html", "2025-12-04"),
    "cdc_work_sleep": ("CDC / NIOSH", "Getting Exercise", "https://archive.cdc.gov/www_cdc_gov/niosh/emres/longhourstraining/gettingexercise.html", None),
    "nhs_sit": ("NHS", "Why we should sit less", "https://www.nhs.uk/live-well/exercise/why-sitting-too-much-is-bad-for-us/", None),
    "nhs_benefits": ("NHS", "Benefits of exercise", "https://www.nhs.uk/live-well/exercise/exercise-health-benefits/", None),
    "nhs_london_sit": ("NHS / MyHealth London", "Stand up for yourself", "https://www.myhealthlondon.nhs.uk/be-healthier/move-more/stand-up-for-yourself/", None),
    "nhs_adult_guidelines": ("NHS", "Physical activity guidelines for adults aged 19 to 64", "https://www.nhs.uk/live-well/exercise/physical-activity-guidelines-for-adults-aged-19-to-64/", None),
    "medline_fitness": ("NIH / MedlinePlus", "Definitions of Health Terms: Fitness", "https://medlineplus.gov/healthdefinitions/fitnessdefinitions.html", None),
    "medline_exercise": ("NIH / MedlinePlus", "How Much Exercise Do I Need?", "https://medlineplus.gov/howmuchexercisedoineed.html", None),
    "aha_hr": ("American Heart Association", "All About Heart Rate", "https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse", None),
    "google_hr": ("Google Health / Fitbit", "Track your heart rate with your Pixel Watch or Fitbit device", "https://support.google.com/googlehealth/answer/14237938?hl=en", None),
    "google_vitals": ("Google Health / Fitbit", "Track your vitals in the Google Health app", "https://support.google.com/googlehealth/answer/14236917?hl=en", None),
    "google_sleep": ("Google Health / Fitbit", "Track sleep with Google Health", "https://support.google.com/googlehealth/answer/14236407?hl=en", None),
    "google_stages": ("Google Health / Fitbit", "Learn about Google Health sleep stages", "https://support.google.com/googlehealth/answer/14236712?hl=en", None),
    "google_activity": ("Google Health / Fitbit", "How does my Fitbit device calculate my daily activity?", "https://support.google.com/googlehealth/answer/14237111?hl=en", None),
}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        elif tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "div"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return "\n".join(re.sub(r"\s+", " ", line).strip() for line in "".join(self.parts).splitlines() if line.strip())


def normalized(text):
    return re.sub(r"\s+", " ", text).casefold()


def fetch_sources(refresh=False, offline=False):
    directory = ROOT / "data" / "source_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    old_path = ROOT / "data" / "source_manifest.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
    manifest = {}
    session = requests.Session()
    for key, (publisher, title, url, published) in SOURCES.items():
        raw_path, text_path = directory / f"{key}.html", directory / f"{key}.txt"
        if raw_path.exists() and text_path.exists() and not refresh:
            record = old.get(key, {})
            record.update({"publisher": publisher, "title": title, "source_url": url})
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != record.get("html_sha256"):
                raise ValueError(f"Cached HTML hash changed for {key}")
            if hashlib.sha256(text_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest() != record.get("text_sha256"):
                raise ValueError(f"Cached text hash changed for {key}")
            manifest[key] = record
            continue
        if offline:
            manifest[key] = old.get(key, {"publisher": publisher, "title": title,
                                         "source_url": url, "status": "unavailable",
                                         "error": "No cached source; offline mode"})
            continue
        try:
            response = session.get(url, timeout=40)
            if key == "cdc_sleep" and response.status_code in {403, 404}:
                response = session.get("https://www.cdc.gov/sleep/about/index.html?source=c1pilot", timeout=40)
            response.raise_for_status()
            response.encoding = "utf-8"
            if "text/html" not in response.headers.get("Content-Type", ""):
                raise ValueError("Expected an HTML public educational page")
            parser = TextExtractor()
            parser.feed(response.text)
            extracted = parser.text()
            if len(extracted) < 300:
                raise ValueError("Page content is suspiciously short")
            raw_path.write_bytes(response.content)
            text_path.write_text(extracted, encoding="utf-8")
            manifest[key] = {
                "publisher": publisher, "title": title, "source_url": url,
                "resolved_url": response.url, "http_status": response.status_code,
                "source_accessed_on": ACCESS_DATE,
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_published_or_reviewed_on": published,
                "html_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
                "text_path": str(text_path.relative_to(ROOT)).replace("\\", "/"),
                "html_sha256": hashlib.sha256(response.content).hexdigest(),
                "text_sha256": hashlib.sha256(extracted.encode()).hexdigest(),
                "status": "fetched",
            }
            print(f"fetched {key}: {len(extracted)} characters")
        except (requests.RequestException, ValueError) as exc:
            manifest[key] = {"publisher": publisher, "title": title, "source_url": url,
                             "status": "unavailable", "error": str(exc), "source_accessed_on": ACCESS_DATE}
            print(f"unavailable {key}: {type(exc).__name__}")
    old_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def build(manifest):
    seed = json.loads((ROOT / "data" / "corpus_seed.json").read_text(encoding="utf-8"))
    items, checks, review_input = [], [], []
    for index, entry in enumerate(seed, 1):
        key = entry["source_key"]
        source = manifest[key]
        if source["status"] != "fetched":
            raise ValueError(f"K{index:03d}: unavailable source {key}")
        text = (ROOT / source["text_path"]).read_text(encoding="utf-8")
        anchors = [entry["support_anchor"], *entry.get("support_anchors", [])]
        for anchor in anchors:
            if normalized(anchor) not in normalized(text):
                raise ValueError(f"K{index:03d}: source anchor not found in {key}: {anchor}")
        locator = entry["source_locator"] + "; text anchors: " + " | ".join(anchors)
        item = {
            "schema_version": "1.0", "id": f"K{index:03d}", "status": "verified",
            "domain": entry["domain"], "title": entry["title"], "content": entry["content"],
            "source": source["publisher"], "source_url": source["source_url"],
            "source_locator": locator, "source_accessed_on": source["source_accessed_on"],
            "language": "en", "keywords": entry.get("keywords", []),
            "applicability": {
                "population": entry.get("population", ["Adults"]),
                "observable_conditions": entry["observable_conditions"],
                "required_context": entry.get("required_context", []),
                "non_applicable_conditions": entry.get("non_applicable_conditions", []),
            },
            "provenance": {
                "content_revision": "source-grounded-pilot-v2",
                "editorial_status": "reviewed",
                "source_published_on": None,
                "license_note": "Independent short paraphrase. Source access and support reviewed by LLM editor, not a human clinician; see CORPUS_AUDIT.md. Source snapshot retained locally for reproducibility, not indexed or distributed as corpus content.",
            },
        }
        items.append(item)
        checks.append({"knowledge_id": item["id"], "source_key": key,
                       "source_text_sha256": source["text_sha256"],
                       "support_anchor_found": True,
                       "support_anchors_found": len(anchors),
                       "reviewer": "source-corpus-LLM-editor", "review_kind": "source_support_and_applicability",
                       "human_review": False})
        canonical_text = re.sub(r"\s+", " ", text)
        contexts = []
        for anchor in anchors:
            support_position = normalized(text).index(normalized(anchor))
            contexts.append(canonical_text[max(0, support_position - 700):support_position + len(anchor) + 1900])
        review_input.append({"knowledge_item": item,
                             "source_text_sha256": source["text_sha256"],
                             "source_context": "\n[additional same-source context]\n".join(contexts),
                             "full_source_text_path": source["text_path"]})
    expected = {"sleep_duration": 16, "sleep_timing": 16, "temporary_variation": 8,
                "daily_activity": 16, "low_movement": 12, "activity_sleep_context": 8,
                "personal_monitoring": 12, "measurement_quality": 8}
    counts = dict(Counter(item["domain"] for item in items))
    if counts != expected or len(items) != 96:
        raise ValueError(f"Unexpected taxonomy counts: {counts}")
    if len({normalized(item["title"] + item["content"]) for item in items}) != len(items):
        raise ValueError("Exact duplicate title/content detected")
    import jsonschema
    schema = json.loads((ROOT / "schemas" / "knowledge_item.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())
    for item in items:
        validator.validate(item)
    (ROOT / "data" / "knowledge_items.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")
    (ROOT / "data" / "corpus_verification.json").write_text(
        json.dumps({"verification_revision": "source-audit-v1", "count": len(items),
                    "domain_counts": counts, "indexed_fields": ["title", "content"],
                    "checks": checks}, indent=2) + "\n", encoding="utf-8")
    (ROOT / "data" / "corpus_review_input.json").write_text(
        json.dumps({"purpose": "Blinded independent source-support review; no cases or method outputs are included",
                    "items": review_input}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stop = set("a an the is are be of to in for and or with from as that by on it not do does can should may must this its than at when so each then even only rather alone about if before after more some same needs".split())
    token_sets = [set(re.findall(r"[a-z]+", (item["title"] + " " + item["content"]).lower())) - stop for item in items]
    candidates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            similarity = len(token_sets[i] & token_sets[j]) / len(token_sets[i] | token_sets[j])
            if similarity >= 0.28:
                candidates.append({"left_id": items[i]["id"], "right_id": items[j]["id"],
                                   "token_jaccard": round(similarity, 6),
                                   "same_domain": items[i]["domain"] == items[j]["domain"]})
    candidates.sort(key=lambda candidate: (-candidate["token_jaccard"], candidate["left_id"], candidate["right_id"]))
    (ROOT / "data" / "corpus_near_duplicate_candidates.json").write_text(
        json.dumps({"criterion": "word-set Jaccard >= 0.28 after declared stop words; a review flag, not semantic proof",
                    "stop_words": sorted(stop), "candidate_pairs": candidates}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"knowledge_count": len(items), "domain_counts": counts,
                      "schema_valid": True, "support_anchors_found": len(checks)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sources-only", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Validate and reuse source snapshots without network calls")
    args = parser.parse_args()
    if args.offline and args.refresh:
        parser.error("--offline and --refresh are mutually exclusive")
    manifest = fetch_sources(refresh=args.refresh, offline=args.offline)
    if not args.sources_only:
        build(manifest)


if __name__ == "__main__":
    main()
