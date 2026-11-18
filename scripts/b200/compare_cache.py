"""Collect cache experiments without treating pending or abstentions as negatives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(row: dict[str, Any]) -> dict[str, Any]:
    """Binary metrics are conditional on decisive outputs; coverage stays explicit."""
    if row.get("counts") is None:
        return {"completion_rate": ratio(row["completed"], row["planned"])}
    tp, fn, fp, tn, uncertain, invalid = row["counts"]
    completed = row["completed"]
    if min(row["counts"]) < 0 or sum(row["counts"]) != completed:
        raise ValueError("Counts must partition completed samples")
    positive = row.get("observed_positive")
    # U/I를 제외한 조건부 지표와 전체 완료 표본의 성능을 함께 남긴다.
    return {
        "precision": ratio(tp, tp + fp),
        "recall_decisive": ratio(tp, tp + fn),
        "f1_decisive": ratio(2 * tp, 2 * tp + fp + fn),
        "specificity_decisive": ratio(tn, tn + fp),
        "positive_detection_recall": ratio(tp, positive) if positive else None,
        "accuracy_completed": ratio(tp + tn, completed),
        "decision_coverage": ratio(tp + fn + fp + tn, completed),
        "uncertain_rate": ratio(uncertain, completed),
        "invalid_rate": ratio(invalid, completed),
        "completion_rate": ratio(completed, row["planned"]),
    }


def read_report(path: Path, hardware: str, policy: str) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    rows = []
    for group in data["groups"]:
        for criterion in ("strict", "semantic"):
            matrix = group[f"{criterion}_matrix"]
            if len(matrix) != 2 or any(len(line) != 4 for line in matrix):
                raise ValueError("Expected a 2 by 4 confusion matrix")
            row = {
                "hardware": hardware,
                "cache": policy,
                "model": group["model"],
                "budget": group["budget"],
                "criterion": criterion,
                "completed": group["completed"],
                "planned": group["planned"],
                "matrix": matrix,
                "counts": [
                    matrix[0][0],
                    matrix[0][1],
                    matrix[1][0],
                    matrix[1][1],
                    matrix[0][2] + matrix[1][2],
                    matrix[0][3] + matrix[1][3],
                ],
                "observed_positive": sum(matrix[0]),
                "provenance": {"kind": "scorer_json", "path": str(path)},
            }
            row["metrics"] = metrics(row)
            rows.append(row)
    return rows


def collect(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    rows = []
    missing = []
    for source in manifest["sources"]:
        path = root / source["path"]
        if not path.exists():
            missing.append(source)
            continue
        rows.extend(read_report(path, source["hardware"], source["cache"]))
    for reference in manifest.get("references", []):
        data = json.loads((root / reference).read_text())
        for row in data["rows"]:
            row["provenance"] = data["provenance"]
            row["metrics"] = metrics(row)
            rows.append(row)
    # 한 조건의 중복 원본을 조용히 합치면 100개 표본이 200개로 보이므로 거부한다.
    keys = [
        (r["hardware"], r["cache"], r["model"], str(r["budget"]), r["criterion"])
        for r in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate comparison condition")
    return {
        "schema_version": 1,
        "notes": manifest["notes"],
        "rows": rows,
        "missing_sources": missing,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    lines = [
        "# 캐시 비교",
        "",
        *[f"- {note}" for note in report["notes"]],
        "",
        "P: precision, R/F1: 유효한 이진 판단에 조건부. R전체: 완료한 실제 양성 중 탐지 비율.",
        "—는 미확인 또는 분모 0. 완료 수가 다른 조건은 동일 표본 성능으로 비교하지 않는다.",
        "",
        "|장비|캐시|모델|상한|채점|완료|TP/FN/FP/TN/U/I|P|R|F1|R전체|정확도|판단율|",
        "|---|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        measures = row["metrics"]
        values = [
            measures.get(key)
            for key in (
                "precision",
                "recall_decisive",
                "f1_decisive",
                "positive_detection_recall",
                "accuracy_completed",
                "decision_coverage",
            )
        ]
        display = ["—" if value is None else f"{value:.4f}" for value in values]
        counts = (
            "/".join(map(str, row["counts"]))
            if row.get("counts") is not None
            else "미확인"
        )
        lines.append(
            "|"
            + "|".join(
                map(
                    str,
                    [
                        row["hardware"],
                        row["cache"],
                        row["model"],
                        row["budget"],
                        row["criterion"],
                        f"{row['completed']}/{row['planned']}",
                        counts,
                        *display,
                    ],
                )
            )
            + "|"
        )
    for source in report["missing_sources"]:
        lines.append(f"\n미생성 원본: `{source['path']}`")
    (output / "comparison.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    write_report(collect(json.loads(args.manifest.read_text()), root), args.output)


if __name__ == "__main__":
    main()
