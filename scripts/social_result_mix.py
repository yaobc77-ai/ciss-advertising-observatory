"""How much of a social result list is replies, retweets or repeated text (free, private cluster only).

For each team-written question, a keyword-only ``Database.search`` (no vector, so no embedding
call) reads the top ``--limit`` social records, and the report counts how many of them are

- replies: the source marks ``post.is_reply`` true. Facebook and Instagram exports carry no
  mark, so a result without one is "no reply mark observed", not a confirmed non-reply;
- retweets: the post text starts with "RT @";
- repeated text: another active social record has exactly the same body.

It also lists the platforms of the results, since only Twitter carries a reply mark. The
overall figures count result appearances: a post found by two questions counts twice.

It reads a private test cluster from ``scripts/private_test_postgres.py``, never the main database:
before any search it checks that the server on the port runs that cluster's own data directory.
It prints no connection string. The questions are generic team examples, not the customer's.

    python -X utf8 scripts/social_result_mix.py --cluster import_rehearsal --out mix.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

QUESTIONS = [
    "Which ads describe reducing or decreasing greenhouse gas emissions?",
    "Which ads mention environmental or climate policies, regulations or programs?",
    "Which ads mention fossil fuel infrastructure or production, such as drilling, pipelines, refineries or power plants?",
    "carbon capture and storage",
    "natural gas as a cleaner energy source",
    "investment in solar and wind power",
]
KINDS = ("reply", "retweet", "repeated_text")


def kinds(row):
    """The non-advertising kinds of one result: {"is_reply", "body", "same_body_records"}."""
    found = set()
    if row.get("is_reply") is True:
        found.add("reply")
    if (row.get("body") or "").lstrip().startswith("RT @"):
        found.add("retweet")
    if (row.get("same_body_records") or 0) > 1:
        found.add("repeated_text")
    return found


def mix(rows):
    """Counts and shares of each kind, and of results with any of them, over one result list."""
    marks = [kinds(row) for row in rows]
    total = len(rows)
    counts = {kind: sum(kind in m for m in marks) for kind in KINDS}
    counts["any"] = sum(bool(m) for m in marks)
    platforms = Counter(row.get("platform") or "unknown" for row in rows)
    return {"results": total, "platforms": dict(platforms.most_common()), "counts": counts,
            "shares": {k: round(v / total, 3) if total else None for k, v in counts.items()}}


_DETAILS = """SELECT r.record_id, v.body, v.payload->>'platform' AS platform,
       COALESCE(v.payload#>>'{raw,source_row,post,is_reply}','') = 'true' AS is_reply,
       (SELECT count(*) FROM records r2 JOIN record_versions v2 ON v2.version_id=r2.current_version
         WHERE r2.active AND r2.dataset='social' AND v2.body_hash=v.body_hash) AS same_body_records
  FROM records r JOIN record_versions v ON v.version_id=r.current_version
 WHERE r.record_id = ANY(%s)"""


def open_private_database(cluster, port, *, connect, database_cls, host):
    """A Database on ``port`` only if that server runs ``cluster``'s own data directory.

    The registered port can be overridden (it may fall in a reserved Windows range), so the
    server behind the port is identified with the cluster's admin login before anything is read.
    """
    settings = cluster.settings()
    with connect(host=host, hostaddr=host, port=port, dbname="postgres", user=settings["admin_user"],
                 password=settings["admin_password"], connect_timeout=5, autocommit=True) as conn:
        row = conn.execute("SELECT current_setting('data_directory'), current_setting('port')").fetchone()
    if Path(row[0]).resolve() != cluster.data or int(row[1]) != port:
        raise RuntimeError("The server on this port is not the named private test cluster; nothing was read.")
    return database_cls(f"postgresql://{quote(settings['app_user'])}:{quote(settings['app_password'], safe='')}"
                        f"@{host}:{port}/obs_test")


def main(argv=None):
    import private_test_postgres as ptp
    import psycopg

    from observatory.db import Database
    from observatory.models import Filters

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cluster", required=True, help="private test cluster name")
    parser.add_argument("--port", type=int, help="override the cluster's recorded port")
    parser.add_argument("--limit", type=int, default=40, help="social records read per question")
    parser.add_argument("--out", type=Path, required=True, help="new JSON report path")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("--out must be a new file")
    cluster = ptp.PrivateTestCluster(args.cluster)
    port = args.port or cluster.state()["port"]
    db = open_private_database(cluster, port, connect=psycopg.connect, database_cls=Database, host=ptp.HOST)
    report = {"cluster": args.cluster, "limit": args.limit, "search": "keyword only, dataset social",
              "overall_unit": "result appearances across questions; a post found twice counts twice",
              "reply_basis": "source post.is_reply true; no mark is not a confirmed non-reply",
              "questions": []}
    every = []
    for question in QUESTIONS:
        evidence = db.search(question, Filters(dataset="social"), limit=args.limit)
        ids = list(dict.fromkeys(item.record_id for item in evidence))
        with db.connect() as conn:
            details = {row["record_id"]: row for row in conn.execute(_DETAILS, [ids]).fetchall()}
        rows = [details[i] for i in ids if i in details]
        every += rows
        report["questions"].append({"question": question, **mix(rows)})
        print(question[:50], report["questions"][-1]["shares"], flush=True)
    report["overall"] = mix(every)
    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["overall"], ensure_ascii=False))


if __name__ == "__main__":
    main()
