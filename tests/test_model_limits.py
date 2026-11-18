from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegislm.experiments.model_limits import (
    ModelLimitManifestError,
    build_load_command,
    enforce_download_limit,
    load_model_limit_manifest,
    summarize_result_rows,
)


def test_manifest_loads_current_candidates() -> None:
    manifest = load_model_limit_manifest(
        Path("experiments/model_limits/candidates.json")
    )

    assert [candidate.key for candidate in manifest.candidates] == [
        "qwen3_coder_next",
        "qwen3_coder_next_base",
        "glm45_air_fp8",
        "deepseek_v4_flash",
        "deepseek_v4_flash_base",
        "glm45_full_fp8",
        "qwen3_coder_480b_fp8",
    ]
    assert (
        manifest.by_key("deepseek_v4_flash").model_id == "deepseek-ai/DeepSeek-V4-Flash"
    )


def test_manifest_requires_fields(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(
        json.dumps({"candidates": [{"key": "broken"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ModelLimitManifestError):
        load_model_limit_manifest(manifest_path)


def test_enforce_download_limit_blocks_oversize_snapshot() -> None:
    with pytest.raises(ValueError, match="exceeds max_download_gib"):
        enforce_download_limit(11 * 1024**3, 10.0)


def test_build_load_command_for_vllm() -> None:
    manifest = load_model_limit_manifest(
        Path("experiments/model_limits/candidates.json")
    )
    candidate = manifest.by_key("qwen3_coder_next")

    command = build_load_command(
        candidate,
        backend="vllm",
        project_root=Path("/project"),
        port=18000,
    )

    assert command[:3] == ["/project/.venv/bin/vllm", "serve", candidate.local_dir]
    assert "--tensor-parallel-size" in command
    assert "4" in command
    assert "--max-model-len" in command


def test_build_load_command_for_sglang() -> None:
    manifest = load_model_limit_manifest(
        Path("experiments/model_limits/candidates.json")
    )
    candidate = manifest.by_key("glm45_air_fp8")

    command = build_load_command(
        candidate,
        backend="sglang",
        project_root=Path("/project"),
        port=18001,
    )

    assert command[:3] == [
        "/project/.venv/bin/python",
        "-m",
        "sglang.launch_server",
    ]
    assert "--tp" in command
    assert "4" in command


def test_summarize_result_rows_returns_markdown_table() -> None:
    table = summarize_result_rows(
        [
            {
                "candidate": "qwen3_coder_next",
                "model_id": "Qwen/Qwen3-Coder-Next",
                "backend": "vllm",
                "phase": "config-only",
                "status": "config_ok",
                "ready": True,
                "model_total_gib": 120.5,
                "oom_kill_delta": 0,
                "return_code": None,
            }
        ]
    )

    assert "| Candidate | Model | Backend | Phase | Status |" in table
    assert "qwen3_coder_next" in table
    assert "config_ok" in table
