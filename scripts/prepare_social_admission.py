"""Prepare source-bound company-post admission; this never connects to a DB."""

import argparse
import json
from pathlib import Path

from observatory.social_admission import prepare_social_admission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--identity-conflicts", type=Path,
                        help="identity_conflicts.json from scripts/split_social_export.py "
                             "(required when the source has Facebook/Instagram rows)")
    args = parser.parse_args()
    receipt = prepare_social_admission(args.source, review_data=args.review_data, reviews=args.reviews, out=args.out,
                                       identity_conflicts=args.identity_conflicts)
    print(json.dumps({key: receipt[key] for key in (
        "status", "source_records", "unique_posts", "quarantined_source_rows",
        "countable_records", "retrievable_records", "out_of_scope_records", "identity_ambiguous_records",
        "count_units", "platform_posts", "conflict_counts", "canonical_sha256",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
