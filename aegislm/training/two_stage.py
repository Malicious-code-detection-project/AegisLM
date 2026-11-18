"""Frozen inputs and objective-specific preparation for source two-stage SFT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aegislm.artifacts import validate_artifact_output_location
from aegislm.datasets.source import SourceAssessmentRecord
from aegislm.datasets.source_evidence_lines import validate_evidence_lines_output
from aegislm.evaluation.harness import load_jsonl
from aegislm.training.source import tokenize_source_training_record

FROZEN = {
    "decision": (
        "phase-f-source-decision-v1",
        "b987d174657061b0d0cdf263f738025514abbd9e3bb054251ca7d9d1777daa4e",
        "883a8159abebced1461e2b9dc88caa5e6578461bdd4227426011f0035aa1de6c",
    ),
    "evidence": (
        "phase-f-source-evidence-lines-v1",
        "bbf08a7e6988a08659badbc2411e75cb1665b76d62753e2712fb3f84982693b8",
        "3def771c14f100296878356168fa920d02c76ba85292a563ddce34b1f04e8987",
    ),
    "benchmark": (
        "phase-f-source-fresh-blind-500-v1",
        "d20ba5c538da786b64d628400b44b021bf4fa8c2fbd03f78bbab26de59103033",
        "d0270e19b024da0d4266d27e54d2435b3fcb22f85b9a71bf07c3f2fd4a8c1eeb",
    ),
    "contracts": (
        "phase-f-source-fresh-blind-contracts-500-v1",
        "c498a64d5f1b1cc6556283223602a6351997189f2ae386116234a6aca01a944e",
        "e5eb74a1f5cd375e83b3baf04de7a75807fdd1f9043d8a108f462c7b07e1a00a",
    ),
}


def digest(path: Path) -> str:
    """Hash a bounded experiment file."""
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Append an immutable experiment artifact; never overwrite results."""
    validate_artifact_output_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def load_config(path: Path) -> dict[str, Any]:
    """Load the deliberately fixed initial comparison recipe."""
    config: dict[str, Any] = json.loads(path.read_text())
    if config["recipe"] != "source_two_stage_v1":
        raise ValueError("wrong two-stage recipe")
    if config["training"] != {
        "max_seq_length": 4096,
        "batch_size": 1,
        "gradient_accumulation_steps": 32,
        "max_steps": 100,
        "learning_rate": 0.0001,
        "warmup_ratio": 0.1,
        "lora_r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "seed": 3407,
    }:
        raise ValueError("initial comparison training settings are frozen")
    roots = [
        Path(config[k]).resolve()
        for k in ("output_dir", "adapter_dir", "checkpoint_dir")
    ]
    for root in roots:
        validate_artifact_output_location(root)
        if any(
            root != other and (root.is_relative_to(other) or other.is_relative_to(root))
            for other in roots
        ):
            raise ValueError("experiment storage roots must be disjoint")
    if len(set(roots)) != 3:
        raise ValueError("experiment storage roots must differ")
    return config


def verify_inputs(base: Path) -> dict[str, Any]:
    """Verify the pinned manifests and every inventoried file before loading."""
    result = {}
    for key, (name, manifest_hash, inventory_hash) in FROZEN.items():
        root = base / name
        manifest = root / (
            "manifest.json" if key == "contracts" else "dataset_manifest.json"
        )
        if (
            digest(manifest) != manifest_hash
            or digest(root / "SHA256SUMS") != inventory_hash
        ):
            raise ValueError(f"{key}: frozen manifest/inventory mismatch")
        count = 0
        for line in (root / "SHA256SUMS").read_text().splitlines():
            expected, relative = line.split(maxsplit=1)
            target = (root / relative.lstrip("*")).resolve()
            if not target.is_relative_to(root.resolve()) or digest(target) != expected:
                raise ValueError(f"{key}: frozen file mismatch")
            count += 1
        result[key] = {"manifest_sha256": manifest_hash, "verified_files": count}
    return result


def data_root(config: dict[str, Any], objective: str) -> Path:
    return Path(config["dataset_dir"]) / FROZEN[objective][0]


def rows_for(
    config: dict[str, Any], objective: str, split: str
) -> list[dict[str, Any]]:
    root = data_root(config, objective)
    if objective == "evidence":
        root /= "canonical"
    rows = load_jsonl(root / f"{split}.jsonl")
    expected = {
        ("decision", "train"): 10000,
        ("decision", "validation"): 1000,
        ("evidence", "train"): 9975,
        ("evidence", "validation"): 996,
    }
    if len(rows) != expected[(objective, split)] or len({r["id"] for r in rows}) != len(
        rows
    ):
        raise ValueError("unexpected objective count or duplicate ids")
    for row in rows:
        validate_row(row, objective)
    return rows


def validate_row(row: dict[str, Any], objective: str) -> None:
    """Validate exact role order and the objective-specific gold contract."""
    messages = row["messages"]
    if [m["role"] for m in messages] != ["system", "user", "assistant"]:
        raise ValueError("training roles must be system/user/assistant")
    value = json.loads(messages[-1]["content"])
    if objective == "decision":
        if set(value) != {"assessment"} or value["assessment"] not in {
            "present",
            "not_observed",
        }:
            raise ValueError("invalid decision training target")
    else:
        payload = user_payload(messages)
        if payload["assessment"] not in {"present", "not_observed"}:
            raise ValueError("invalid evidence condition")
        errors = validate_evidence_lines_output(
            value, line_count=len(payload["numbered_source_code"].splitlines())
        )
        if errors:
            raise ValueError("invalid evidence training target: " + "; ".join(errors))


def user_payload(messages: list[dict[str, str]]) -> dict[str, Any]:
    content = next(m["content"] for m in messages if m["role"] == "user")
    payload, _ = json.JSONDecoder().raw_decode(content[content.index("{") :])
    if not isinstance(payload, dict):
        raise ValueError("user payload must be an object")
    return payload


def freeze_tokenizer(tokenizer: Any, date: str, *, training: bool) -> None:
    """Freeze the clock-dependent template in memory, preserving cached assets."""
    marker = 'strftime_now("%Y-%m-%d")'
    if marker in tokenizer.chat_template:
        if tokenizer.chat_template.count(marker) != 1:
            raise ValueError("unexpected tokenizer date expression")
        tokenizer.chat_template = tokenizer.chat_template.replace(
            marker, json.dumps(date)
        )
    elif f'"{date}"' not in tokenizer.chat_template:
        raise ValueError("tokenizer template does not have this run frozen date")
    tokenizer.padding_side = "right" if training else "left"
    if tokenizer.pad_token_id != 200017:
        raise ValueError("unexpected GPT-OSS padding token")


def tokenize_rows(
    rows: list[dict[str, Any]], tokenizer: Any, maximum: int
) -> list[dict[str, list[int]]]:
    """Use identical GPT-OSS boundaries for both compact objectives."""
    return [
        tokenize_source_training_record(
            SourceAssessmentRecord(str(row["id"]), tuple(row["messages"])),
            tokenizer,
            max_length=maximum,
            reasoning_effort="low",
        )
        for row in rows
    ]


def development(config: dict[str, Any]) -> dict[str, Any]:
    """Select shared development IDs from the original evidence dev100."""
    root = data_root(config, "evidence") / "development"
    evidence = load_jsonl(root / "challenge.jsonl")
    ids = [r["id"] for r in evidence]
    validation = {r["id"]: r for r in rows_for(config, "decision", "validation")}
    if len(ids) != 100 or len(set(ids)) != 100 or not set(ids) <= set(validation):
        raise ValueError("dev100 is not an exact validation subset")
    return {
        "decision": [{"id": i, "messages": validation[i]["messages"][:2]} for i in ids],
        "decision_gold": [
            {
                "id": i,
                "expected_output": json.loads(validation[i]["messages"][2]["content"]),
            }
            for i in ids
        ],
        "evidence": evidence,
        "evidence_gold": load_jsonl(root / "gold.jsonl"),
        "private": load_jsonl(root / "private-records.jsonl"),
    }


def split_overlap(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> dict[str, Any]:
    """Audit both IDs and actual visible code; renamed IDs cannot hide leakage."""

    def code_hash(row: dict[str, Any]) -> str:
        code = user_payload(row["messages"])["source_code"]
        if not isinstance(code, str) or not code:
            raise ValueError("split isolation requires source code")
        return hashlib.sha256(code.encode()).hexdigest()

    left_by_code: dict[str, list[str]] = {}
    for row in left:
        left_by_code.setdefault(code_hash(row), []).append(row["id"])
    left_ids = {row["id"] for row in left}
    matched = []
    for row in right:
        matches = left_by_code.get(code_hash(row), [])
        if row["id"] in left_ids or matches:
            matched.append(
                {
                    "right_id": row["id"],
                    "same_id": row["id"] in left_ids,
                    "same_code_left_ids": matches,
                }
            )
    return {
        "id_overlap_count": sum(row["same_id"] for row in matched),
        "code_overlap_count": sum(bool(row["same_code_left_ids"]) for row in matched),
        "matches": matched,
    }
