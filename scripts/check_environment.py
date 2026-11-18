"""Preflight checks for the B200 AegisLM fine-tuning workspace."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check local environment before dataset build or smoke training."
    )
    parser.add_argument("--project-root", default=".", help="AegisLM project root.")
    parser.add_argument(
        "--llamafactory-dir",
        default=os.environ.get("LLAMAFACTORY_DIR", "LLaMA-Factory"),
        help="Local LLaMA-Factory checkout path.",
    )
    parser.add_argument(
        "--dataset-output-dir",
        default=os.environ.get("DATASET_OUTPUT_DIR", "data/processed"),
        help="Processed dataset output directory.",
    )
    parser.add_argument(
        "--model-root",
        default=os.environ.get("MODEL_ROOT", "model"),
        help="Local model artifact root.",
    )
    parser.add_argument(
        "--expected-cuda-devices",
        type=int,
        default=4,
        help="Expected CUDA device count for the B200 training profile.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    checks = [
        _check_path(project_root / ".venv", "project virtualenv", required=True),
        _check_path(
            project_root / args.llamafactory_dir,
            "LLaMA-Factory checkout",
            required=True,
        ),
        _check_path(
            project_root / args.llamafactory_dir / "data" / "dataset_info.json",
            "LLaMA-Factory dataset_info.json",
            required=True,
        ),
        _check_path(
            project_root / args.dataset_output_dir,
            "processed dataset output directory",
            required=False,
        ),
        _check_path(
            project_root / args.model_root, "model artifact root", required=True
        ),
        _check_path(
            project_root / args.model_root / "base",
            "base model directory",
            required=False,
        ),
        _check_git_ignored(project_root, args.model_root),
        _check_git_ignored(
            project_root,
            args.dataset_output_dir.split("/", maxsplit=1)[0],
        ),
        _check_env("WANDB_API_KEY", required=False, secret=True),
        _check_env("WANDB_PROJECT", required=False),
        _check_env("HF_TOKEN", required=False, secret=True),
        _check_env("CUDA_VISIBLE_DEVICES", required=False),
        _check_cuda(project_root, args.expected_cuda_devices),
    ]

    for check in checks:
        status = "OK" if check.ok else ("WARN" if check.warning else "FAIL")
        print(f"[{status}] {check.message}")

    failures = [check for check in checks if not check.ok and not check.warning]
    if failures:
        raise SystemExit(1)


class CheckResult:
    def __init__(self, ok: bool, message: str, *, warning: bool = False) -> None:
        self.ok = ok
        self.message = message
        self.warning = warning


def _check_path(path: Path, label: str, *, required: bool) -> CheckResult:
    if path.exists():
        return CheckResult(True, f"{label}: {path}")
    if required:
        return CheckResult(False, f"missing {label}: {path}")
    return CheckResult(False, f"not created yet: {label}: {path}", warning=True)


def _check_env(name: str, *, required: bool, secret: bool = False) -> CheckResult:
    value = os.environ.get(name)
    if value:
        rendered = "<set>" if secret else value
        return CheckResult(True, f"{name}: {rendered}")
    if required:
        return CheckResult(False, f"{name} is not set")
    return CheckResult(False, f"{name} is not set", warning=True)


def _check_git_ignored(project_root: Path, relative_path: str) -> CheckResult:
    command = ["git", "check-ignore", "-q", relative_path]
    try:
        subprocess.run(
            command,
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.CalledProcessError:
        return CheckResult(False, f"{relative_path} is not Git-ignored")
    except Exception as exc:  # pragma: no cover - git availability dependent
        return CheckResult(False, f"Git ignore check failed for {relative_path}: {exc}")
    return CheckResult(True, f"{relative_path} is Git-ignored")


def _check_cuda(project_root: Path, expected_device_count: int) -> CheckResult:
    python_path = project_root / ".venv" / "bin" / "python"
    if not python_path.exists():
        return CheckResult(
            False, "cannot check CUDA because .venv/bin/python is missing"
        )

    command = [
        str(python_path),
        "-c",
        "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # pragma: no cover - hardware dependent
        return CheckResult(False, f"CUDA check failed: {exc}", warning=True)

    output = completed.stdout.strip()
    parts = output.split()
    if len(parts) == 2 and parts[0] == "True":
        try:
            device_count = int(parts[1])
        except ValueError:
            device_count = -1
        if device_count < expected_device_count:
            return CheckResult(
                False,
                f"CUDA device count is {device_count}, expected at least "
                f"{expected_device_count}",
                warning=True,
            )
    return CheckResult(True, f"CUDA availability/device count: {output}")


if __name__ == "__main__":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    main()
