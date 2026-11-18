"""Memory budget helpers for large-model B200 smoke runs."""

from __future__ import annotations

import csv
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BYTES_PER_GIB = 1024**3
UNLIMITED = "max"


@dataclass(frozen=True)
class CgroupMemorySnapshot:
    path: Path
    memory_max: int | None
    memory_current: int | None
    memory_peak: int | None
    memory_events: dict[str, int]


@dataclass(frozen=True)
class MemoryBudgetReport:
    cgroups: list[CgroupMemorySnapshot]
    effective_limit: int | None
    effective_limit_path: Path | None
    host_mem_available: int | None
    gpu_metrics: list[dict[str, int | str]]
    process_metrics: list[dict[str, int | float | str]]
    model_total_bytes: int | None
    model_shard_count: int
    missing_shards: list[str]
    known_risk: bool
    warnings: list[str]


def bytes_to_gib(value: int | None) -> float | None:
    if value is None:
        return None
    return value / BYTES_PER_GIB


def parse_memory_value(raw: str) -> int | None:
    value = raw.strip()
    if value == UNLIMITED or not value:
        return None
    return int(value)


def parse_memory_events(raw: str) -> dict[str, int]:
    events: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                events[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return events


def discover_cgroup_paths(
    *,
    proc_cgroup: Path = Path("/proc/self/cgroup"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> list[Path]:
    """Return the current cgroup v2 path followed by its existing ancestors."""
    relative = Path("/")
    for line in proc_cgroup.read_text(encoding="utf-8").splitlines():
        parts = line.split(":", maxsplit=2)
        if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
            relative = Path(parts[2].lstrip("/"))
            break

    current = (cgroup_root / relative).resolve()
    root = cgroup_root.resolve()
    paths: list[Path] = []
    while True:
        if current.exists():
            paths.append(current)
        if current == root or current.parent == current:
            break
        current = current.parent
    if root.exists() and root not in paths:
        paths.append(root)
    return paths


def read_cgroup_memory(path: Path) -> CgroupMemorySnapshot:
    return CgroupMemorySnapshot(
        path=path,
        memory_max=_read_optional_memory_value(path / "memory.max"),
        memory_current=_read_optional_memory_value(path / "memory.current"),
        memory_peak=_read_optional_memory_value(path / "memory.peak"),
        memory_events=parse_memory_events(_read_optional_text(path / "memory.events")),
    )


def read_cgroup_chain(
    *,
    proc_cgroup: Path = Path("/proc/self/cgroup"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> list[CgroupMemorySnapshot]:
    return [
        read_cgroup_memory(path)
        for path in discover_cgroup_paths(
            proc_cgroup=proc_cgroup,
            cgroup_root=cgroup_root,
        )
    ]


def effective_memory_limit(
    snapshots: list[CgroupMemorySnapshot],
) -> tuple[int | None, Path | None]:
    finite = [
        (snapshot.memory_max, snapshot.path)
        for snapshot in snapshots
        if snapshot.memory_max is not None
    ]
    if not finite:
        return None, None
    return min(finite, key=lambda item: item[0])


def read_host_mem_available(meminfo: Path = Path("/proc/meminfo")) -> int | None:
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2:
                return int(parts[1]) * 1024
    return None


def read_gpu_metrics() -> list[dict[str, int | str]]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []

    metrics: list[dict[str, int | str]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            metrics.append(
                {
                    "index": int(parts[0]),
                    "memory_used_mib": int(parts[1]),
                    "utilization_gpu_percent": int(parts[2]),
                }
            )
        except ValueError:
            metrics.append({"raw": line})
    return metrics


def read_process_metrics(limit: int = 12) -> list[dict[str, int | float | str]]:
    """Return top-like process rows sorted by resident memory."""
    command = [
        "ps",
        "-eo",
        "pid,ppid,pcpu,pmem,rss,vsz,comm,args",
        "--sort=-rss",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []

    metrics: list[dict[str, int | float | str]] = []
    for line in completed.stdout.splitlines()[1 : limit + 1]:
        parts = line.split(maxsplit=7)
        if len(parts) < 8:
            continue
        try:
            metrics.append(
                {
                    "pid": int(parts[0]),
                    "ppid": int(parts[1]),
                    "cpu_percent": float(parts[2]),
                    "mem_percent": float(parts[3]),
                    "rss_kib": int(parts[4]),
                    "vsz_kib": int(parts[5]),
                    "command": parts[6],
                    "args": parts[7],
                }
            )
        except ValueError:
            continue
    return metrics


def inspect_model_dir(model_dir: Path) -> tuple[int, int, list[str]]:
    if not model_dir.exists():
        return 0, 0, []

    shards = sorted(model_dir.glob("*.safetensors"))
    total = sum(path.stat().st_size for path in shards)
    missing = _missing_shards_from_index(model_dir)
    return total, len(shards), missing


def build_memory_budget_report(
    *,
    model_dir: Path | None,
    nproc: int,
    known_risk_limit_gib: float = 900.0,
    proc_cgroup: Path = Path("/proc/self/cgroup"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    meminfo: Path = Path("/proc/meminfo"),
    process_count: int = 12,
) -> MemoryBudgetReport:
    cgroups = read_cgroup_chain(proc_cgroup=proc_cgroup, cgroup_root=cgroup_root)
    limit, limit_path = effective_memory_limit(cgroups)
    model_total = None
    model_shard_count = 0
    missing_shards: list[str] = []
    if model_dir is not None:
        model_total, model_shard_count, missing_shards = inspect_model_dir(model_dir)

    known_risk = is_known_qwen3_480b_fp8_risk(
        model_dir=model_dir,
        model_total_bytes=model_total,
        nproc=nproc,
        effective_limit=limit,
        known_risk_limit_gib=known_risk_limit_gib,
    )
    warnings = build_warnings(
        effective_limit=limit,
        effective_limit_path=limit_path,
        known_risk=known_risk,
        missing_shards=missing_shards,
        model_total_bytes=model_total,
        model_shard_count=model_shard_count,
        nproc=nproc,
    )

    return MemoryBudgetReport(
        cgroups=cgroups,
        effective_limit=limit,
        effective_limit_path=limit_path,
        host_mem_available=read_host_mem_available(meminfo),
        gpu_metrics=read_gpu_metrics(),
        process_metrics=read_process_metrics(limit=process_count),
        model_total_bytes=model_total,
        model_shard_count=model_shard_count,
        missing_shards=missing_shards,
        known_risk=known_risk,
        warnings=warnings,
    )


def is_known_qwen3_480b_fp8_risk(
    *,
    model_dir: Path | None,
    model_total_bytes: int | None,
    nproc: int,
    effective_limit: int | None,
    known_risk_limit_gib: float,
) -> bool:
    if effective_limit is None or nproc < 4:
        return False

    model_name = str(model_dir or "").lower()
    looks_like_480b_fp8 = (
        "qwen3-coder-480b" in model_name and "fp8" in model_name
    ) or (model_total_bytes is not None and model_total_bytes >= 450 * BYTES_PER_GIB)
    limit_is_tight = effective_limit <= int(known_risk_limit_gib * BYTES_PER_GIB)
    return looks_like_480b_fp8 and limit_is_tight


def build_warnings(
    *,
    effective_limit: int | None,
    effective_limit_path: Path | None,
    known_risk: bool,
    missing_shards: list[str],
    model_total_bytes: int | None,
    model_shard_count: int,
    nproc: int,
) -> list[str]:
    warnings: list[str] = []
    if effective_limit is None:
        warnings.append("No finite cgroup memory.max limit was found.")
    else:
        warnings.append(
            "Effective cgroup memory.max is "
            f"{bytes_to_gib(effective_limit):.1f} GiB at {effective_limit_path}."
        )
    if model_total_bytes is not None:
        warnings.append(
            "Model safetensors total is "
            f"{bytes_to_gib(model_total_bytes):.1f} GiB across "
            f"{model_shard_count} shard(s)."
        )
    if missing_shards:
        warnings.append(f"Missing safetensors shard(s): {', '.join(missing_shards)}")
    if known_risk:
        warnings.append(
            "Known-risk profile: Qwen3-Coder 480B FP8 with "
            f"{nproc} ranks has already reached the 800 GiB container limit "
            "during checkpoint loading."
        )
    return warnings


def snapshot_to_record(report: MemoryBudgetReport) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "effective_limit_bytes": report.effective_limit,
        "effective_limit_gib": bytes_to_gib(report.effective_limit),
        "effective_limit_path": str(report.effective_limit_path)
        if report.effective_limit_path
        else None,
        "host_mem_available_bytes": report.host_mem_available,
        "host_mem_available_gib": bytes_to_gib(report.host_mem_available),
        "gpu_metrics": report.gpu_metrics,
        "process_metrics": report.process_metrics,
        "cgroups": [
            {
                "path": str(snapshot.path),
                "memory_max_bytes": snapshot.memory_max,
                "memory_current_bytes": snapshot.memory_current,
                "memory_peak_bytes": snapshot.memory_peak,
                "memory_events": snapshot.memory_events,
            }
            for snapshot in report.cgroups
        ],
    }


def watch_memory(
    *,
    output_dir: Path,
    model_dir: Path | None,
    nproc: int,
    interval_seconds: float,
    duration_seconds: float | None,
    process_count: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    jsonl_path = output_dir / f"memory_watch_{timestamp}.jsonl"
    csv_path = output_dir / f"memory_watch_{timestamp}.csv"
    fieldnames = [
        "timestamp",
        "effective_limit_gib",
        "host_mem_available_gib",
        "cgroup_current_gib",
        "cgroup_peak_gib",
        "oom",
        "oom_kill",
        "gpu_memory_used_mib_total",
        "gpu_utilization_percent_max",
        "top_rss_mib_total",
        "top_rss_mib_max",
        "top_cpu_percent_max",
        "top_process_count",
        "top_process",
    ]
    start = time.monotonic()
    with (
        jsonl_path.open("a", encoding="utf-8") as jsonl_file,
        csv_path.open(
            "a",
            encoding="utf-8",
            newline="",
        ) as csv_file,
    ):
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        while True:
            report = build_memory_budget_report(
                model_dir=model_dir,
                nproc=nproc,
                process_count=process_count,
            )
            record = snapshot_to_record(report)
            jsonl_file.write(json.dumps(record, sort_keys=True) + "\n")
            jsonl_file.flush()
            writer.writerow(_record_to_csv_row(record))
            csv_file.flush()
            if (
                duration_seconds is not None
                and time.monotonic() - start >= duration_seconds
            ):
                break
            time.sleep(interval_seconds)


def _record_to_csv_row(record: dict[str, Any]) -> dict[str, Any]:
    cgroup = record["cgroups"][0] if record["cgroups"] else {}
    events = cgroup.get("memory_events", {})
    gpu_metrics = record["gpu_metrics"]
    process_metrics = record["process_metrics"]
    top_rss_values = [
        metric.get("rss_kib", 0)
        for metric in process_metrics
        if isinstance(metric.get("rss_kib"), int)
    ]
    top_cpu_values = [
        metric.get("cpu_percent", 0.0)
        for metric in process_metrics
        if isinstance(metric.get("cpu_percent"), float | int)
    ]
    top_process = process_metrics[0] if process_metrics else {}
    return {
        "timestamp": record["timestamp"],
        "effective_limit_gib": record["effective_limit_gib"],
        "host_mem_available_gib": record["host_mem_available_gib"],
        "cgroup_current_gib": bytes_to_gib(cgroup.get("memory_current_bytes")),
        "cgroup_peak_gib": bytes_to_gib(cgroup.get("memory_peak_bytes")),
        "oom": events.get("oom"),
        "oom_kill": events.get("oom_kill"),
        "gpu_memory_used_mib_total": sum(
            metric.get("memory_used_mib", 0)
            for metric in gpu_metrics
            if isinstance(metric.get("memory_used_mib"), int)
        ),
        "gpu_utilization_percent_max": max(
            [
                metric.get("utilization_gpu_percent", 0)
                for metric in gpu_metrics
                if isinstance(metric.get("utilization_gpu_percent"), int)
            ],
            default=0,
        ),
        "top_rss_mib_total": sum(top_rss_values) / 1024,
        "top_rss_mib_max": max(top_rss_values, default=0) / 1024,
        "top_cpu_percent_max": max(top_cpu_values, default=0.0),
        "top_process_count": len(process_metrics),
        "top_process": top_process.get("args") or top_process.get("command"),
    }


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_optional_memory_value(path: Path) -> int | None:
    if not path.exists():
        return None
    return parse_memory_value(path.read_text(encoding="utf-8"))


def _missing_shards_from_index(model_dir: Path) -> list[str]:
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    weight_map = data.get("weight_map", {})
    expected = sorted(set(weight_map.values()))
    return [name for name in expected if not (model_dir / name).exists()]
