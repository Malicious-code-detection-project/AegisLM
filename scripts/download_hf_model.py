"""Download Hugging Face base models into the local model/ tree."""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

sys.path.append(str(Path(__file__).resolve().parents[1]))

from aegislm.runtime.memory_budget import bytes_to_gib, inspect_model_dir  # noqa: E402


MODEL_VARIANTS = {
    "deepseek-v4-flash": {
        "model_id": "deepseek-ai/DeepSeek-V4-Flash",
        "local_dir": "model/base/deepseek-v4-flash",
    },
    "deepseek-v4-flash-base": {
        "model_id": "deepseek-ai/DeepSeek-V4-Flash-Base",
        "local_dir": "model/base/deepseek-v4-flash-base",
    },
    "glm45-air-fp8": {
        "model_id": "zai-org/GLM-4.5-Air-FP8",
        "local_dir": "model/base/glm-4.5-air-fp8",
    },
    "glm45-full-fp8": {
        "model_id": "zai-org/GLM-4.5-FP8",
        "local_dir": "model/base/glm-4.5-fp8",
    },
    "qwen3-coder-next": {
        "model_id": "Qwen/Qwen3-Coder-Next",
        "local_dir": "model/base/qwen3-coder-next",
    },
    "qwen3-coder-30b": {
        "model_id": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
        "local_dir": "model/base/qwen3-coder-30b-a3b-instruct",
    },
    "fp8": {
        "model_id": "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        "local_dir": "model/base/qwen3-coder-480b-a35b-instruct-fp8",
    },
    "non-fp8": {
        "model_id": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "local_dir": "model/base/qwen3-coder-480b-a35b-instruct",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a Hugging Face model snapshot for local training."
    )
    parser.add_argument(
        "--variant",
        choices=sorted(MODEL_VARIANTS),
        default="fp8",
        help="Known model variant to download into model/base.",
    )
    parser.add_argument(
        "--model-id",
        help="Override the Hugging Face model id instead of using --variant.",
    )
    parser.add_argument(
        "--local-dir",
        help="Override the local destination directory.",
    )
    parser.add_argument("--revision", help="Optional model revision.")
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("HF_HOME", "model/cache/huggingface"),
        help="Hugging Face download cache directory.",
    )
    parser.add_argument(
        "--allow-pattern",
        action="append",
        dest="allow_patterns",
        help="Optional allow pattern. Can be passed multiple times.",
    )
    parser.add_argument(
        "--ignore-pattern",
        action="append",
        dest="ignore_patterns",
        help="Optional ignore pattern. Can be passed multiple times.",
    )
    parser.add_argument(
        "--dry-run-files",
        action="store_true",
        help="List matching Hugging Face files and estimated size without downloading.",
    )
    parser.add_argument(
        "--max-download-gib",
        type=float,
        help="Abort if the estimated matching snapshot size exceeds this GiB value.",
    )
    parser.add_argument(
        "--inspect-local",
        action="store_true",
        help="Inspect local safetensors shard count/size and missing index shards.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    variant = MODEL_VARIANTS[args.variant]
    model_id = args.model_id or variant["model_id"]
    local_dir = Path(args.local_dir or variant["local_dir"])
    cache_dir = Path(args.cache_dir)
    token = os.environ.get("HF_TOKEN")

    local_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.inspect_local:
        _print_local_model_report(local_dir)
        if not args.dry_run_files and args.max_download_gib is None:
            return

    if args.dry_run_files or args.max_download_gib is not None:
        files = _list_matching_hf_files(
            model_id=model_id,
            revision=args.revision,
            token=token,
            allow_patterns=args.allow_patterns,
            ignore_patterns=args.ignore_patterns,
        )
        total_size = sum(size for _, size in files if size is not None)
        unknown_count = sum(1 for _, size in files if size is None)
        print(f"Hugging Face file plan for {model_id}:")
        for path, size in files:
            rendered_size = (
                "unknown" if size is None else f"{bytes_to_gib(size):.2f} GiB"
            )
            print(f"- {path} ({rendered_size})")
        print(
            f"Estimated known size: {bytes_to_gib(total_size):.2f} GiB "
            f"across {len(files)} file(s); unknown sizes: {unknown_count}"
        )
        if (
            args.max_download_gib is not None
            and total_size > args.max_download_gib * 1024**3
        ):
            raise SystemExit(
                "Estimated Hugging Face snapshot size exceeds "
                f"--max-download-gib={args.max_download_gib}."
            )
        if args.dry_run_files:
            return

    print(f"Downloading {model_id} -> {local_dir}")
    snapshot_download(
        repo_id=model_id,
        revision=args.revision,
        local_dir=local_dir,
        cache_dir=cache_dir,
        token=token or None,
        allow_patterns=args.allow_patterns,
        ignore_patterns=args.ignore_patterns,
    )
    print(f"Model snapshot is ready at {local_dir}")


def _list_matching_hf_files(
    *,
    model_id: str,
    revision: str | None,
    token: str | None,
    allow_patterns: list[str] | None,
    ignore_patterns: list[str] | None,
) -> list[tuple[str, int | None]]:
    api = HfApi(token=token or None)
    tree = api.list_repo_tree(
        repo_id=model_id,
        revision=revision,
        recursive=True,
    )
    files: list[tuple[str, int | None]] = []
    for entry in tree:
        path = getattr(entry, "path", "")
        if entry.__class__.__name__ != "RepoFile" or not path:
            continue
        if not _matches_patterns(path, allow_patterns, default=True):
            continue
        if _matches_patterns(path, ignore_patterns, default=False):
            continue
        files.append((path, getattr(entry, "size", None)))
    return sorted(files)


def _matches_patterns(
    path: str,
    patterns: list[str] | None,
    *,
    default: bool,
) -> bool:
    if not patterns:
        return default
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _print_local_model_report(local_dir: Path) -> None:
    total, shard_count, missing = inspect_model_dir(local_dir)
    print(f"Local model directory: {local_dir}")
    print(f"- safetensors size: {bytes_to_gib(total):.2f} GiB")
    print(f"- safetensors shards: {shard_count}")
    if missing:
        print(f"- missing shards: {', '.join(missing)}")
    else:
        print("- missing shards: none")


if __name__ == "__main__":
    main()
