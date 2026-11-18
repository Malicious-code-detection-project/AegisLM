"""Unsloth adapter inference helpers for Phase E/F verification and evaluation."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aegislm.artifacts import (
    load_bounded_json_object,
    validate_artifact_output_location,
    validate_no_symlink_components,
)
from aegislm.inference.baseline import GenerateResponse
from aegislm.inference.source import (
    SOURCE_EOS_TOKEN_IDS,
    SOURCE_MAX_NEW_TOKENS,
    SOURCE_MAX_SEQ_LENGTH,
    SOURCE_PADDING_SIDE,
    SOURCE_PAD_TOKEN_ID,
    SOURCE_REASONING_EFFORT,
    extract_harmony_final,
    source_generation_protocol_metadata,
)
from aegislm.prompts import PromptMessage


def make_unsloth_response_generator(
    *,
    adapter_path: str | Path | None,
    max_seq_length: int = SOURCE_MAX_SEQ_LENGTH,
    max_new_tokens: int = SOURCE_MAX_NEW_TOKENS,
    temperature: float = 0.0,
    cache_dir: str | Path | None = "models/cache",
    revision: str | None = None,
    expected_base_model_id: str | None = None,
) -> GenerateResponse:
    """Build a provenance-bound Unsloth base or persisted-adapter generator."""
    if cache_dir is None:
        raise ValueError("an explicit Git-safe model cache directory is required")
    validated_cache_dir = Path(cache_dir)
    validate_artifact_output_location(validated_cache_dir)
    validated_cache_dir.mkdir(parents=True, exist_ok=True)
    if validated_cache_dir.is_symlink() or not validated_cache_dir.is_dir():
        raise ValueError("model cache must be a real directory")
    if revision is None and expected_base_model_id is None:
        if adapter_path is None:
            raise ValueError("legacy Unsloth inference requires an adapter path")
        return _make_legacy_unsloth_response_generator(
            adapter_path=Path(adapter_path),
            max_seq_length=max_seq_length,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            cache_dir=validated_cache_dir,
        )
    if revision is None or expected_base_model_id is None:
        raise ValueError(
            "pinned Unsloth inference requires both revision and base model ID"
        )
    protocol = source_generation_protocol_metadata(
        backend="unsloth",
        mode="raw",
        max_new_tokens=max_new_tokens,
        max_seq_length=max_seq_length,
        temperature=temperature,
    )
    if not revision:
        raise ValueError("a pinned base model revision is required")
    base_model_id = expected_base_model_id
    if not isinstance(base_model_id, str) or not base_model_id:
        raise ValueError("an expected base model ID is required")

    local_adapter_path = Path(adapter_path) if adapter_path is not None else None
    adapter_artifact_sha256: str | None = None
    adapter_sha256: str | None = None
    tokenizer_contract_digest: str
    if local_adapter_path is not None:
        # Read and hash every adapter file before importing/loading any model.
        # The same complete tree digest is checked around every response below.
        adapter_artifact_sha256 = adapter_directory_sha256(local_adapter_path)
        validate_unsloth_runtime_identity(
            adapter_path=local_adapter_path,
            expected_base_model_id=base_model_id,
            expected_revision=revision,
            resolved_model_id=base_model_id,
            resolved_revision=revision,
        )
        weights = local_adapter_path / "adapter_model.safetensors"
        if not weights.is_file() or weights.is_symlink():
            raise ValueError("adapter artifact requires regular adapter weights")
        adapter_sha256 = _file_sha256(weights)

    transformers = importlib.import_module("transformers")
    AutoTokenizer = transformers.AutoTokenizer
    base_tokenizer = AutoTokenizer.from_pretrained(
        base_model_id,
        revision=revision,
        cache_dir=str(validated_cache_dir) if validated_cache_dir else None,
    )
    base_tokenizer.padding_side = SOURCE_PADDING_SIDE
    contract = SimpleNamespace(
        padding_side=SOURCE_PADDING_SIDE,
        pad_token_id=SOURCE_PAD_TOKEN_ID,
        eos_token_ids=SOURCE_EOS_TOKEN_IDS,
    )
    if local_adapter_path is not None:
        from aegislm.training.source import load_persisted_source_tokenizer

        tokenizer, tokenizer_contract_digest = load_persisted_source_tokenizer(
            AutoTokenizer, local_adapter_path, base_tokenizer, contract
        )
    else:
        tokenizer = base_tokenizer
        from aegislm.training.source import tokenizer_contract_sha256 as fingerprint

        tokenizer_contract_digest = fingerprint(tokenizer, contract)

    unsloth = importlib.import_module("unsloth")
    FastLanguageModel = unsloth.FastLanguageModel
    print(f"[INFO] Loading pinned Unsloth base model: {base_model_id}")
    model, _runtime_tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model_id,
        max_seq_length=max_seq_length,
        dtype=None,  # Auto-detection
        load_in_4bit=True,
        cache_dir=str(validated_cache_dir) if validated_cache_dir else None,
        revision=revision,
    )
    resolved_model_id = str(getattr(model.config, "_name_or_path", ""))
    resolved_revision = getattr(model.config, "_commit_hash", None)
    if local_adapter_path is not None:
        validate_unsloth_runtime_identity(
            adapter_path=local_adapter_path,
            expected_base_model_id=base_model_id,
            expected_revision=revision,
            resolved_model_id=resolved_model_id,
            resolved_revision=resolved_revision,
        )
        peft = importlib.import_module("peft")
        model = peft.PeftModel.from_pretrained(
            model, str(local_adapter_path), is_trainable=False
        )
    elif resolved_model_id != base_model_id or resolved_revision != revision:
        raise RuntimeError("resolved base model identity does not match the request")
    tokenizer.padding_side = SOURCE_PADDING_SIDE
    if tokenizer.pad_token_id != SOURCE_PAD_TOKEN_ID:
        raise ValueError(
            f"tokenizer pad_token_id mismatch: expected {SOURCE_PAD_TOKEN_ID}"
        )
    if tokenizer.eos_token_id not in SOURCE_EOS_TOKEN_IDS:
        raise ValueError("tokenizer eos_token_id is outside the canonical EOS set")

    # Enable native 2x faster inference
    FastLanguageModel.for_inference(model)

    def generate_response(messages: list[PromptMessage]) -> str:
        if local_adapter_path is not None and (
            adapter_directory_sha256(local_adapter_path) != adapter_artifact_sha256
        ):
            raise RuntimeError("adapter artifact changed before generation")
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            padding=True,
            return_tensors="pt",
            return_dict=True,
            reasoning_effort=SOURCE_REASONING_EFFORT,
        )
        inputs = inputs.to("cuda")

        generation_kwargs: dict[str, Any] = {
            **inputs,
            "max_new_tokens": max_new_tokens,
            "use_cache": True,
            "do_sample": False,
            "pad_token_id": SOURCE_PAD_TOKEN_ID,
            "eos_token_id": list(SOURCE_EOS_TOKEN_IDS),
        }
        output_ids = model.generate(**generation_kwargs)
        if local_adapter_path is not None and (
            adapter_directory_sha256(local_adapter_path) != adapter_artifact_sha256
        ):
            raise RuntimeError("adapter artifact changed during generation")
        input_length = inputs["input_ids"].shape[1]
        generated_token_ids = output_ids[0][input_length:].tolist()
        trimmed_ids, finish_reason, eos_token_id = _trim_at_first_eos(
            generated_token_ids,
            max_new_tokens=max_new_tokens,
        )
        raw_generation = tokenizer.decode(trimmed_ids, skip_special_tokens=False)
        clean = tokenizer.decode(trimmed_ids, skip_special_tokens=True)
        scoreable_output = extract_harmony_final(raw_generation, fallback=clean)
        setattr(
            generate_response,
            "aegislm_last_generation",
            {
                "raw_generation": raw_generation,
                "scoreable_output": scoreable_output,
                "generated_token_count": len(trimmed_ids),
                "finish_reason": finish_reason,
                "eos_token_id": eos_token_id,
                "generated_token_ids": trimmed_ids,
                "harmony_prefix": raw_generation.startswith(
                    "<|channel|>analysis<|message|>"
                ),
                "harmony_final": "<|channel|>final<|message|>" in raw_generation,
            },
        )
        return scoreable_output

    torch = importlib.import_module("torch")
    properties = torch.cuda.get_device_properties(0)
    hardware = {
        "gpu_name": properties.name,
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "torch_cuda": torch.version.cuda,
    }
    hardware_signature = hashlib.sha256(
        json.dumps(hardware, sort_keys=True).encode()
    ).hexdigest()
    setattr(
        generate_response,
        "aegislm_provenance",
        {
            "resolved_model_id": resolved_model_id,
            "base_model_revision": resolved_revision,
            "adapter_artifact_sha256": adapter_artifact_sha256,
            "adapter_sha256": adapter_sha256,
            "tokenizer_contract_sha256": tokenizer_contract_digest,
            "hardware_signature": hardware_signature,
            "hardware": hardware,
            **protocol,
        },
    )
    return generate_response


def _make_legacy_unsloth_response_generator(
    *,
    adapter_path: Path,
    max_seq_length: int,
    max_new_tokens: int,
    temperature: float,
    cache_dir: str | Path | None,
) -> GenerateResponse:
    """Preserve the Phase-D/E CLI without granting source-v2 comparability."""
    if max_seq_length <= 0 or max_new_tokens <= 0 or temperature < 0:
        raise ValueError("legacy generation limits and temperature must be valid")
    artifact_digest = adapter_directory_sha256(adapter_path)
    unsloth = importlib.import_module("unsloth")
    FastLanguageModel = unsloth.FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter_path),
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    if adapter_directory_sha256(adapter_path) != artifact_digest:
        raise RuntimeError("legacy adapter artifact changed while loading")
    FastLanguageModel.for_inference(model)

    def generate_response(messages: list[PromptMessage]) -> str:
        if adapter_directory_sha256(adapter_path) != artifact_digest:
            raise RuntimeError("legacy adapter artifact changed before generation")
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to("cuda")
        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "use_cache": True,
            "do_sample": temperature > 0.0,
        }
        if temperature > 0.0:
            generation_kwargs["temperature"] = temperature
        output_ids = model.generate(input_ids=inputs, **generation_kwargs)
        if adapter_directory_sha256(adapter_path) != artifact_digest:
            raise RuntimeError("legacy adapter artifact changed during generation")
        input_length = inputs.shape[-1]
        generated_ids = output_ids[0][input_length:]
        decoded = tokenizer.decode(generated_ids, skip_special_tokens=True)
        if not isinstance(decoded, str):
            raise TypeError("legacy Unsloth tokenizer returned non-text output")
        return decoded

    setattr(
        generate_response,
        "aegislm_provenance",
        {
            "legacy_unpinned_inference": True,
            "adapter_artifact_sha256": artifact_digest,
        },
    )
    return generate_response


def _trim_at_first_eos(
    token_ids: list[int], *, max_new_tokens: int
) -> tuple[list[int], str, int | None]:
    for index, token_id in enumerate(token_ids):
        if token_id in SOURCE_EOS_TOKEN_IDS:
            return token_ids[: index + 1], "eos", token_id
    finish_reason = "length" if len(token_ids) >= max_new_tokens else "unknown"
    return list(token_ids), finish_reason, None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def adapter_directory_sha256(path: Path) -> str:
    """Hash the complete local adapter tree without following symlinks."""
    validate_no_symlink_components(path, description="adapter artifact")
    try:
        root_stat = path.lstat()
    except OSError as exc:
        raise ValueError(f"adapter artifact is unavailable: {path}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("adapter artifact must be a real directory")

    digest = hashlib.sha256()
    file_count = 0
    for directory, directory_names, file_names in os.walk(
        path,
        topdown=True,
        onerror=_raise_adapter_walk_error,
        followlinks=False,
    ):
        directory_path = Path(directory)
        for name in sorted(directory_names):
            candidate = directory_path / name
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError("adapter artifact directory contains an unsafe entry")
        directory_names.sort()
        for name in sorted(file_names):
            candidate = directory_path / name
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ValueError("adapter artifact directory contains an unsafe entry")
            relative = candidate.relative_to(path).as_posix()
            digest.update(relative.encode())
            digest.update(b"\0")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(candidate, flags)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise ValueError("adapter artifact directory contains an unsafe entry")
            with os.fdopen(descriptor, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\n")
            file_count += 1
    if file_count == 0:
        raise ValueError("adapter artifact directory is empty")
    return digest.hexdigest()


def _raise_adapter_walk_error(error: OSError) -> None:
    raise ValueError(
        "adapter artifact directory could not be read completely"
    ) from error


def validate_unsloth_runtime_identity(
    *,
    adapter_path: Path,
    expected_base_model_id: str,
    expected_revision: str | None,
    resolved_model_id: str,
    resolved_revision: str | None,
) -> None:
    """Require requested, adapter-declared, and resolved base identity to agree."""
    if not expected_revision:
        raise ValueError("a pinned base model revision is required")
    if adapter_path.is_dir():
        config_path = adapter_path / "adapter_config.json"
        try:
            adapter_config, _digest = load_bounded_json_object(
                config_path, description="local adapter config"
            )
        except ValueError as exc:
            raise ValueError(f"invalid local adapter config: {config_path}") from exc
        if (
            adapter_config.get("base_model_name_or_path") != expected_base_model_id
            or adapter_config.get("revision") != expected_revision
        ):
            raise ValueError(
                "local adapter base model or revision does not match the request"
            )
    if resolved_model_id != expected_base_model_id:
        raise RuntimeError(
            f"resolved model mismatch: expected {expected_base_model_id}, "
            f"got {resolved_model_id}"
        )
    if resolved_revision is None:
        raise RuntimeError("runtime did not expose a resolved base model revision")
    if resolved_revision != expected_revision:
        raise RuntimeError(
            f"resolved revision mismatch: expected {expected_revision}, "
            f"got {resolved_revision}"
        )
