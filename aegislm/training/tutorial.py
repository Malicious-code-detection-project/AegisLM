"""Final-only GPT-OSS targets and native answer-end diagnostics."""

from __future__ import annotations

import ast
from collections.abc import Callable
import importlib
import json
from pathlib import Path
from typing import Any

from aegislm.artifacts import validate_artifact_output_location
from aegislm.datasets.source import SourceAssessmentRecord
from aegislm.training.source import harmony_training_messages
from aegislm.training.two_stage import digest

RESPONSE = "<|start|>assistant<|channel|>final<|message|>"
INSTRUCTION = "<|start|>user<|message|>"
RETURN_ID = 200002
EOS = (RETURN_ID, 199999)
SETTINGS: dict[str, Any] = {
    "max_seq_length": 4096,
    "batch_size": 1,
    "gradient_accumulation_steps": 32,
    "max_steps": 100,
    "learning_rate": 0.0002,
    "warmup_steps": 5,
    "weight_decay": 0.001,
    "lr_scheduler_type": "linear",
    "lora_r": 8,
    "lora_alpha": 16,
    "lora_dropout": 0,
    "seed": 3407,
    "eval_steps": 25,
}


def load_config(path: Path) -> dict[str, Any]:
    """Accept only the explicitly documented tutorial adaptation."""
    config: dict[str, Any] = json.loads(path.read_text())
    generation = config["generation"]
    if (
        config["recipe"] != "cc_tutorial_final_only_eos_v1"
        or config["training"] != SETTINGS
        or generation
        != {
            "max_new_tokens": 65536,
            "runtime_context_length": 131072,
            "max_time_seconds": 300,
            "sample_count": 2,
            "start_protocols": ["bare-assistant", "final-prefill"],
            "eos_token_ids": list(EOS),
            "answer_end_token_id": RETURN_ID,
            "force_eos": False,
        }
    ):
        raise ValueError("unsupported tutorial recipe or generation protocol")
    if digest(Path(config["source_config"])) != config["source_config_sha256"]:
        raise ValueError("source config changed")
    comparison = Path(config["reference_dir"]) / "comparison.json"
    if digest(comparison) != config["reference_comparison_sha256"]:
        raise ValueError("reference comparison changed")
    roots = [
        Path(config[key]).resolve()
        for key in ("output_dir", "adapter_dir", "checkpoint_dir")
    ]
    for root in roots:
        validate_artifact_output_location(root)
    if any(
        a.is_relative_to(b) or b.is_relative_to(a)
        for i, a in enumerate(roots)
        for b in roots[i + 1 :]
    ):
        raise ValueError("experiment storage roots must be disjoint")
    return config


def formatting_text(row: dict[str, Any], tokenizer: Any) -> str:
    """Render the cached template with a final channel, without inventing CoT."""
    record = SourceAssessmentRecord(str(row["id"]), tuple(row["messages"]))
    text: str = tokenizer.apply_chat_template(
        harmony_training_messages(record),
        tokenize=False,
        add_generation_prompt=False,
        reasoning_effort="low",
    )
    if RESPONSE not in text or not text.endswith("<|return|>"):
        raise ValueError("training serialization lacks final/return boundary")
    return text


def cpu_mask_function(tokenizer: Any, source: Path) -> Callable[..., Any]:
    """Use reviewed installed Zoo functions without importing GPU-only Unsloth.

    These functions come from the installed LGPL-3.0 Unsloth Zoo source; the
    original source and its hash remain the reference, not a vendored rewrite.
    """
    names = {
        "_longest_common_sublist",
        "_find_common_token_ids",
        "train_on_responses_only",
    }
    nodes = [
        node
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in nodes} != names:
        raise ValueError("unsupported installed masking implementation")
    namespace: dict[str, Any] = {"torch": importlib.import_module("torch")}
    body: list[ast.stmt] = list(nodes)
    exec(
        compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), namespace
    )
    result: Callable[..., Any] = namespace["train_on_responses_only"](
        None,
        tokenizer=tokenizer,
        instruction_part=INSTRUCTION,
        response_part=RESPONSE,
        return_function=True,
    )
    return result


def validate_final_labels(
    row: dict[str, Any],
    input_ids: list[int],
    labels: list[int],
    tokenizer: Any,
    maximum: int,
) -> int:
    """Require exactly the gold JSON+return tail and no prompt/header supervision."""
    tail = tokenizer.encode(
        row["messages"][-1]["content"] + "<|return|>", add_special_tokens=False
    )
    if not tail or tail[-1] != RETURN_ID or len(input_ids) > maximum:
        raise ValueError("missing return or overlength training sequence")
    if len(labels) != len(input_ids) or input_ids[-len(tail) :] != tail:
        raise ValueError("tokenized assistant tail differs from gold")
    expected = [-100] * (len(input_ids) - len(tail)) + tail
    if labels != expected:
        raise ValueError("final-only labels supervise unexpected prompt/header tokens")
    return len(tail)


def completion_metadata(
    ids: list[int], maximum: int, elapsed: float, max_time: float
) -> dict[str, Any]:
    """Distinguish native return from other EOS and exhausted resource bounds."""
    if not ids:
        reason = "empty"
    elif ids[-1] == RETURN_ID:
        reason = "answer_end"
    elif ids[-1] in EOS:
        reason = "endoftext"
    elif len(ids) >= maximum:
        reason = "token_limit"
    elif elapsed >= max_time:
        reason = "time_limit"
    else:
        reason = "other"
    return {
        "answer_end_present": bool(ids and ids[-1] == RETURN_ID),
        "engine_eos_present": bool(ids and ids[-1] in EOS),
        "completion_reason": reason,
        "token_count": len(ids),
        "at_token_cap": len(ids) >= maximum,
        "forced_eos": False,
    }


def model_features(row: dict[str, Any]) -> dict[str, list[int]]:
    """Keep tensor inputs separate from audited ID/text metadata."""
    result = {
        key: row[key] for key in ("input_ids", "attention_mask", "labels") if key in row
    }
    if not {"input_ids", "labels"}.issubset(result):
        raise ValueError("model features lack token IDs or labels")
    return result


def final_prefix_text(row: dict[str, Any], tokenizer: Any) -> str:
    """Open the supervised final boundary using no gold or invented reasoning."""
    if [m["role"] for m in row["messages"]] != ["system", "user"]:
        raise ValueError("final prefix must receive gold-free prompt messages")
    text: str = tokenizer.apply_chat_template(
        [*row["messages"], {"role": "assistant", "thinking": "", "content": ""}],
        tokenize=False,
        add_generation_prompt=False,
        reasoning_effort="low",
    )
    if not text.endswith(RESPONSE + "<|return|>"):
        raise ValueError("unexpected cached final prefix serialization")
    return text[: -len("<|return|>")]


def extended_rows(
    reference: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Retain all historical rows and append the new training recipe's result."""
    if len(reference) != 8 or any(row["model"] != "tutorial_adapter" for row in new):
        raise ValueError("unexpected comparison scope")
    return [dict(row) for row in reference] + [dict(row) for row in new]
