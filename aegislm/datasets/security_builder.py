"""Build safe AegisLM records from public security datasets.

This module intentionally does not produce LLaMA-Factory records directly.
AegisLM canonical records are safer to validate, split, audit, and later export
through ``scripts/export_llamafactory_dataset.py``.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from aegislm.datasets.validation import (
    DatasetValidationError,
    SafetyPolicyViolationError,
    validate_record,
    validate_safety_policy,
)
from aegislm.evaluation.validation import validate_dataset_record


DEFAULT_RETRIEVED_AT = "2026-07-01"
MAX_CONTEXT_CHARS = 6000
MAX_CODE_CHARS = 4000
MAX_WRITEUP_EXCERPT_CHARS = 1800
SOURCE_FILE_PATTERNS = ("*.py", "*.js", "*.ts", "*.java", "*.c", "*.cpp", "*.sh")

_SUSPICIOUS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("dynamic_execution", r"\b(eval|exec)\s*\("),
    ("process_execution", r"\b(os\.system|subprocess\.)"),
    ("network_access", r"\b(socket\.|requests\.|urllib\.|httpx\.)"),
    ("unsafe_deserialization", r"\b(pickle\.loads|pickle\.load|yaml\.load)\s*\("),
    ("encoded_payload_indicator", r"\b(base64|b64decode|fromhex)\b"),
    ("filesystem_modification", r"\b(open|write|unlink|remove|rmdir)\s*\("),
)

_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<key>\b[A-Za-z0-9_]*(?:password|api_key|client_secret)[A-Za-z0-9_]*\b)"
    r"\s*=\s*"
    r"(?P<value>[^\s,;)}\]]+)",
    flags=re.IGNORECASE,
)

_RISK_WORDS = {
    "취약": "high",
    "vulnerable": "high",
    "malicious": "high",
    "exploit": "high",
    "safe": "low",
    "안전": "low",
    "benign": "low",
}


class SecurityDatasetBuildError(Exception):
    """Raised when source data cannot be converted into safe records."""

    pass


SKIPPABLE_RECORD_ERRORS = (
    DatasetValidationError,
    SafetyPolicyViolationError,
    SecurityDatasetBuildError,
)


def build_record(
    *,
    record_id: str,
    source_name: str,
    source_url: str | None,
    license_or_terms: str | None,
    task: str,
    context: str,
    signals: dict[str, Any],
    summary: str,
    behavior_explanation: str,
    risk_level: str,
    behaviors: list[dict[str, str]] | None = None,
    attack_mapping: list[dict[str, str]] | None = None,
    recommendations: list[str] | None = None,
    limitations: list[str] | None = None,
    split: str = "train",
    safety_level: str = "redacted",
    notes: list[str] | None = None,
    source_type: str = "public_security_dataset",
    retrieved_at: str = DEFAULT_RETRIEVED_AT,
) -> dict[str, Any]:
    """Create and validate one AegisLM canonical dataset record."""
    redacted_context, secret_redaction_count = _redact_sensitive_assignments(context)
    record_signals = dict(signals)
    if secret_redaction_count:
        record_signals["redacted_secret_like_assignments"] = secret_redaction_count

    record = {
        "id": record_id,
        "source": {
            "type": source_type,
            "name": source_name,
            "url": source_url,
            "license_or_terms": license_or_terms,
            "retrieved_at": retrieved_at,
        },
        "input": {
            "task": task,
            "context": _truncate(_clean_text(redacted_context), MAX_CONTEXT_CHARS),
            "signals": record_signals,
        },
        "expected_output": {
            "summary": summary,
            "behavior_explanation": behavior_explanation,
            "risk_level": risk_level,
            "malware_like_behaviors": behaviors or [],
            "attack_mapping": attack_mapping or [],
            "recommendations": recommendations
            or [
                "Use deterministic analyzer findings and human review before making a final security decision.",
                "Prioritize remediation based on verified evidence, severity, and exposure.",
            ],
            "limitations": limitations
            or [
                "This record is derived from public dataset metadata or redacted excerpts.",
                "No executable malware sample or runtime behavior was analyzed.",
            ],
        },
        "metadata": {
            "split": split,
            "safety_level": safety_level,
            "contains_executable_payload": False,
            "notes": notes or [],
        },
    }

    _validate_safe_record(record)
    return record


def legacy_alpaca_to_aegislm_record(
    row: Mapping[str, Any],
    *,
    index: int,
    split: str = "train",
    source_name: str = "legacy security_sft_dataset.json",
) -> dict[str, Any]:
    """Convert an existing instruction/input/output row into AegisLM shape.

    The original output is not copied into the target answer. This prevents CTF
    write-up bodies, exploit recipes, or patch code from becoming supervised
    assistant output.
    """
    instruction = _string(row.get("instruction"))
    user_input = _string(row.get("input"))
    legacy_output = _string(row.get("output"))
    combined = "\n\n".join(part for part in [instruction, user_input] if part)
    risk_level = _infer_risk_level(" ".join([instruction, user_input, legacy_output]))
    signal_names = _scan_signal_names(user_input)
    signals = {
        "legacy_format": "alpaca",
        "legacy_instruction_present": bool(instruction),
        "legacy_input_present": bool(user_input),
        "legacy_output_redacted": bool(legacy_output),
        "suspicious_signal_names": signal_names,
    }

    return build_record(
        record_id=f"legacy-alpaca-{index:06d}-{_short_hash(combined)}",
        source_name=source_name,
        source_url=None,
        license_or_terms="Inherited from source datasets; verify before release.",
        task="summarize defensive security dataset row as structured AegisLM report",
        context=(
            "Legacy instruction/input row converted for defensive structured "
            f"reporting.\n\nInstruction:\n{instruction}\n\nInput excerpt:\n"
            f"{_truncate(user_input, MAX_CODE_CHARS)}"
        ),
        signals=signals,
        summary="Legacy security dataset row was normalized for defensive structured reporting.",
        behavior_explanation=(
            "The original row may contain useful security context, but the "
            "assistant target is converted to a conservative report instead of "
            "copying source answers, exploit narratives, or patch code."
        ),
        risk_level=risk_level,
        behaviors=_behaviors_from_signal_names(signal_names),
        recommendations=[
            "Review the original source provenance and license before training at scale.",
            "Prefer Project NuriLab normalized analyzer outputs when available.",
            "Do not use rows that require attack execution or payload details to be useful.",
        ],
        limitations=[
            "Original legacy output was intentionally redacted from the supervised target.",
            "Risk level is inferred from text and should not be treated as ground truth.",
        ],
        split=split,
        safety_level="redacted",
        notes=["Converted from legacy Alpaca-style dataset row."],
    )


def diversevul_to_aegislm_record(
    row: Mapping[str, Any],
    *,
    index: int,
    split: str = "train",
) -> dict[str, Any] | None:
    """Convert one DiverseVul row into a defensive AegisLM record."""
    code = _string(row.get("func"))
    if not code:
        return None

    is_vulnerable = int(row.get("target") or 0) == 1
    signal_names = _scan_signal_names(code)
    risk_level = "high" if is_vulnerable else ("medium" if signal_names else "low")
    label = "vulnerable" if is_vulnerable else "not labeled vulnerable"

    return build_record(
        record_id=f"diversevul-{index:06d}-{_short_hash(code)}",
        source_name="bstee615/diversevul",
        source_url="https://huggingface.co/datasets/bstee615/diversevul",
        license_or_terms="Hugging Face dataset card; verify license before release.",
        task="explain vulnerability label and static code risk signals",
        context=(
            f"DiverseVul function excerpt. Dataset label: {label}.\n\n"
            f"Code excerpt:\n{_truncate(code, MAX_CODE_CHARS)}"
        ),
        signals={
            "dataset": "DiverseVul",
            "target": int(is_vulnerable),
            "label": label,
            "suspicious_signal_names": signal_names,
            "code_excerpt_sha256": _sha256(code),
        },
        summary=f"DiverseVul sample is {label} according to the source label.",
        behavior_explanation=(
            "The record is used to train defensive explanation of static code "
            "risk signals. The label is dataset-provided and should be checked "
            "against deterministic analysis before operational use."
        ),
        risk_level=risk_level,
        behaviors=_behaviors_from_signal_names(signal_names)
        or [
            {
                "behavior": "Dataset-provided vulnerability label",
                "evidence": f"DiverseVul target label is {int(is_vulnerable)}.",
                "confidence": "medium",
            }
        ],
        recommendations=[
            "Validate the code with deterministic static analysis before using the label operationally.",
            "Use the model output as reviewer-facing explanation, not final vulnerability judgment.",
        ],
        limitations=[
            "Only a redacted/truncated function excerpt and dataset label are used.",
            "No exploitability proof or runtime behavior was analyzed.",
        ],
        split=split,
        safety_level="redacted",
        notes=["Converted from DiverseVul row."],
    )


def bigvul_to_aegislm_record(
    row: Mapping[str, Any],
    *,
    index: int,
    split: str = "train",
) -> dict[str, Any] | None:
    """Convert one BigVul patch-pair row without teaching patch code output."""
    before = _string(row.get("func_before"))
    after = _string(row.get("func_after"))
    if not before:
        return None

    signal_names = _scan_signal_names(before)
    has_patch = bool(after)

    return build_record(
        record_id=f"bigvul-{index:06d}-{_short_hash(before)}",
        source_name="DynaOuchebara/BigVul",
        source_url="https://huggingface.co/datasets/DynaOuchebara/BigVul",
        license_or_terms="Hugging Face dataset card; verify license before release.",
        task="explain vulnerable code context from a patch-pair dataset",
        context=(
            "BigVul vulnerable function excerpt. The source dataset contains a "
            f"corresponding fixed version: {has_patch}.\n\nVulnerable excerpt:\n"
            f"{_truncate(before, MAX_CODE_CHARS)}"
        ),
        signals={
            "dataset": "BigVul",
            "has_fixed_pair": has_patch,
            "suspicious_signal_names": signal_names,
            "vulnerable_excerpt_sha256": _sha256(before),
            "fixed_excerpt_sha256": _sha256(after) if after else None,
        },
        summary="BigVul patch-pair sample indicates vulnerable code that should be reviewed defensively.",
        behavior_explanation=(
            "The record preserves vulnerability context and patch-pair metadata "
            "without training the assistant to emit full replacement code."
        ),
        risk_level="high",
        behaviors=_behaviors_from_signal_names(signal_names)
        or [
            {
                "behavior": "Patch-pair vulnerability context",
                "evidence": "The source dataset provides vulnerable code paired with a fixed version.",
                "confidence": "medium",
            }
        ],
        recommendations=[
            "Inspect the vulnerable code path with deterministic static analysis.",
            "Use the fixed pair as private review evidence, but avoid emitting full patch code in model targets.",
        ],
        limitations=[
            "The fixed code body is not included in the supervised target.",
            "Patch-pair metadata alone does not prove exploitability in the deployed product.",
        ],
        split=split,
        safety_level="redacted",
        notes=[
            "Converted from BigVul row without copying patch code into target output."
        ],
    )


def cybersecurity_qa_to_aegislm_record(
    row: Mapping[str, Any],
    *,
    index: int,
    split: str = "train",
    dataset_name: str = "rezaduty/cybersecurity-qa-v2",
) -> dict[str, Any] | None:
    """Convert one public cybersecurity QA row without copying answer as target."""
    question, answer = _extract_qa_fields(row)
    if not question or not answer:
        return None

    combined = f"{question}\n\n{answer}"
    risk_level = _infer_risk_level(combined)

    return build_record(
        record_id=(
            f"cybersecurity-qa-{index:06d}-"
            f"{_short_hash(dataset_name + question + answer)}"
        ),
        source_name=dataset_name,
        source_url=f"https://huggingface.co/datasets/{dataset_name}",
        license_or_terms="Hugging Face dataset card; verify license before release.",
        task="summarize public cybersecurity QA as defensive analysis guidance",
        context=(
            "Public cybersecurity QA row converted for defensive training.\n\n"
            f"Question:\n{_truncate(question, 1600)}\n\n"
            f"Answer excerpt:\n{_truncate(answer, 2200)}"
        ),
        signals={
            "dataset": dataset_name,
            "question_sha256": _sha256(question),
            "answer_sha256": _sha256(answer),
            "answer_redacted_from_target": True,
            "suspicious_signal_names": _scan_signal_names(combined),
        },
        summary="Public cybersecurity QA row was normalized into defensive guidance context.",
        behavior_explanation=(
            "The source answer is available only as bounded context. The supervised "
            "target remains a conservative AegisLM report so broad QA text does not "
            "override the project-specific output contract."
        ),
        risk_level=risk_level,
        recommendations=[
            "Use the QA row as background context, not as a final security decision.",
            "Prefer deterministic analyzer signals and source provenance for operational decisions.",
            "Review licensing before scaling this source beyond local experiments.",
        ],
        limitations=[
            "The original QA answer is not copied into the supervised target.",
            "The dataset may include broad cybersecurity topics outside malware code analysis.",
        ],
        split=split,
        safety_level="redacted",
        notes=["Converted from public Cybersecurity QA row."],
    )


def ctf_writeup_to_aegislm_record(
    path: str | Path,
    *,
    base_dir: str | Path,
    index: int,
    split: str = "train",
) -> dict[str, Any] | None:
    """Convert one local CTF write-up into metadata/redacted-summary training data."""
    filepath = Path(path)
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not content.strip():
        return None

    rel_path = filepath.relative_to(base_dir).as_posix()
    title = _extract_markdown_title(content) or filepath.stem
    excerpt = _writeup_excerpt(content)
    risk_level = _infer_risk_level(content)
    signal_names = _scan_signal_names(content)

    return build_record(
        record_id=f"ctf-writeup-{index:06d}-{_short_hash(rel_path + content)}",
        source_name="local CTF write-up corpus",
        source_url=None,
        license_or_terms="Local dataset; verify provenance before release.",
        task="summarize CTF write-up metadata for defensive security learning",
        context=(
            "Local CTF write-up metadata and redacted excerpt.\n"
            f"Title: {title}\n"
            f"Relative path: {rel_path}\n\n"
            f"Redacted excerpt:\n{excerpt}"
        ),
        signals={
            "title": title,
            "relative_path": rel_path,
            "content_sha256": _sha256(content),
            "suspicious_signal_names": signal_names,
            "full_writeup_redacted_from_target": True,
        },
        summary="CTF write-up was converted as metadata and a bounded redacted excerpt.",
        behavior_explanation=(
            "The record can teach defensive summarization and provenance tracking "
            "without training the assistant to reproduce a challenge solution, "
            "payload, or exploitation procedure."
        ),
        risk_level=risk_level,
        behaviors=_behaviors_from_signal_names(signal_names),
        recommendations=[
            "Use CTF write-ups primarily as human reference or RAG evidence.",
            "Exclude rows that require procedural exploitation details to be useful.",
            "Keep original write-up files outside Git unless their license and safety are reviewed.",
        ],
        limitations=[
            "The full write-up body is intentionally not included in the supervised target.",
            "CTF scenarios may not reflect real-world operational risk.",
        ],
        split=split,
        safety_level="redacted",
        notes=["Converted from local CTF write-up metadata only."],
    )


def source_file_to_aegislm_record(
    path: str | Path,
    *,
    base_dir: str | Path,
    index: int,
    split: str = "train",
) -> dict[str, Any] | None:
    """Convert one local source file into a Project NuriLab-style record."""
    filepath = Path(path)
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not content.strip():
        return None

    signal_names = _scan_signal_names(content)
    rel_path = filepath.relative_to(base_dir).as_posix()
    risk_level = "medium" if signal_names else "low"

    return build_record(
        record_id=f"local-source-{index:06d}-{_short_hash(rel_path + content)}",
        source_name="local redacted source corpus",
        source_url=None,
        license_or_terms="Local dataset; verify provenance before release.",
        task="summarize normalized static-analysis signals for a local source file",
        context=(
            f"Local source file excerpt for defensive static analysis.\n"
            f"Relative path: {rel_path}\n\nCode excerpt:\n"
            f"{_truncate(content, MAX_CODE_CHARS)}"
        ),
        signals={
            "relative_path": rel_path,
            "suspicious_signal_names": signal_names,
            "line_count": len(content.splitlines()),
            "code_excerpt_sha256": _sha256(content),
        },
        summary="Local source file was normalized into defensive static-analysis metadata.",
        behavior_explanation=(
            "The record teaches the model to explain static signals extracted "
            "from source code while leaving final judgment to deterministic analyzers."
        ),
        risk_level=risk_level,
        behaviors=_behaviors_from_signal_names(signal_names),
        recommendations=[
            "Review highlighted static signals with Project NuriLab deterministic analyzers.",
            "Escalate only when multiple signals, data flow, or human review support the finding.",
        ],
        limitations=[
            "The record uses static source text only.",
            "No runtime execution, sandbox result, or full data-flow analysis is included.",
        ],
        split=split,
        safety_level="redacted",
        notes=["Converted from local source file corpus."],
    )


def extract_zip_archive(zip_path: str | Path, extract_root: str | Path) -> Path:
    """Safely extract one ZIP archive below ``extract_root``.

    Members that would escape the destination directory are rejected before any
    extraction occurs.
    """
    archive_path = Path(zip_path)
    destination = Path(extract_root) / archive_path.stem
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()

    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_target = (destination / member.filename).resolve()
            if not _is_relative_to(member_target, resolved_destination):
                raise SecurityDatasetBuildError(
                    f"Unsafe ZIP member path in {archive_path}: {member.filename}"
                )
        archive.extractall(destination)

    return destination


def load_ctf_writeup_records(
    writeup_dir: str | Path,
    *,
    max_records: int,
    split: str = "train",
) -> list[dict[str, Any]]:
    """Load local Markdown CTF write-ups as safe AegisLM records."""
    base_dir = Path(writeup_dir)
    if not base_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for filepath in sorted(base_dir.rglob("*.md")):
        if reached_record_limit(records, max_records):
            break
        if _should_skip_writeup(filepath, base_dir):
            continue
        try:
            record = ctf_writeup_to_aegislm_record(
                filepath,
                base_dir=base_dir,
                index=len(records),
                split=split,
            )
        except SKIPPABLE_RECORD_ERRORS:
            continue
        if record:
            records.append(record)
    return records


def load_source_corpus_records(
    source_dir: str | Path,
    *,
    max_records: int,
    split: str = "train",
) -> list[dict[str, Any]]:
    """Load source files below a directory as local source corpus records."""
    base_dir = Path(source_dir)
    if not base_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for filepath in _iter_source_files(base_dir):
        if reached_record_limit(records, max_records):
            break
        try:
            record = source_file_to_aegislm_record(
                filepath,
                base_dir=base_dir,
                index=len(records),
                split=split,
            )
        except SKIPPABLE_RECORD_ERRORS:
            continue
        if record:
            records.append(record)
    return records


def load_zip_source_records(
    zip_source_dir: str | Path,
    *,
    zip_extract_dir: str | Path,
    max_records: int,
    split: str = "train",
) -> list[dict[str, Any]]:
    """Extract local ZIP archives safely and convert contained source files."""
    source_dir = Path(zip_source_dir)
    if not source_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for archive_path in sorted(source_dir.rglob("*.zip")):
        if reached_record_limit(records, max_records):
            break
        extracted_dir = extract_zip_archive(archive_path, zip_extract_dir)
        remaining = remaining_record_limit(records, max_records)
        extracted_records = load_source_corpus_records(
            extracted_dir,
            max_records=remaining,
            split=split,
        )
        records.extend(extracted_records)
    return records


def load_legacy_alpaca_json(
    path: str | Path, *, split: str = "train"
) -> list[dict[str, Any]]:
    """Load a legacy Alpaca JSON/JSONL file and convert records."""
    rows = _load_json_or_jsonl(path)
    records = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        try:
            records.append(
                legacy_alpaca_to_aegislm_record(row, index=index, split=split)
            )
        except SKIPPABLE_RECORD_ERRORS:
            continue
    return records


def write_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> None:
    """Write records as JSONL."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def reached_record_limit(records: list[dict[str, Any]], max_records: int) -> bool:
    """Return whether a non-negative max record limit has been reached."""
    return max_records >= 0 and len(records) >= max_records


def remaining_record_limit(records: list[dict[str, Any]], max_records: int) -> int:
    """Return remaining quota, preserving negative values as unlimited."""
    if max_records < 0:
        return max_records
    return max_records - len(records)


def split_records(
    records: list[dict[str, Any]],
    *,
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Deterministically split records into train/validation/test.

    The function copies records before mutating ``metadata.split`` so callers can
    keep the original list unchanged. Splitting is deterministic for reproducible
    experiment comparisons.
    """
    _validate_split_ratios(train_ratio, validation_ratio, test_ratio)

    shuffled = [deepcopy(record) for record in records]
    rng = random.Random(seed)
    shuffled.sort(key=lambda record: str(record.get("id", "")))
    rng.shuffle(shuffled)

    total = len(shuffled)
    train_count = int(total * train_ratio)
    validation_count = int(total * validation_ratio)

    # Keep at least one test item when possible and ratios request a test split.
    if total >= 3 and test_ratio > 0 and train_count + validation_count >= total:
        validation_count = max(0, validation_count - 1)

    split_map = {
        "train": shuffled[:train_count],
        "validation": shuffled[train_count : train_count + validation_count],
        "test": shuffled[train_count + validation_count :],
    }

    for split_name, split_records_ in split_map.items():
        for record in split_records_:
            metadata = record.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["split"] = split_name
            _validate_safe_record(record)

    return split_map


def write_split_jsonl(
    split_map: Mapping[str, list[dict[str, Any]]],
    output_dir: str | Path,
    *,
    prefix: str = "aegislm_security",
) -> dict[str, Path]:
    """Write train/validation/test JSONL files and return their paths."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for split_name in ("train", "validation", "test"):
        path = destination / f"{prefix}_{split_name}.jsonl"
        write_jsonl(split_map.get(split_name, []), path)
        paths[split_name] = path
    return paths


def _validate_safe_record(record: dict[str, Any]) -> None:
    validate_record(record)
    validate_safety_policy(record)
    result = validate_dataset_record(record)
    if not result.ok:
        raise SecurityDatasetBuildError("; ".join(result.errors))


def _load_json_or_jsonl(path: str | Path) -> list[Any]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return parsed
    raise SecurityDatasetBuildError(
        f"{source} must contain a JSON array or JSONL records."
    )


def _validate_split_ratios(
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> None:
    ratios = (train_ratio, validation_ratio, test_ratio)
    if any(ratio < 0 for ratio in ratios):
        raise SecurityDatasetBuildError("Split ratios must be non-negative.")
    total = sum(ratios)
    if not 0.999 <= total <= 1.001:
        raise SecurityDatasetBuildError(
            f"Split ratios must sum to 1.0, got {total:.4f}."
        )


def _behaviors_from_signal_names(signal_names: list[str]) -> list[dict[str, str]]:
    behaviors = []
    for signal_name in signal_names:
        behaviors.append(
            {
                "behavior": signal_name.replace("_", " "),
                "evidence": f"Static text scan matched signal '{signal_name}'.",
                "confidence": "medium",
            }
        )
    return behaviors


def _scan_signal_names(text: str) -> list[str]:
    return [
        name
        for name, pattern in _SUSPICIOUS_PATTERNS
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def _infer_risk_level(text: str) -> str:
    lowered = text.lower()
    for keyword, risk in _RISK_WORDS.items():
        if keyword in lowered:
            return risk
    return "unknown"


def _redact_sensitive_assignments(value: str) -> tuple[str, int]:
    redaction_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return f"{match.group('key')} = [REDACTED_SECRET]"

    return _SECRET_ASSIGNMENT_PATTERN.sub(replace, value), redaction_count


def _extract_qa_fields(row: Mapping[str, Any]) -> tuple[str, str]:
    messages = row.get("messages")
    if isinstance(messages, list):
        question = _message_content(messages, "user")
        answer = _message_content(messages, "assistant")
        if question and answer:
            return question, answer

    vars_value = row.get("vars")
    if isinstance(vars_value, Mapping):
        question = _string(vars_value.get("question"))
        answer = _string(vars_value.get("answer"))
        if question and answer:
            return question, answer

    question = _string(row.get("question") or row.get("prompt"))
    answer_value = row.get("answers")
    if answer_value is None:
        answer_value = row.get("answer") or row.get("response")
    answer = _string_answer(answer_value)
    return question, answer


def _message_content(messages: list[Any], role: str) -> str:
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        if _string(message.get("role")).lower() == role:
            return _string(message.get("content"))
    return ""


def _string_answer(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_string(item) for item in value if _string(item)).strip()
    if isinstance(value, Mapping):
        for key in ("text", "answer", "content", "value"):
            if key in value:
                return _string_answer(value[key])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _string(value)


def _extract_markdown_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].replace("**", "").strip()
    return ""


def _writeup_excerpt(content: str) -> str:
    cleaned_lines = []
    in_fence = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _looks_like_payload_line(stripped):
            cleaned_lines.append("[REDACTED technical procedure or payload line]")
            continue
        cleaned_lines.append(line)
    return _truncate(_clean_text("\n".join(cleaned_lines)), MAX_WRITEUP_EXCERPT_CHARS)


def _looks_like_payload_line(line: str) -> bool:
    if not line:
        return False
    lowered = line.lower()
    payload_indicators = (
        "curl ",
        "nc ",
        "netcat",
        "msfconsole",
        "meterpreter",
        "python -c",
        "bash -c",
        "chmod +x",
        "reverse shell",
        "step-by-step",
        "step by step",
        "payload",
    )
    return any(indicator in lowered for indicator in payload_indicators)


def _should_skip_writeup(filepath: Path, base_dir: Path) -> bool:
    filename = filepath.stem.lower()
    ignored_names = ("contributing", "license", "summary", "security", "changelog")
    if filename in ignored_names or filename.startswith("readme-"):
        return True

    try:
        relative_path = filepath.relative_to(base_dir)
    except ValueError:
        return True
    if filename == "readme" and len(relative_path.parts) <= 2:
        return True
    return False


def _iter_source_files(base_dir: Path) -> Iterable[Path]:
    for pattern in SOURCE_FILE_PATTERNS:
        yield from sorted(base_dir.rglob(pattern))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _clean_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.replace("\x00", "")).strip()


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n[TRUNCATED]"


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _short_hash(value: str) -> str:
    return _sha256(value)[:12]
