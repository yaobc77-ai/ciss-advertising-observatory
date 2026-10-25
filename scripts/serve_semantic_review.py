"""Standalone file-backed semantic review, independent of the production app."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from observatory.semantic_review import (  # noqa: E402
    ReviewStore,
    demo_packet,
    make_server,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--codebook", type=Path, default=ROOT / "eval/semantic_review/semantic_codebook.v1.json")
    init.add_argument("--packets", type=Path)
    assign = commands.add_parser("assign")
    for name in ("reviewer-a", "reviewer-b", "adjudicator"):
        assign.add_argument("--" + name, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8072)
    export = commands.add_parser("export")
    export.add_argument("--destination", type=Path, required=True)
    commands.add_parser("status")
    links = commands.add_parser("links")
    links.add_argument("--port", type=int, default=8072)
    args = parser.parse_args(argv)
    if args.command == "init":
        codebook = json.loads(args.codebook.read_text(encoding="utf-8"))
        packets = [json.loads(line) for line in args.packets.read_text(encoding="utf-8").splitlines()] if args.packets else [demo_packet()]
        store = ReviewStore.initialize(args.store, codebook, packets)
        print(json.dumps(store.manifest, ensure_ascii=False, indent=2))
        return 0
    store = ReviewStore(args.store)
    if args.command == "assign":
        store.assign(args.reviewer_a, args.reviewer_b, args.adjudicator)
        print("Assigned three distinct human reviewer IDs. Use links locally; do not publish bearer links.")
    elif args.command == "serve":
        server = make_server(store, port=args.port)
        print(f"Local semantic review: http://127.0.0.1:{args.port}/", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    elif args.command == "export":
        store.export(args.destination)
        print("Exported review material and agreement; gold=false.")
    elif args.command == "links":
        assignments = json.loads((args.store / "assignments.private.json").read_text(encoding="utf-8"))
        for role, value in assignments.items():
            for case in store.packets:
                print(role + " " + f"http://127.0.0.1:{args.port}/review?" + urlencode(
                    {"role": role, "token": value["token"], "case": case}))
    else:
        print(json.dumps(store.agreement(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
