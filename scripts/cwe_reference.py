"""Build and query local English CWE references without GPU or network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegislm.datasets.cwe_reference import (
    build_reference,
    load_reference,
    lookup,
    markdown,
    search,
)


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    build = commands.add_parser("build")
    build.add_argument("--xml", type=Path, required=True)
    build.add_argument("--terms", type=Path, required=True)
    build.add_argument("--source-url", required=True)
    build.add_argument("--output", type=Path, required=True)
    show = commands.add_parser("show")
    show.add_argument("--reference", type=Path, required=True)
    show.add_argument("--id", required=True)
    show.add_argument("--format", choices=("json", "markdown"), default="markdown")
    find = commands.add_parser("search")
    find.add_argument("--reference", type=Path, required=True)
    find.add_argument("--query", required=True)
    find.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.action == "build":
        manifest = build_reference(args.xml, args.terms, args.output, args.source_url)
        print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=2))
        return
    records = load_reference(args.reference)
    if args.action == "show":
        record = lookup(records, args.id)
        print(
            markdown(record)
            if args.format == "markdown"
            else json.dumps(record, indent=2)
        )
    else:
        results = search(records, args.query, args.limit)
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
