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
    validate_source_assessment,
)
from aegislm.evaluation.source import (
    bind_source_comparison_inputs,
    compare_source_summaries,
    evaluate_source_predictions,
    validate_source_gold,
    write_source_report_html,
)

__all__ = [
    "Prediction",
    "ValidationResult",
    "bind_source_comparison_inputs",
    "evaluate_predictions",
    "load_jsonl",
    "load_predictions",
    "parse_model_output",
    "validate_dataset_record",
    "validate_model_output",
    "validate_source_assessment",
    "compare_source_summaries",
    "evaluate_source_predictions",
    "validate_source_gold",
    "write_source_report_html",
    "write_report_html",
    "write_summary_json",
]
