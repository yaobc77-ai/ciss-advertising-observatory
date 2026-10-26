"""Capture this read-only/offline audit's evidence; no model or database access."""

import csv
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/reviews/agent_review_20261005_evidence.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def junit(path):
    tree = ET.parse(path)
    suites = tree.getroot().findall("testsuite")
    if tree.getroot().tag == "testsuite":
        suites = [tree.getroot()]
    totals = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    return {"file": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
            **totals, "seconds": sum(float(s.get("time", 0)) for s in suites)}


def review_sheet(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        rows = list(reader)
    tracked = ("reviewer", "verdict", "human_verdict", "correct", "no_overclaim")
    return {"file": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
            "rows": len(rows), "nonempty_fields": {
                key: sum(bool((row.get(key) or "").strip()) for row in rows)
                for key in tracked if key in fields}}


def main():
    if OUTPUT.exists():
        raise SystemExit("Evidence receipt already exists; preserve this audit's original receipt.")
    preparation = command(sys.executable, "-X", "utf8", "scripts/prepare_client_review.py",
                          "--packet", "eval/client_review_20260925")
    prerequisites = json.loads(preparation.stdout)
    files = ["pyproject.toml", "src/observatory/research_agent.py", "src/observatory/research_tools.py",
             "src/observatory/structured_queries.py", "src/observatory/service.py",
             "src/observatory/rag.py", "src/observatory/evaluate.py", "src/observatory/mcp_server.py",
             "scripts/prepare_client_review.py", "scripts/run_selftest.py",
             "tests/test_research_tools.py", "tests/test_structured_queries.py",
             "tests/test_date_inference.py", "tests/test_evaluate.py",
             "tests/test_research_service.py", "tests/test_answer_web_fallback_routes.py",
             "eval/user_questions/cases.json", "eval/selftest/cases.json",
             "eval/client_review_20260925/review_plan.json",
             "eval/client_review_20260925/questions.jsonl",
             "eval/client_review_20260925/article_groups.csv",
             "reports/reviews/agent_review_20261005_capture.py"]
    sheets = [ROOT / "eval/client_review_20260925/answer_review.csv",
              *sorted((ROOT / "outputs").glob("user-questions-review*.csv")),
              *sorted((ROOT / "reports").glob("citation_review*.csv"))]
    changed_paths = command("git", "diff", "--name-only").stdout.splitlines()
    lint_paths = [name for name in changed_paths if name.endswith(".py")]
    lint = command(sys.executable, "-m", "ruff", "check", *lint_paths,
                   "reports/reviews/agent_review_20261005_capture.py")
    whitespace = command("git", "diff", "--check")
    receipt = {
        "schema_version": 1, "report_date": "2026-10-05", "report_timezone": "America/New_York",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": command("git", "rev-parse", "HEAD").stdout.strip(),
        "changes_are_uncommitted": True,
        "changed_tracked_paths": changed_paths,
        "source_byte_sha256": {name: digest(ROOT / name) for name in files},
        "environment": {"python": sys.version.split()[0],
                        "pytest": importlib.metadata.version("pytest"),
                        "pydantic": importlib.metadata.version("pydantic")},
        "tests": {
            "baseline": junit(ROOT / "reports/reviews/agent_review_20261005_baseline.junit.xml"),
            "full_initial": junit(ROOT / "reports/reviews/agent_review_20261005_full_initial.junit.xml"),
            "full_retry1": junit(ROOT / "reports/reviews/agent_review_20261005_full_retry1.junit.xml"),
            "asset_check": junit(ROOT / "reports/reviews/agent_review_20261005_asset_check.junit.xml"),
            "final": junit(ROOT / "reports/reviews/agent_review_20261005_final.junit.xml")},
        "quality_checks": {
            "ruff": {"exit_code": lint.returncode, "stdout": lint.stdout.strip()},
            "git_diff_check": {"exit_code": whitespace.returncode,
                               "stdout": whitespace.stdout.strip()}},
        "review_packet_check": {"command": "python scripts/prepare_client_review.py --packet eval/client_review_20260925",
                                "exit_code": preparation.returncode, "result": prerequisites},
        "review_sheets": [review_sheet(path) for path in sheets],
        "paid_api_calls": 0, "database_evaluation_run": False,
        "deployment_performed": False, "semantic_acceptance": "pending_human_review",
        "overall_pass": None,
        "limits": ["JUnit counts describe engineering tests, not real model accuracy.",
                   "CSV completeness does not authenticate a reviewer or prove semantic support.",
                   "No current production or live-model acceptance was evaluated."]}
    OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(OUTPUT), "tests": receipt["tests"],
                      "review_packet_status": prerequisites["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
