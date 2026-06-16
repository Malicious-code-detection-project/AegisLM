"""Evaluation and validation helpers for AegisLM."""

from aegislm.evaluation.harness import (
    Prediction,
    evaluate_predictions,
    load_jsonl,
    load_predictions,
    write_report_html,
    write_summary_json,
)
from aegislm.evaluation.validation import (
    ValidationResult,
    parse_model_output,
    validate_dataset_record,
    validate_model_output,
)

__all__ = [
    "Prediction",
    "ValidationResult",
    "evaluate_predictions",
    "load_jsonl",
    "load_predictions",
    "parse_model_output",
    "validate_dataset_record",
    "validate_model_output",
    "write_report_html",
    "write_summary_json",
]
