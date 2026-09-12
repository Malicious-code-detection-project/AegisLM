"""Inference helpers for base models and adapters."""

from aegislm.inference.baseline import (
    GenerateResponse,
    make_static_response_generator,
    make_transformers_response_generator,
    run_baseline_inference,
)
from aegislm.inference.adapter import (
    adapter_directory_sha256,
    make_unsloth_response_generator,
)
from aegislm.inference.source import (
    SOURCE_EOS_TOKEN_IDS,
    SOURCE_GENERATION_PROTOCOL_VERSION,
    SOURCE_MAX_NEW_TOKENS,
    SOURCE_MAX_SEQ_LENGTH,
    SOURCE_PADDING_SIDE,
    SOURCE_PAD_TOKEN_ID,
    SOURCE_REASONING_EFFORT,
    SourceGenerateResponse,
    extract_harmony_final,
    make_openai_compatible_source_generator,
    run_source_inference,
    source_generation_protocol_metadata,
)

__all__ = [
    "GenerateResponse",
    "make_static_response_generator",
    "make_transformers_response_generator",
    "run_baseline_inference",
    "make_unsloth_response_generator",
    "adapter_directory_sha256",
    "SOURCE_EOS_TOKEN_IDS",
    "SOURCE_GENERATION_PROTOCOL_VERSION",
    "SOURCE_MAX_NEW_TOKENS",
    "SOURCE_MAX_SEQ_LENGTH",
    "SOURCE_PADDING_SIDE",
    "SOURCE_PAD_TOKEN_ID",
    "SOURCE_REASONING_EFFORT",
    "SourceGenerateResponse",
    "extract_harmony_final",
    "make_openai_compatible_source_generator",
    "run_source_inference",
    "source_generation_protocol_metadata",
]
