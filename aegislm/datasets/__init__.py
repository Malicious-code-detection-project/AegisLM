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
from aegislm.datasets.source import (
    SourceAssessmentRecord,
    load_source_gold,
    load_source_records,
    records_sha256,
    select_source_train_canary,
    select_stratified_canary,
    select_target_cwe_assessment_canary,
    source_code_sha256,
    validate_source_split_integrity,
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
    "SourceAssessmentRecord",
    "load_source_gold",
    "load_source_records",
    "records_sha256",
    "select_source_train_canary",
    "select_stratified_canary",
    "select_target_cwe_assessment_canary",
    "source_code_sha256",
    "validate_source_split_integrity",
]
