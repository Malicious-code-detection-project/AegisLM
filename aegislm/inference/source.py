"""Inference runners for source-v2 base and adapter comparisons."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import tempfile
import time
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from aegislm.artifacts import strict_json_loads, validate_artifact_path_plan
from aegislm.datasets.source import load_source_records
from aegislm.prompts import PromptMessage
from aegislm.schemas import SOURCE_ASSESSMENT_SCHEMA

SourceGenerateResponse = Callable[[list[PromptMessage]], str]

_HARMONY_FINAL_MARKER = "<|channel|>final<|message|>"
_HARMONY_RETURN_MARKER = "<|return|>"
_HARMONY_END_OF_TEXT_MARKER = "<|endoftext|>"

SOURCE_GENERATION_PROTOCOL_VERSION = "aegislm.source-v2-harmony-generation.v1"
SOURCE_REASONING_EFFORT = "low"
SOURCE_PADDING_SIDE = "left"
SOURCE_PAD_TOKEN_ID = 200017
SOURCE_EOS_TOKEN_IDS = (200002, 199999)
SOURCE_MAX_NEW_TOKENS = 512
SOURCE_MAX_SEQ_LENGTH = 2048
MAX_OPENAI_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_OPENAI_CONTENT_BYTES = 1024 * 1024


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent bearer credentials from following redirects to another origin."""

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def extract_harmony_final(raw_text: str, *, fallback: str | None = None) -> str:
    """Extract only GPT-OSS Harmony's final channel from decoded generation."""
    if _HARMONY_FINAL_MARKER not in raw_text:
        return fallback if fallback is not None else raw_text
    # The first final-channel marker is structural. A later identical string may
    # legitimately occur inside a JSON value and must not replace that boundary.
    final = raw_text.split(_HARMONY_FINAL_MARKER, 1)[1].rstrip()
    for terminator in (_HARMONY_RETURN_MARKER, _HARMONY_END_OF_TEXT_MARKER):
        if final.endswith(terminator):
            final = final[: -len(terminator)]
            break
    return final.strip()


def source_generation_protocol_metadata(
    *,
    backend: str,
    mode: str,
    max_new_tokens: int,
    max_seq_length: int,
    temperature: float,
) -> dict[str, Any]:
    """Return a digest-bound description of the effective source protocol."""
    if not isinstance(backend, str) or not backend:
        raise ValueError("backend must be a non-empty string")
    if not isinstance(mode, str) or not mode:
        raise ValueError("mode must be a non-empty string")
    if type(max_new_tokens) is not int or max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")
    if type(max_seq_length) is not int or max_seq_length <= 0:
        raise ValueError("max_seq_length must be positive")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature)
        or temperature < 0
    ):
        raise ValueError("temperature must be a finite non-negative number")
    if backend == "unsloth":
        if mode != "raw":
            raise ValueError("Unsloth source inference only supports raw mode")
        if temperature != 0.0:
            raise ValueError("canonical Unsloth source inference must be deterministic")
        if max_new_tokens != SOURCE_MAX_NEW_TOKENS:
            raise ValueError(
                "canonical Unsloth source inference requires max_new_tokens=512"
            )
        if max_seq_length != SOURCE_MAX_SEQ_LENGTH:
            raise ValueError(
                "canonical Unsloth source inference requires max_seq_length=2048"
            )
        protocol: dict[str, Any] = {
            "generation_protocol_version": SOURCE_GENERATION_PROTOCOL_VERSION,
            "reasoning_effort": SOURCE_REASONING_EFFORT,
            "padding_side": SOURCE_PADDING_SIDE,
            "pad_token_id": SOURCE_PAD_TOKEN_ID,
            "eos_token_ids": list(SOURCE_EOS_TOKEN_IDS),
            "do_sample": False,
            "deterministic": True,
            "first_eos_trim": True,
            "max_new_tokens": max_new_tokens,
            "max_seq_length": max_seq_length,
        }
    else:
        protocol = {
            "generation_protocol_version": (
                f"aegislm.source-v2-{backend}-{mode}-generation.v1"
            ),
            "reasoning_effort": "server_managed",
            "padding_side": "server_managed",
            "pad_token_id": "server_managed",
            "eos_token_ids": "server_managed",
            "do_sample": temperature > 0.0,
            "deterministic": temperature == 0.0,
            "first_eos_trim": False,
            "max_new_tokens": max_new_tokens,
            "max_seq_length": max_seq_length,
        }
    encoded = json.dumps(
        protocol, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return {
        **protocol,
        "generation_protocol_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def run_source_inference(
    *,
    dataset_path: Path,
    predictions_path: Path,
    model_id: str,
    run_id: str,
    generate_response: SourceGenerateResponse,
    generation_metadata: Mapping[str, Any] | None = None,
    limit: int | None = None,
) -> int:
    """Generate predictions from model-visible challenge messages only."""
    validate_artifact_path_plan(
        inputs=(dataset_path,),
        outputs=(predictions_path,),
        require_new=True,
    )
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("model_id must be a non-empty string")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    records = load_source_records(dataset_path, require_assistant=False)
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        records = records[:limit]
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "challenge_file_sha256": _file_sha256(dataset_path),
        "challenge_records_sha256": _records_digest(records),
        **dict(generation_metadata or {}),
    }
    descriptor, temporary_name = tempfile.mkstemp(
        dir=predictions_path.parent,
        prefix=f".{predictions_path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            for record in records:
                messages = cast(list[PromptMessage], list(record.prompt_messages))
                started = time.perf_counter()
                raw_output = generate_response(messages)
                if not isinstance(raw_output, str):
                    raise TypeError("source generator must return a string")
                latency_ms = (time.perf_counter() - started) * 1000
                artifact: dict[str, Any] = {
                    "record_id": record.record_id,
                    "model_id": model_id,
                    "run_id": run_id,
                    "raw_output": raw_output,
                    "latency_ms": round(latency_ms, 4),
                    "generated_at": datetime.now(UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "metadata": {
                        "target_cwe": record.target_cwe,
                        **metadata,
                    },
                }
                last_generation = getattr(
                    generate_response, "aegislm_last_generation", None
                )
                if isinstance(last_generation, Mapping):
                    scoreable_output = last_generation.get("scoreable_output")
                    raw_generation = last_generation.get("raw_generation")
                    if scoreable_output != raw_output or not isinstance(
                        raw_generation, str
                    ):
                        raise ValueError("invalid source generation evidence envelope")
                    artifact["raw_generation"] = raw_generation
                    artifact["scoreable_output"] = raw_output
                    artifact["generation"] = {
                        key: value
                        for key, value in last_generation.items()
                        if key not in {"raw_generation", "scoreable_output"}
                    }
                output.write(
                    json.dumps(artifact, ensure_ascii=False, allow_nan=False) + "\n"
                )
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, predictions_path, follow_symlinks=False)
        except FileExistsError as exc:
            raise FileExistsError(
                f"artifact output already exists: {predictions_path}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return len(records)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records_digest(records: list[Any]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.record_id.encode())
        digest.update(b"\0")
        digest.update(record.target_cwe.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def make_openai_compatible_source_generator(
    *,
    base_url: str,
    model_id: str,
    max_new_tokens: int,
    temperature: float,
    constrained: bool,
    api_key_env: str = "AEGISLM_INFERENCE_API_KEY",
    timeout_seconds: float = 300.0,
) -> SourceGenerateResponse:
    """Build a local OpenAI-compatible raw or JSON-schema response generator."""
    endpoint = _validated_loopback_base_url(base_url) + "/v1/chat/completions"

    def generate(messages: list[PromptMessage]) -> str:
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }
        if constrained:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "aegislm_source_assessment",
                    "strict": True,
                    "schema": SOURCE_ASSESSMENT_SCHEMA,
                },
            }
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get(api_key_env)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )
        with opener.open(request, timeout=timeout_seconds) as response:
            encoded_body = response.read(MAX_OPENAI_RESPONSE_BYTES + 1)
        if len(encoded_body) > MAX_OPENAI_RESPONSE_BYTES:
            raise ValueError("OpenAI-compatible response exceeds the byte limit")
        try:
            body = strict_json_loads(encoded_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("OpenAI-compatible response is invalid JSON") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                "OpenAI-compatible response has no message content"
            ) from exc
        if not isinstance(content, str):
            raise ValueError("OpenAI-compatible message content must be a string")
        if len(content.encode("utf-8")) > MAX_OPENAI_CONTENT_BYTES:
            raise ValueError("OpenAI-compatible message content exceeds the byte limit")
        return content

    return generate


def _validated_loopback_base_url(base_url: str) -> str:
    """Accept only explicit loopback HTTP(S) endpoints for source-bearing prompts."""
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("OpenAI-compatible base URL must be a loopback HTTP(S) URL")
    hostname = parsed.hostname.lower()
    if "%" in hostname:
        raise ValueError(
            "numeric loopback base URL must not use an IPv6 scope identifier"
        )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise ValueError(
            "OpenAI-compatible base URL must use a numeric loopback host"
        ) from exc
    if not address.is_loopback:
        raise ValueError("OpenAI-compatible base URL must use a numeric loopback host")
    return base_url.rstrip("/")
