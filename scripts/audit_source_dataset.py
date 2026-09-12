"""Audit source-v2 splits, leakage, labels, schema, and exact evidence spans."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan, write_text_artifact
    from aegislm.datasets import (
        load_source_gold,
        load_source_records,
        records_sha256,
        source_code_sha256,
    )
    from aegislm.evaluation import validate_source_gold, validate_source_assessment

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None:
        validate_artifact_path_plan(
            inputs=(args.train, args.validation, args.challenge, args.gold),
            outputs=(args.output,),
            protected_roots=(
                args.train.parent,
                args.validation.parent,
                args.challenge.parent,
                args.gold.parent,
            ),
            require_new=True,
        )

    splits = {
        "train": load_source_records(args.train, require_assistant=True),
        "validation": load_source_records(args.validation, require_assistant=True),
        "challenge": load_source_records(args.challenge, require_assistant=False),
    }
    gold = load_source_gold(args.gold)
    id_sets = {
        name: {record.record_id for record in rows} for name, rows in splits.items()
    }
    hash_sets = {
        name: {source_code_sha256(record) for record in rows}
        for name, rows in splits.items()
    }
    overlap: dict[str, dict[str, int]] = {}
    names = list(splits)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap[f"{left}:{right}"] = {
                "id": len(id_sets[left] & id_sets[right]),
                "code_sha256": len(hash_sets[left] & hash_sets[right]),
            }

    schema_failures: list[dict[str, object]] = []
    exact_span_failures = 0
    for split in ("train", "validation"):
        for record in splits[split]:
            output = record.assistant_output
            assert output is not None
            validation = validate_source_assessment(
                output,
                source_code=record.source_code,
                target_cwe=record.target_cwe,
            )
            if not validation.ok:
                exact_span_failures += sum(
                    "exact substring" in error for error in validation.errors
                )
                schema_failures.append(
                    {"id": record.record_id, "errors": validation.errors}
                )

    gold_failures: list[str] = []
    try:
        validate_source_gold(splits["challenge"], gold)
    except ValueError as exc:
        gold_failures.append(str(exc))

    report = {
        "splits": {
            name: {
                "count": len(rows),
                "sha256": records_sha256(rows),
                "assessment_counts": dict(
                    Counter(
                        record.assessment
                        for record in rows
                        if record.assessment is not None
                    )
                ),
                "cwe_count": len({record.target_cwe for record in rows}),
            }
            for name, rows in splits.items()
        },
        "overlap": overlap,
        "gold": {
            "count": len(gold),
            "sha256": _file_sha256(args.gold),
            "validation_failure_count": len(gold_failures),
            "sample_failures": gold_failures[:10],
        },
        "schema_failure_count": len(schema_failures),
        "exact_span_failure_count": exact_span_failures,
        "sample_failures": schema_failures[:10],
    }
    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        write_text_artifact(args.output, text + "\n")
    print(text)
    if any(value["id"] or value["code_sha256"] for value in overlap.values()):
        raise SystemExit("split leakage detected")
    if schema_failures:
        raise SystemExit("source-v2 validation failures detected")
    if gold_failures:
        raise SystemExit("source-v2 gold validation failures detected")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
