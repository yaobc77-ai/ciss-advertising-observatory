"""Prepare source-preserving retrieval for paused social posts, without a DB or model."""

import argparse
import json
from pathlib import Path

from observatory.social_source_retrieval import prepare_source_retrieval


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--original-source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-changes", type=int)
    args = parser.parse_args()
    receipt = prepare_source_retrieval(args.source, original_source=args.original_source,
                                       out=args.out, expected_changes=args.expected_changes)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
