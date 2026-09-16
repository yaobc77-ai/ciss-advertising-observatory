import argparse
import json
from pathlib import Path

from .config import Settings
from .db import Database
from .models import Filters


def emit(value, out=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def main():
    parser = argparse.ArgumentParser(
        description="CISS Observatory local administration"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("health")
    sub.add_parser("serve")
    sub.add_parser("budget")
    imp = sub.add_parser("import-native")
    imp.add_argument("--root", type=Path, default=Path.cwd())
    imp.add_argument("--out", default="outputs/native_import.json")
    social = sub.add_parser("import-social")
    social.add_argument("path", type=Path)
    social.add_argument("--mapping", type=Path, required=True)
    social.add_argument("--out", default="outputs/social_import.json")
    sub.add_parser("index")
    for command in ["search", "answer"]:
        p = sub.add_parser(command)
        p.add_argument("question")
        p.add_argument(
            "--dataset", choices=["native", "social", "all"], default="native"
        )
        p.add_argument("--out")
    args = parser.parse_args()
    settings = Settings.from_env()
    db = Database(settings.database_url)
    if args.command == "init-db":
        db.initialize()
        emit({"initialized": True})
    elif args.command == "health":
        emit(db.health())
    elif args.command == "budget":
        from .budget import Budget

        emit(Budget(db, settings).summary())
    elif args.command == "import-native":
        from .ingest import load_native

        emit(
            db.import_batch(
                load_native(
                    args.root, require_admissions=True, require_body_reviews=True
                ),
                snapshot_dataset="native",
            ),
            args.out,
        )
    elif args.command == "import-social":
        from .ingest import load_social

        mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
        batch = load_social(args.path, mapping)
        emit(db.import_batch(batch), args.out)
    elif args.command == "index":
        from .rag import Rag

        emit(Rag(db, settings).index())
    elif args.command in ("search", "answer"):
        from .service import Service

        service = Service(settings)
        filters = Filters(dataset=args.dataset)
        result = (
            [e.model_dump() for e in service.search(args.question, filters)]
            if args.command == "search"
            else service.answer(args.question, filters, "local-maintainer").model_dump()
        )
        emit(result, args.out)
    elif args.command == "serve":
        from waitress import serve

        from .app import create_app
        from .service import Service

        app = create_app(Service(settings), settings)
        serve(app.server, host=settings.host, port=settings.port, threads=8)


if __name__ == "__main__":
    main()
