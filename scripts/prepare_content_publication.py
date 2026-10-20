"""Prepare private review templates and pinned membership artifacts without calls.

Only an independently supplied, explicitly approved review may produce a partial
or complete artifact. Pending real material is validated, never auto-approved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from prepare_content_assessment import load_content_packet, parse_json, read_bytes

from observatory.content_publication import (
    build_publication,
    make_review_template,
    validate_review,
)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _outside_packet(path, packet):
    if Path(path).resolve().is_relative_to(Path(packet).resolve()):
        raise ValueError("output_inside_original_packet")


def write_review_template(packet_dir, out_path, *, max_input_tokens=24000):
    """Write a new all-pending review; do not alter the original source packet."""
    out_path = Path(out_path)
    _outside_packet(out_path, packet_dir)
    if out_path.exists():
        raise ValueError("new_review_file_required")
    source = load_content_packet(packet_dir)
    review = make_review_template(source, max_input_tokens=max_input_tokens)
    data = encoded(review)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("review_template_too_large")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("xb") as stream:
        stream.write(data)
    return {"status": "pending_review_template", "selected_records": len(source["selected"]),
            "review_units": len(review["slots"]), "reviewed_units": 0,
            "review_sha256": digest(data), "definitions_sha256": review["definitions_sha256"],
            "scope_sha256": review["scope_sha256"], "model_calls": 0, "database_writes": 0,
            "publications": 0, "semantic_gold": False, "quality_scores": None}


def validate_review_file(packet_dir, review_path):
    return validate_review(load_content_packet(packet_dir), parse_json(read_bytes(review_path)))


def prepare_publication(packet_dir, review_path, out_dir):
    """Write a new immutable artifact; configuration and public activation are separate."""
    out_dir = Path(out_dir)
    _outside_packet(out_dir, packet_dir)
    if out_dir.exists() or Path(review_path).resolve().is_relative_to(out_dir.resolve()):
        raise ValueError("new_output_directory_required")
    source = load_content_packet(packet_dir)
    review_bytes = read_bytes(review_path)
    review_sha256 = digest(review_bytes)
    review = parse_json(review_bytes)
    publication = build_publication(source, review, review_sha256=review_sha256, review_bytes=review_bytes)
    publication_bytes = encoded(publication)
    if len(publication_bytes) > 64 * 1024 * 1024:
        raise ValueError("publication_artifact_too_large")
    summary = {"status": "prepared_immutable_artifact", "publication_status": publication["status"],
               "publication_sha256": digest(publication_bytes), "review_sha256": review_sha256,
               "packet_manifest_sha256": source["manifest_sha256"],
               "definitions_sha256": publication["definitions_sha256"], "scope_sha256": publication["scope_sha256"],
               "selected_records": len(publication["sources"]), "review_units": len(publication["slots"]),
               "reviewed_units": publication["reviewed_units"],
               "classification_complete": publication["classification_complete"],
               "model_calls": 0, "database_writes": 0, "server_activations": 0,
               "semantic_gold": False, "quality_scores": None}
    out_dir.mkdir(parents=True, exist_ok=False)
    for name, data in (("publication.json", publication_bytes), ("review.json", review_bytes),
                       ("preparation_summary.json", encoded(summary))):
        with (out_dir / name).open("xb") as stream:
            stream.write(data)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Create every record × 24 pending review slots")
    template.add_argument("--packet", required=True, type=Path)
    template.add_argument("--out", required=True, type=Path)
    template.add_argument("--max-input-tokens", type=int, default=24000)
    validate = sub.add_parser("validate", help="Validate review bindings without approving or publishing")
    validate.add_argument("--packet", required=True, type=Path)
    validate.add_argument("--review", required=True, type=Path)
    prepare = sub.add_parser("prepare", help="Prepare explicitly approved final review in a new directory")
    prepare.add_argument("--packet", required=True, type=Path)
    prepare.add_argument("--review", required=True, type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "template":
        result = write_review_template(args.packet, args.out, max_input_tokens=args.max_input_tokens)
    elif args.command == "validate":
        result = validate_review_file(args.packet, args.review)
    else:
        result = prepare_publication(args.packet, args.review, args.out)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
