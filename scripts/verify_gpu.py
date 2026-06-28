"""Verify local GPU, PyTorch, toolchain, HF auth, and storage path compatibility."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configure stdout to use UTF-8 if supported, otherwise fallback gracefully
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Diagnostic report container
report: dict[str, Any] = {
    "python_env": {},
    "system_tools": {},
    "git_ignored_paths": {},
    "hf_configuration": {},
    "pytorch_cuda": {},
    "llm_libraries": {},
}


def check_python_version() -> None:
    print("=== Python Environment ===")
    py_ver = sys.version
    py_exec = sys.executable
    platform_name = sys.platform
    print(f"Python Version: {py_ver}")
    print(f"Python Executable: {py_exec}")
    print(f"Platform: {platform_name}\n")

    report["python_env"] = {
        "version": py_ver,
        "executable": py_exec,
        "platform": platform_name,
    }


def check_system_tools() -> None:
    print("=== System CLI Tools ===")
    uv_ok = False
    uv_version = "NOT FOUND"
    try:
        res = subprocess.run(
            ["uv", "--version"], capture_output=True, text=True, check=True
        )
        uv_version = res.stdout.strip()
        print(f"[PASS] uv CLI: {uv_version}")
        uv_ok = True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("[FAIL] uv CLI: NOT FOUND (or not in system PATH)")

    report["system_tools"]["uv"] = {"ok": uv_ok, "version": uv_version}

    # Optional check for NVIDIA system driver info
    nvidia_ok = False
    driver_info = "NOT AVAILABLE"
    try:
        res = subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=True)
        driver_line = res.stdout.splitlines()[0] if res.stdout else "Driver detected"
        driver_info = " ".join(driver_line.split())
        print(f"[PASS] NVIDIA Driver Info: {driver_info}")
        nvidia_ok = True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("[INFO] nvidia-smi: NOT AVAILABLE (expected on non-GPU hosts)")

    report["system_tools"]["nvidia_smi"] = {
        "ok": nvidia_ok,
        "info": driver_info,
    }
    print()


def check_git_ignored_paths() -> None:
    print("=== Git Ignore Verification ===")
    # List of critical paths that must be ignored to prevent Git leaks
    paths_to_verify = [
        ".env",
        ".env.local",
        "checkpoints/",
        "adapters/",
        "models/",
        "experiments/env_check_report.json",
    ]

    ignored_status = {}
    for path_str in paths_to_verify:
        test_path = REPO_ROOT / path_str.rstrip("/")
        try:
            # git check-ignore exit code 0 if ignored, 1 if not ignored
            res = subprocess.run(
                ["git", "check-ignore", "-q", str(test_path)],
                capture_output=True,
                check=False,
            )
            is_ignored = res.returncode == 0
            if is_ignored:
                print(f"[PASS] Ignored by Git: {path_str}")
                ignored_status[path_str] = "ignored"
            else:
                print(f"[WARN] Not explicitly ignored by Git check-ignore: {path_str}")
                ignored_status[path_str] = "not_ignored"
        except (subprocess.SubprocessError, FileNotFoundError):
            print(
                f"[INFO] Git CLI not available. Skipping ignore check for: {path_str}"
            )
            ignored_status[path_str] = "skipped"

    report["git_ignored_paths"] = ignored_status
    print()


def check_hf_configuration() -> None:
    print("=== Hugging Face Config & Token Security ===")

    # 1. HF Token Check
    token = os.environ.get("HF_TOKEN")
    token_source = "environment variable"

    if not token:
        # Check standard cache file path
        token_path = Path(os.path.expanduser("~")) / ".cache" / "huggingface" / "token"
        if token_path.exists():
            try:
                token = token_path.read_text(encoding="utf-8").strip()
                token_source = f"cache file ({token_path})"
            except Exception as e:
                print(f"[WARN] Failed to read HF token from cache file: {e}")

    if token:
        # Mask the token for safety: hf_xxxx... -> hf_••••xxxx
        masked_token = token
        if len(token) > 8:
            masked_token = f"{token[:3]}••••{token[-4:]}"
        print(f"[PASS] HF Token detected from {token_source} (masked: {masked_token})")
        report["hf_configuration"]["token"] = {
            "detected": True,
            "source": token_source,
            "masked": masked_token,
        }
    else:
        print(
            "[WARN] No HF token found (HF_TOKEN env var or cache token). Gated models may not be accessible."
        )
        report["hf_configuration"]["token"] = {
            "detected": False,
            "source": None,
            "masked": None,
        }

    # 2. HF Cache Location Check
    hf_home = os.environ.get("HF_HOME") or os.environ.get("HF_HUB_CACHE")
    cache_source = "environment variable"

    if not hf_home:
        hf_home_path = Path(os.path.expanduser("~")) / ".cache" / "huggingface"
        cache_source = "default location"
    else:
        hf_home_path = Path(hf_home)

    try:
        resolved_hf_home = hf_home_path.resolve()
        resolved_repo = REPO_ROOT.resolve()
        is_inside_repo = (
            resolved_repo in resolved_hf_home.parents
            or resolved_repo == resolved_hf_home
        )
        if is_inside_repo:
            print(
                f"[WARN] HF cache path is inside the Git repo: {hf_home_path} ({cache_source})"
            )
            print("       Ensure it is explicitly ignored or set to an external path.")
            path_ok = False
        else:
            print(
                f"[PASS] HF cache path is external to the Git repo: {hf_home_path} ({cache_source})"
            )
            path_ok = True
    except Exception as e:
        print(f"[WARN] Could not resolve HF cache path: {e}")
        path_ok = False

    report["hf_configuration"]["cache"] = {
        "path": str(hf_home_path),
        "source": cache_source,
        "is_external": path_ok,
    }
    print()


def check_gpu_and_pytorch() -> bool:
    print("=== PyTorch & CUDA Environment ===")
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError as e:
        print("[FAIL] PyTorch: NOT INSTALLED in the current environment.")
        report["pytorch_cuda"] = {"installed": False, "error": str(e)}
        return False

    torch_ver = torch.__version__
    cuda_available = torch.cuda.is_available()
    print(f"PyTorch Version: {torch_ver}")
    print(f"CUDA Available: {cuda_available}")

    report["pytorch_cuda"] = {
        "installed": True,
        "pytorch_version": torch_ver,
        "cuda_available": cuda_available,
    }

    if not cuda_available:
        print("[FAIL] CUDA is not available. GPU acceleration cannot be used.")
        return False

    cuda_ver = torch.version.cuda
    device_count = torch.cuda.device_count()
    print(f"CUDA Version (PyTorch): {cuda_ver}")
    print(f"GPU Device Count: {device_count}")

    report["pytorch_cuda"]["cuda_version"] = cuda_ver
    report["pytorch_cuda"]["devices"] = []

    for i in range(device_count):
        device_name = torch.cuda.get_device_name(i)
        properties = torch.cuda.get_device_properties(i)
        total_memory_gb = properties.total_memory / (1024**3)
        print(f"  - Device [{i}]: {device_name}")
        print(f"    Total VRAM: {total_memory_gb:.2f} GB")
        print(f"    Compute Capability: {properties.major}.{properties.minor}")

        report["pytorch_cuda"]["devices"].append(
            {
                "index": i,
                "name": device_name,
                "total_vram_gb": round(total_memory_gb, 2),
                "compute_capability": f"{properties.major}.{properties.minor}",
            }
        )

    # Basic tensor operation on GPU
    try:
        print("\nRunning simple GPU tensor operation...")
        device = torch.device("cuda:0")
        x = torch.randn(1000, 1000, device=device)
        y = torch.randn(1000, 1000, device=device)
        _ = torch.matmul(x, y)
        torch.cuda.synchronize(device)
        print("[PASS] GPU tensor multiplication successful!")
        report["pytorch_cuda"]["dry_run"] = {"ok": True, "error": None}
        return True
    except Exception as e:
        print(f"[FAIL] GPU tensor operation failed: {e}")
        report["pytorch_cuda"]["dry_run"] = {"ok": False, "error": str(e)}
        return False


def check_llm_libraries() -> None:
    print("\n=== LLM & Fine-Tuning Libraries ===")
    libraries = [
        "transformers",
        "datasets",
        "peft",
        "trl",
        "unsloth",
    ]

    for lib in libraries:
        try:
            mod = __import__(lib)
            version = getattr(mod, "__version__", "Installed (unknown version)")
            print(f"[PASS] {lib:<15}: {version}")
            report["llm_libraries"][lib] = {"installed": True, "version": version}
        except ImportError as e:
            print(f"[FAIL] {lib:<15}: NOT INSTALLED")
            report["llm_libraries"][lib] = {"installed": False, "error": str(e)}


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
    check_hf_configuration()
    gpu_ok = check_gpu_and_pytorch()
    check_llm_libraries()

    # Save validation results
    save_report()

    print("\n" + "=" * 50)
    if gpu_ok:
        print("[INFO] Environment validation complete. GPU is READY for SFT PoC.")
    else:
        print("[WARN] Environment validation complete with warnings/failures.")
    print("=" * 50)


if __name__ == "__main__":
    main()
