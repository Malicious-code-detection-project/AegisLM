"""Load and audit the frozen source-v2 chat datasets."""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from aegislm.artifacts import (
    DEFAULT_JSONL_MAX_BYTES,
    DEFAULT_JSONL_MAX_LINE_BYTES,
    DEFAULT_JSONL_MAX_RECORDS,
    load_bounded_jsonl_objects,
    strict_json_loads,
)
from aegislm.schemas import SOURCE_ASSESSMENTS

SOURCE_RECORD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SOURCE_CWE_PATTERN = re.compile(r"^CWE-[1-9][0-9]*$")
MAX_SOURCE_MESSAGE_CHARACTERS = DEFAULT_JSONL_MAX_LINE_BYTES


@dataclass(frozen=True)
class SourceAssessmentRecord:
    """One source-vulnerability chat record with an optional gold response."""

    record_id: str
    messages: tuple[dict[str, str], ...]
    code_sha256: str | None = None

    @property
    def prompt_messages(self) -> tuple[dict[str, str], ...]:
        """Return model-visible messages, excluding the gold assistant response."""
        return tuple(
            message for message in self.messages if message["role"] != "assistant"
        )

    @property
    def assistant_output(self) -> dict[str, Any] | None:
        """Parse the single assistant JSON object, if this split has one."""
        assistants = [
            message for message in self.messages if message["role"] == "assistant"
        ]
        if not assistants:
            return None
        parsed = _strict_embedded_json(assistants[0]["content"], self.record_id)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"{self.record_id}: assistant content must be a JSON object"
            )
        return parsed

    @property
    def user_payload(self) -> dict[str, Any]:
        """Parse the JSON payload embedded in the user message."""
        user_messages = [
            message for message in self.messages if message["role"] == "user"
        ]
        if len(user_messages) != 1:
            raise ValueError(f"{self.record_id}: expected exactly one user message")
        content = user_messages[0]["content"]
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end < start:
            raise ValueError(f"{self.record_id}: user message has no JSON payload")
        payload = _strict_embedded_json(content[start : end + 1], self.record_id)
        if not isinstance(payload, dict):
            raise ValueError(f"{self.record_id}: user payload must be a JSON object")
        return payload

    @property
    def source_code(self) -> str:
        value = self.user_payload.get("source_code")
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{self.record_id}: source_code must be a non-empty string"
            )
        return value

    @property
    def target_cwe(self) -> str:
        scope = self.user_payload.get("scope")
        value = scope.get("target_cwe") if isinstance(scope, dict) else None
        if not isinstance(value, str) or SOURCE_CWE_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{self.record_id}: scope.target_cwe must be a CWE ID")
        return value

    @property
    def assessment(self) -> str | None:
        output = self.assistant_output
        value = output.get("assessment") if output else None
        return value if isinstance(value, str) else None


def load_source_records(
    path: Path, *, require_assistant: bool
) -> list[SourceAssessmentRecord]:
    """Load strict chat JSONL without exposing a separate gold file to inference."""
    records: list[SourceAssessmentRecord] = []
    seen_ids: set[str] = set()
    rows, _digest = load_bounded_jsonl_objects(
        path,
        description="source dataset",
        max_bytes=DEFAULT_JSONL_MAX_BYTES,
        max_line_bytes=DEFAULT_JSONL_MAX_LINE_BYTES,
        max_records=DEFAULT_JSONL_MAX_RECORDS,
    )
    for line_number, raw in enumerate(rows, 1):
        record = parse_source_record(raw, require_assistant=require_assistant)
        if record.record_id in seen_ids:
            raise ValueError(f"{path}:{line_number}: duplicate id {record.record_id!r}")
        seen_ids.add(record.record_id)
        records.append(record)
    if not records:
        raise ValueError(f"{path}: dataset is empty")
    return records


def parse_source_record(raw: Any, *, require_assistant: bool) -> SourceAssessmentRecord:
    """Validate the outer chat shape while preserving frozen message content."""
    if not isinstance(raw, dict):
        raise ValueError("source record must be a JSON object")
    record_id = raw.get("id")
    messages = raw.get("messages")
    code_sha256 = raw.get("code_sha256")
    if (
        not isinstance(record_id, str)
        or SOURCE_RECORD_ID_PATTERN.fullmatch(record_id) is None
    ):
        raise ValueError("source record id has an invalid safe identifier format")
    if not isinstance(messages, list):
        raise ValueError(f"{record_id}: messages must be an array")
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError(f"{record_id}: every message must be an object")
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str):
            raise ValueError(f"{record_id}: invalid message role/content")
        if len(content) > MAX_SOURCE_MESSAGE_CHARACTERS:
            raise ValueError(f"{record_id}: message content exceeds the size limit")
        normalized.append({"role": role, "content": content})
    roles = [message["role"] for message in normalized]
    expected = (
        ["system", "user", "assistant"] if require_assistant else ["system", "user"]
    )
    if roles != expected:
        raise ValueError(f"{record_id}: expected message roles {expected}, got {roles}")
    if code_sha256 is not None and not isinstance(code_sha256, str):
        raise ValueError(f"{record_id}: code_sha256 must be a string when present")
    record = SourceAssessmentRecord(record_id, tuple(normalized), code_sha256)
    _ = record.target_cwe
    if code_sha256 is not None:
        if re.fullmatch(r"[0-9a-f]{64}", code_sha256) is None:
            raise ValueError(
                f"{record_id}: code_sha256 must be 64 lowercase hex digits"
            )
        calculated = source_code_sha256(record)
        if code_sha256 != calculated:
            raise ValueError(
                f"{record_id}: code_sha256 does not match the supplied source_code"
            )
    if require_assistant and record.assessment not in SOURCE_ASSESSMENTS:
        raise ValueError(f"{record_id}: invalid or missing assistant assessment")
    return record


def load_source_gold(path: Path) -> dict[str, dict[str, Any]]:
    """Load gold outputs separately; callers must do this only after inference."""
    gold: dict[str, dict[str, Any]] = {}
    rows, _digest = load_bounded_jsonl_objects(
        path,
        description="source gold",
        max_bytes=DEFAULT_JSONL_MAX_BYTES,
        max_line_bytes=DEFAULT_JSONL_MAX_LINE_BYTES,
        max_records=DEFAULT_JSONL_MAX_RECORDS,
    )
    for line_number, item in enumerate(rows, 1):
        record_id = item.get("id") if isinstance(item, dict) else None
        expected = item.get("expected_output") if isinstance(item, dict) else None
        if (
            not isinstance(record_id, str)
            or SOURCE_RECORD_ID_PATTERN.fullmatch(record_id) is None
            or not isinstance(expected, dict)
        ):
            raise ValueError(f"{path}:{line_number}: invalid gold record")
        if record_id in gold:
            raise ValueError(f"{path}:{line_number}: duplicate id {record_id!r}")
        gold[record_id] = expected
    if not gold:
        raise ValueError(f"{path}: gold dataset is empty")
    return gold


def select_stratified_canary(
    records: list[SourceAssessmentRecord], size: int, *, seed: int
) -> list[SourceAssessmentRecord]:
    """Select a deterministic assessment-stratified canary subset."""
    if size <= 0 or size > len(records):
        raise ValueError("canary size must be between 1 and the dataset size")
    groups: dict[str, list[SourceAssessmentRecord]] = {}
    for record in records:
        label = record.assessment
        if label is None:
            raise ValueError(f"{record.record_id}: canary selection requires a label")
        groups.setdefault(label, []).append(record)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    selected: list[SourceAssessmentRecord] = []
    labels = sorted(groups)
    while len(selected) < size:
        progressed = False
        for label in labels:
            if groups[label] and len(selected) < size:
                selected.append(groups[label].pop())
                progressed = True
        if not progressed:
            break
    return selected


def select_target_cwe_assessment_canary(
    records: list[SourceAssessmentRecord], size: int, *, seed: int
) -> list[SourceAssessmentRecord]:
    """Select a deterministic train canary across CWE/assessment strata.

    This is an opt-in data-distribution ablation. The legacy assessment-only
    selector above remains unchanged so its historical record ordering and
    digest stay reproducible. Lexical tuple ordering is part of the v1
    contract; callers must version a different ordering as a new strategy.
    """
    if size <= 0 or size > len(records):
        raise ValueError("canary size must be between 1 and the dataset size")
    groups: dict[tuple[str, str], list[SourceAssessmentRecord]] = {}
    for record in records:
        label = record.assessment
        if label is None:
            raise ValueError(f"{record.record_id}: canary selection requires a label")
        groups.setdefault((record.target_cwe, label), []).append(record)
    if size < len(groups):
        raise ValueError(
            "target-CWE/assessment canary size must cover every observed stratum"
        )

    rng = random.Random(seed)
    keys = sorted(groups)
    for key in keys:
        rng.shuffle(groups[key])
    selected: list[SourceAssessmentRecord] = []
    while len(selected) < size:
        progressed = False
        for key in keys:
            if groups[key] and len(selected) < size:
                selected.append(groups[key].pop())
                progressed = True
        if not progressed:
            break
    return selected


def select_source_train_canary(
    records: list[SourceAssessmentRecord],
    size: int,
    *,
    seed: int,
    strategy: str,
) -> list[SourceAssessmentRecord]:
    """Dispatch a versioned train-only canary selection strategy."""
    if strategy == "assessment_round_robin_v1":
        return select_stratified_canary(records, size, seed=seed)
    if strategy == "target_cwe_assessment_round_robin_v1":
        return select_target_cwe_assessment_canary(records, size, seed=seed)
    raise ValueError(f"unsupported source train selection strategy: {strategy}")


def records_sha256(records: Iterable[SourceAssessmentRecord]) -> str:
    """Return a stable digest over record IDs and frozen message content."""
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.record_id.encode())
        digest.update(b"\0")
        digest.update(
            json.dumps(
                record.messages,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


def source_code_sha256(record: SourceAssessmentRecord) -> str:
    """Calculate the authoritative digest from the parsed source text."""
    return hashlib.sha256(record.source_code.encode()).hexdigest()


def validate_source_split_integrity(
    train_records: Iterable[SourceAssessmentRecord],
    validation_records: Iterable[SourceAssessmentRecord],
) -> None:
    """Reject train/validation leakage by identity or canonical source content."""
    train = tuple(train_records)
    validation = tuple(validation_records)
    train_ids = {record.record_id for record in train}
    validation_ids = {record.record_id for record in validation}
    duplicate_ids = train_ids & validation_ids
    if duplicate_ids:
        raise ValueError("source train/validation split leakage detected by record id")
    train_code = {source_code_sha256(record) for record in train}
    validation_code = {source_code_sha256(record) for record in validation}
    duplicate_code = train_code & validation_code
    if duplicate_code:
        raise ValueError(
            "source train/validation split leakage detected by source code"
        )


def _strict_embedded_json(text: str, record_id: str) -> Any:
    if len(text.encode("utf-8")) > DEFAULT_JSONL_MAX_LINE_BYTES:
        raise ValueError(f"{record_id}: embedded JSON exceeds the byte limit")
    try:
        return strict_json_loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{record_id}: embedded JSON is invalid") from exc
