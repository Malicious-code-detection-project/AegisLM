"""Dataset formatting and validation helpers."""

from aegislm.datasets.validation import (
    ContaminationError,
    DatasetValidationError,
    SafetyPolicyViolationError,
    check_contamination,
    validate_record,
    validate_safety_policy,
)
from aegislm.datasets.formatting import (
    SFTFormattingError,
    SFTSafetyLevelError,
    SFTSplitError,
    SFTValidationError,
    check_sft_eligibility,
    format_sft_dataset,
    format_sft_record,
)

__all__ = [
    "validate_record",
    "validate_safety_policy",
    "check_contamination",
    "DatasetValidationError",
    "SafetyPolicyViolationError",
    "ContaminationError",
    "format_sft_record",
    "format_sft_dataset",
    "check_sft_eligibility",
    "SFTFormattingError",
    "SFTValidationError",
    "SFTSplitError",
    "SFTSafetyLevelError",
]
