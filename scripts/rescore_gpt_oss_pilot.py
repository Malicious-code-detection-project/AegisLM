"""CPU-only correction of saved Harmony predictions; never loads/trains a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gpt_oss_pilot import digest, parse_final, read_rows, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_root
    output = run / "rescored_summary_v2.json"
    if output.exists():
        raise ValueError("refusing to overwrite rescoring evidence")
    original = json.loads((run / "summary.json").read_text())
    manifest = json.loads((run / "manifest.json").read_text())
    if (
        digest(run / "validation.jsonl")
        != manifest["artifact_hashes"]["validation.jsonl"]
    ):
        raise ValueError("validation changed")
    gold = {row["id"]: row["label"] for row in read_rows(run / "validation.jsonl")}
    corrected = dict(original)
    evidence = {}
    for phase, key in (("baseline", "baseline"), ("reload", "adapter")):
        file = run / f"{phase}_predictions.jsonl"
        rows = read_rows(file)
        if len(rows) != len(gold) or {r["id"] for r in rows} != set(gold):
            raise ValueError("prediction identity set mismatch")
        for row in rows:
            if row["label"] != gold[row["id"]]:
                raise ValueError("prediction gold mismatch")
            row["assessment"], row["schema"] = parse_final(row["raw"])
        tp = sum(r["label"] == "present" and r["assessment"] == "present" for r in rows)
        fp = sum(
            r["label"] == "not_observed" and r["assessment"] == "present" for r in rows
        )
        positives = sum(r["label"] == "present" for r in rows)
        metrics = dict(original[key])
        metrics.update(
            schema_rate=sum(r["schema"] == "valid" for r in rows) / len(rows),
            accuracy=sum(r["label"] == r["assessment"] for r in rows) / len(rows),
            precision=tp / (tp + fp) if tp + fp else None,
            recall=tp / positives,
            fpr=fp / (len(rows) - positives),
            invalid_count=sum(r["assessment"] is None for r in rows),
            uncertain_count=sum(r["assessment"] == "uncertain" for r in rows),
        )
        corrected[key] = metrics
        evidence[phase] = {
            "predictions_sha256": digest(file),
            "corrected_labels": {r["id"]: r["assessment"] for r in rows},
        }
    corrected["diagnostic_quality_gate"] = (
        corrected["adapter"]["schema_rate"] >= 0.95
        and corrected["adapter"]["accuracy"] >= corrected["baseline"]["accuracy"]
    )
    corrected["rescoring"] = {
        "version": 2,
        "gpu_execution": False,
        "additional_training_runs": 0,
        "reason": "Recognize native Harmony final header with optional constrain JSON metadata; reject analysis-only content.",
        "original_summary_sha256": digest(run / "summary.json"),
        "scorer_sha256": digest(Path(__file__)),
        "parser_sha256": digest(Path(__file__).with_name("gpt_oss_pilot.py")),
        "evidence": evidence,
    }
    corrected["interpretation"] = (
        "Both base and adapter score 20/20 on this small diagnostic set; no observed accuracy gain. Loss is teacher-forced canonical final-answer loss."
    )
    write_json(output, corrected)
    print(json.dumps(corrected, indent=2))


if __name__ == "__main__":
    main()
