"""Verify local GPU, PyTorch, toolchain, HF auth, and storage path compatibility."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configure stdout to use UTF-8 if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)

# Diagnostic report container
report: dict[str, Any] = {
    "versions": {},
    "python_env": {},
    "system_tools": {},
    "git_ignored_paths": {},
    "secret_files": {},
    "hf_configuration": {},
    "wandb_configuration": {},
    "pytorch_cuda": {},
    "llm_libraries": {},
}


def check_python_version() -> None:
    py_ver = sys.version.split()[0]
    report["python_env"] = {
        "version": sys.version,
        "executable": sys.executable,
        "platform": sys.platform,
    }
    report["versions"]["python"] = py_ver


def check_system_tools() -> None:
    uv_ok = False
    uv_version = "NOT FOUND"
    try:
        res = subprocess.run(
            ["uv", "--version"], capture_output=True, text=True, check=True
        )
        uv_version = res.stdout.strip()
        uv_ok = True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    report["system_tools"]["uv"] = {"ok": uv_ok, "version": uv_version}

    # Extract clean uv version (e.g. "uv 0.11.14" -> "0.11.14")
    report["versions"]["uv"] = (
        uv_version.split()[1]
        if uv_ok and len(uv_version.split()) > 1
        else (uv_version if uv_ok else None)
    )

    nvidia_ok = False
    driver_info = "NOT AVAILABLE"
    try:
        res = subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=True)
        driver_line = res.stdout.splitlines()[0] if res.stdout else "Driver detected"
        driver_info = " ".join(driver_line.split())
        nvidia_ok = True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    report["system_tools"]["nvidia_smi"] = {"ok": nvidia_ok, "info": driver_info}


def check_git_ignored_paths() -> None:
    print("=== Git Ignore Verification ===")
    paths_to_verify = [
        ".env",
        ".env.local",
        "checkpoints/",
        "adapters/",
        "models/",
        "unsloth_compiled_cache/",
        "experiments/env_check_report.json",
    ]

    ignored_status = {}
    for path_str in paths_to_verify:
        test_path = REPO_ROOT / path_str
        check_path = str(test_path)
        if path_str.endswith("/") and not check_path.endswith("/"):
            check_path += "/"

        try:
            res = subprocess.run(
                ["git", "check-ignore", "-q", check_path],
                capture_output=True,
                check=False,
            )
            is_ignored = res.returncode == 0
            status = "ignored" if is_ignored else "not_ignored"
            print(
                f"[{'PASS' if is_ignored else 'WARN'}] Git Ignore: {path_str} -> {status}"
            )
            ignored_status[path_str] = status
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"[INFO] Git CLI not available. Skipping: {path_str}")
            ignored_status[path_str] = "skipped"

    report["git_ignored_paths"] = ignored_status


def check_secret_file_permissions() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        report["secret_files"][".env"] = {"exists": False, "mode": None, "ok": True}
        return
    mode = stat.S_IMODE(env_path.stat().st_mode)
    secure = mode == 0o600
    report["secret_files"][".env"] = {
        "exists": True,
        "mode": f"{mode:04o}",
        "ok": secure,
    }
    print(f"[{'PASS' if secure else 'WARN'}] Secret File: .env -> mode {mode:04o}")


def check_hf_configuration() -> None:
    # Authentication is intentionally environment-only for reproducibility.
    token = os.environ.get("HF_TOKEN")

    report["hf_configuration"]["token"] = {
        "detected": bool(token),
        "source": "environment" if token else None,
    }

    # 2. HF Cache Location Check
    hf_home = os.environ.get("HF_HOME") or os.environ.get("HF_HUB_CACHE")
    cache_source = "env var" if hf_home else "default location"
    hf_home_path = (
        Path(hf_home)
        if hf_home
        else Path(os.path.expanduser("~")) / ".cache" / "huggingface"
    )

    path_ok = False
    try:
        resolved_hf_home = hf_home_path.resolve()
        resolved_repo = REPO_ROOT.resolve()
        path_ok = (
            resolved_repo not in resolved_hf_home.parents
            and resolved_repo != resolved_hf_home
        )
    except Exception:
        pass

    report["hf_configuration"]["cache"] = {
        "path": str(hf_home_path),
        "source": cache_source,
        "is_external": path_ok,
    }


def check_wandb_configuration() -> None:
    """Report W&B readiness without reading or displaying credential contents."""
    wandb_version = importlib_metadata.version("wandb")
    dotenv_version = importlib_metadata.version("python-dotenv")
    report["wandb_configuration"] = {
        "api_key_detected": bool(os.environ.get("WANDB_API_KEY")),
        "project": "aegislm",
        "group": "source-v2",
        "mode": "online when --wandb is selected",
        "wandb_version": wandb_version,
        "python_dotenv_version": dotenv_version,
    }
    report["versions"]["wandb"] = wandb_version
    report["versions"]["python-dotenv"] = dotenv_version


def check_gpu_and_pytorch() -> bool:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError as e:
        report["pytorch_cuda"] = {"installed": False, "error": str(e)}
        report["versions"]["pytorch"] = None
        report["versions"]["cuda"] = None
        return False

    torch_ver = torch.__version__
    cuda_available = torch.cuda.is_available()
    cuda_ver = torch.version.cuda if cuda_available else None

    report["pytorch_cuda"] = {
        "installed": True,
        "pytorch_version": torch_ver,
        "cuda_available": cuda_available,
        "cuda_version": cuda_ver,
        "devices": [],
    }
    report["versions"]["pytorch"] = torch_ver
    report["versions"]["cuda"] = cuda_ver

    if not cuda_available:
        return False

    for i in range(torch.cuda.device_count()):
        try:
            prop = torch.cuda.get_device_properties(i)
            device_name = torch.cuda.get_device_name(i)
            total_vram_gb = round(prop.total_memory / (1024**3), 2)
            compute_cap = f"{prop.major}.{prop.minor}"
        except Exception as e:
            device_name = f"Unknown Device {i}"
            total_vram_gb = 0.0
            compute_cap = f"unknown ({e})"

        report["pytorch_cuda"]["devices"].append(
            {
                "index": i,
                "name": device_name,
                "total_vram_gb": total_vram_gb,
                "compute_capability": compute_cap,
            }
        )

    # Basic tensor operation on GPU
    try:
        device = torch.device("cuda:0")
        x = torch.randn(1000, 1000, device=device)
        y = torch.randn(1000, 1000, device=device)
        _ = torch.matmul(x, y)
        torch.cuda.synchronize(device)
        report["pytorch_cuda"]["dry_run"] = {"ok": True, "error": None}
        return True
    except Exception as e:
        report["pytorch_cuda"]["dry_run"] = {"ok": False, "error": str(e)}
        return False


def check_llm_libraries() -> None:
    # Unsloth must be imported first to apply its internal optimizations and avoid warnings
    for lib in ["unsloth", "transformers", "datasets", "peft", "trl"]:
        try:
            mod = __import__(lib)
            version = getattr(mod, "__version__", "Installed")
            report["llm_libraries"][lib] = {"installed": True, "version": version}
            report["versions"][lib] = version
        except Exception as e:
            report["llm_libraries"][lib] = {"installed": False, "error": str(e)}
            report["versions"][lib] = None


def print_version_summary() -> None:
    print("\n=== Version Verification Summary ===")
    for lib, ver in report["versions"].items():
        status = "[PASS]" if ver else "[FAIL]"
        print(f"{status} {lib:<16}: {ver or 'NOT FOUND/INSTALLED'}")


def save_report() -> Path:
    report_dir = REPO_ROOT / "experiments"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "env_check_report.json"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[INFO] Diagnostic report written to: {report_path}")
    return report_path


def main() -> None:
    print("=" * 50)
    print("AegisLM GPU & Runtime Environment Check")
    print("=" * 50)
    print()

    check_python_version()
    check_system_tools()
    check_git_ignored_paths()
    check_secret_file_permissions()
    check_hf_configuration()
    check_wandb_configuration()
    gpu_ok = check_gpu_and_pytorch()
    check_llm_libraries()

    print_version_summary()
    save_report()

    print("\n" + "=" * 50)
    if gpu_ok:
        print("[INFO] Environment validation complete. GPU is READY for SFT PoC.")
    else:
        print("[WARN] Environment validation complete with warnings/failures.")
    print("=" * 50)


if __name__ == "__main__":
    main()
