"""Run eval/selftest against the configured database.

Free:  --rules (rule planner + database statistics), --lexical (keyword search)
Paid:  --agent (research agent answers), --hybrid (query embedding + search);
       both require --paid and are paced to stay under the per-visitor rate limit.

Gold values come from independent SQL over the same active, countable records;
retrieval gold is every retrievable article whose current text contains the
case's phrase. Results are written to outputs/ and never overwrite a file.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg

from observatory.config import Settings
from observatory.models import Filters
from observatory.service import Service
from observatory.structured_queries import plan_question

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "eval" / "selftest" / "cases.json").read_text(encoding="utf-8"))
NATIVE = Filters(dataset="native")
BASE = """FROM records r JOIN record_versions v ON v.version_id=r.current_version
 WHERE r.active AND r.dataset='native' AND (v.payload->>'countable')::boolean"""


def gold_statistics(conn, case):
    c = case.get("constraints", {})
    where, params = BASE, []
    for field in ("publisher", "sponsor"):
        if field in c:
            where += f" AND v.payload->>'{field}'=%s"
            params.append(c[field])
    if "years" in c:
        where += " AND (v.payload->>'published_at')::date BETWEEN %s AND %s"
        params += [date(c["years"][0], 1, 1), date(c["years"][1], 12, 31)]
    if case["expect"] == "group":
        field = case["group_by"]
        rows = conn.execute(
            f"SELECT COALESCE(NULLIF(v.payload->>'{field}',''),'(Unknown)'), count(*) {where} GROUP BY 1",
            params).fetchall()
        return dict(rows)
    return conn.execute(f"SELECT count(*) {where}", params).fetchone()[0]


def judge(case, gold, mode, total, groups, conn=None):
    if case["expect"] == "no_count":
        return mode != "statistics"
    if mode != "statistics":
        return False
    if (groups == gold if case["expect"] == "group" else total == gold):
        return True
    # An equally correct answer shape, e.g. a full distribution for a share question.
    return any(judge(alt, gold_statistics(conn, alt), mode, total, groups)
               for alt in case.get("alternatives", []) if conn is not None)


def outcome(answer):
    result = answer.structured_result or {}
    collections = result.get("collections") or []
    total = sum(item["total"] for item in collections) if collections else None
    groups = {g["name"]: g["count"] for g in result.get("groups") or []} or None
    return answer.answer_mode, total, groups


def run_rules(service, conn):
    facets = service.facets("native")
    rows = []
    for case in CASES["statistics"]:
        plan = plan_question(case["question"], NATIVE, facets)
        if plan is not None and plan.status == "ready":
            mode, total, groups = outcome(service._statistics_answer(plan))
        else:
            mode, total, groups = (plan.status if plan else "rag"), None, None
        gold = gold_statistics(conn, case) if case["expect"] != "no_count" else None
        rows.append({"id": case["id"], "pass": judge(case, gold, mode, total, groups, conn),
                     "mode": mode, "total": total, "groups": groups, "gold": gold})
    return rows


def run_agent(service, conn, settings):
    delay = 60 / max(1, settings.requests_per_minute) + 1
    visitor = f"selftest-{int(time.time())}"
    rows = []
    for index, case in enumerate(CASES["statistics"]):
        if index:
            time.sleep(delay)
        answer = service.answer(case["question"], NATIVE, visitor)
        mode, total, groups = outcome(answer)
        gold = gold_statistics(conn, case) if case["expect"] != "no_count" else None
        rows.append({"id": case["id"], "pass": judge(case, gold, mode, total, groups, conn),
                     "mode": mode, "status": answer.status, "failure": answer.failure_reason,
                     "total": total, "groups": groups, "gold": gold,
                     "answer": (answer.answer or "")[:200], "cost_usd": answer.cost_usd})
    return rows


def gold_records(conn, phrase):
    return {r[0] for r in conn.execute(
        "SELECT r.record_id FROM records r JOIN record_versions v ON v.version_id=r.current_version "
        "WHERE r.active AND (v.payload->>'retrievable')::boolean AND v.body ILIKE %s", (f"%{phrase}%",))}


def run_retrieval(service, conn, settings, hybrid):
    visitor = f"selftest-{int(time.time())}"
    rows = []
    for case in CASES["retrieval"]:
        gold = gold_records(conn, case["gold_phrase"])
        row = {"id": case["id"], "gold_records": len(gold)}
        for variant in ("en", "zh", "paraphrase"):
            question = case[variant]
            if hybrid:
                vector = service.rag.embed([question], visitor=visitor)[0]
                evidence = service.db.search(question, NATIVE, limit=5, vector=vector,
                                             model=settings.embedding_model, chunks_per_record=3)
            else:
                evidence = service.search_report(question, NATIVE)["evidence"]
            top = list(dict.fromkeys(e.record_id for e in evidence))[:5]
            row[variant] = bool(gold & set(top))
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for flag in ("rules", "lexical", "agent", "hybrid", "paid"):
        parser.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args()
    if (args.agent or args.hybrid) and not args.paid:
        raise SystemExit("--agent and --hybrid call the OpenAI API; add --paid to confirm.")
    if not any((args.rules, args.lexical, args.agent, args.hybrid)):
        args.rules = args.lexical = True
    settings = Settings.from_env()
    if args.agent and not settings.research_agent_enabled:
        raise SystemExit("--agent needs OBS_RESEARCH_AGENT_ENABLED=true.")
    service = Service(settings)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    report = {"run_at": datetime.now(timezone.utc).isoformat(), "cases_version": CASES["version"],
              "code_commit": commit, "src_uncommitted_changes": dirty,
              "generation_model": settings.generation_model, "embedding_model": settings.embedding_model,
              "data_version": service.health().get("data_version")}
    with psycopg.connect(settings.database_url) as conn:
        if args.rules:
            report["rules"] = run_rules(service, conn)
        if args.lexical:
            report["lexical"] = run_retrieval(service, conn, settings, hybrid=False)
        if args.agent:
            report["agent"] = run_agent(service, conn, settings)
        if args.hybrid:
            report["hybrid"] = run_retrieval(service, conn, settings, hybrid=True)
    if service.health().get("data_version") != report["data_version"]:
        raise SystemExit("Data changed during the run; results discarded.")

    summary = {}
    for name in ("rules", "agent"):
        if name in report:
            summary[name] = f"{sum(r['pass'] for r in report[name])}/{len(report[name])}"
    for name in ("lexical", "hybrid"):
        if name in report:
            summary[name] = {v: f"{sum(r[v] for r in report[name])}/{len(report[name])}"
                             for v in ("en", "zh", "paraphrase")}
    if "agent" in report:
        summary["agent_cost_usd"] = round(sum(r["cost_usd"] or 0 for r in report["agent"]), 5)
    report["summary"] = summary
    out = ROOT / "outputs" / f"selftest-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.parent.mkdir(exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for name in ("rules", "agent"):
        for row in report.get(name, []):
            if not row["pass"]:
                print(f"FAIL {name} {row['id']}: mode={row['mode']} total={row['total']} gold={row['gold']}",
                      file=sys.stderr)
    print(f"Saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
