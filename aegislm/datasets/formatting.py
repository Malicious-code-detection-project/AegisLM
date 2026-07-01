"""Dataset formatting helpers for supervised fine-tuning (SFT)."""

from __future__ import annotations

import json
from typing import Any, Mapping, TypedDict, Literal

from aegislm.prompts import format_baseline_prompt
from aegislm.datasets.validation import validate_record, validate_safety_policy
from aegislm.evaluation.validation import validate_dataset_record


class SFTPromptMessage(TypedDict):
    """Chat-style prompt message for SFT training."""

    role: Literal["system", "user", "assistant"]
    content: str


class SFTFormattingError(Exception):
    """Base exception for SFT formatting and validation errors."""

    pass


class SFTValidationError(SFTFormattingError):
    """Raised when a record fails schema or safety policy checks for SFT."""

    pass


class SFTSplitError(SFTFormattingError):
    """Raised when a record has a split that is not allowed for training."""

    pass


class SFTSafetyLevelError(SFTFormattingError):
    """Raised when a record's safety level is restricted."""

    pass


def check_sft_eligibility(record: Mapping[str, Any]) -> None:
    """Ensure a dataset record is eligible for SFT training.

    Verifies that the record:
    1. Passes standard JSON schema validation.
    2. Passes basic safety policy (no executable payload, no sensitive credential leaks).
    3. Passes evaluation validation (no unsafe offensive instructions/guidance).
    4. Has a safety level that is not "restricted".
    5. Belongs to a split suitable for training (e.g., "train" or "validation")
       and is NOT in a held-out/test split ("test" or "fixture").

    Args:
        record: The dataset record to verify.

    Raises:
        SFTValidationError: If schema, safety policy, or evaluation validation fails.
        SFTSafetyLevelError: If the safety level is restricted.
        SFTSplitError: If the split is not allowed for training.
    """
    record_id = record.get("id", "unknown-id")

    # 1. JSON Schema validation
    try:
        validate_record(dict(record))
    except Exception as e:
        raise SFTValidationError(
            f"Record {record_id} failed schema validation: {e}"
        ) from e

    # 2. Safety policy validation (executable payloads, credentials)
    try:
        validate_safety_policy(dict(record))
    except Exception as e:
        raise SFTValidationError(
            f"Record {record_id} failed safety policy validation: {e}"
        ) from e

    # 3. Evaluation validation (unsafe guidance patterns check)
    eval_res = validate_dataset_record(dict(record))
    if not eval_res.ok:
        errors_str = ", ".join(eval_res.errors)
        raise SFTValidationError(
            f"Record {record_id} failed evaluation/safety validation: {errors_str}"
        )

    # 4. Check safety level
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        raise SFTValidationError(f"Record {record_id} has invalid metadata structure.")

    safety_level = metadata.get("safety_level")
    if safety_level == "restricted":
        raise SFTSafetyLevelError(
            f"Record {record_id} safety level is 'restricted', which is excluded from training."
        )

    # 5. Check split
    split = metadata.get("split")
    if split in ("test", "fixture"):
        raise SFTSplitError(
            f"Record {record_id} belongs to a held-out split '{split}' and must be excluded from training."
        )
    if split not in ("train", "validation"):
        raise SFTSplitError(
            f"Record {record_id} split '{split}' is not allowed for SFT training (allowed: train, validation)."
        )


def format_sft_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Format one AegisLM dataset record into a chat template SFT structure.

    The output format is:
    {
        "messages": [
            {"role": "system", "content": ...},
            {"role": "user", "content": ...},
            {"role": "assistant", "content": ...}
        ]
    }

    The assistant content contains the expected output serialized as a clean,
    deterministic, key-sorted, pretty-printed JSON string conforming to
    OUTPUT_CONTRACT_SCHEMA.

    Args:
        record: The dataset record to format.

    Returns:
        A dictionary with a "messages" key containing the formatted conversation.

    Raises:
        SFTFormattingError: If the record fails validation or split eligibility checks.
    """
    check_sft_eligibility(record)

    # Reuse format_baseline_prompt to keep prompt formatting logic perfectly aligned.
    # This guarantees we don't introduce prompt mismatch between baseline and SFT.
    messages = format_baseline_prompt(record)

    expected_output = record.get("expected_output")
    # Pretty print expected output JSON identically to output contract requirements
    assistant_content = json.dumps(
        expected_output, ensure_ascii=False, indent=2, sort_keys=True
    )

    # Construct complete chat format
    sft_messages: list[SFTPromptMessage] = [
        {"role": m["role"], "content": m["content"]} for m in messages
    ]
    sft_messages.append({"role": "assistant", "content": assistant_content})

    return {"messages": sft_messages}


def format_sft_dataset(
    records: list[dict[str, Any]],
    ignore_errors: bool = False,
) -> list[dict[str, Any]]:
    """Format a batch of dataset records for SFT.

    Args:
        records: A list of raw dataset records.
        ignore_errors: If True, records that fail eligibility checks or validation
            are silently skipped. If False, raises the corresponding SFTFormattingError.

    Returns:
        A list of formatted SFT chat dictionaries.

    Raises:
        SFTFormattingError: If ignore_errors is False and any record is invalid.
    """
    formatted_records = []
    for record in records:
        try:
            formatted = format_sft_record(record)
            formatted_records.append(formatted)
        except SFTFormattingError:
            if not ignore_errors:
                raise
    return formatted_records
