import json
from pathlib import Path

from aegislm.runtime.memory_budget import (
    BYTES_PER_GIB,
    _record_to_csv_row,
    build_memory_budget_report,
    effective_memory_limit,
    inspect_model_dir,
    parse_memory_events,
    parse_memory_value,
    read_cgroup_chain,
)


def test_parse_memory_values():
    assert parse_memory_value("max\n") is None
    assert parse_memory_value("858993459200\n") == 858993459200


def test_parse_memory_events():
    assert parse_memory_events("oom 109\noom_kill 4\n") == {
        "oom": 109,
        "oom_kill": 4,
    }


def test_cgroup_ancestor_effective_limit(tmp_path):
    cgroup_root = tmp_path / "sys" / "fs" / "cgroup"
    leaf = cgroup_root / "docker.scope" / "system.slice" / "cron.service"
    leaf.mkdir(parents=True)
    proc_cgroup = tmp_path / "proc_self_cgroup"
    proc_cgroup.write_text(
        "0::/docker.scope/system.slice/cron.service\n",
        encoding="utf-8",
    )

    _write_cgroup_files(cgroup_root, memory_max="max")
    _write_cgroup_files(
        cgroup_root / "docker.scope", memory_max=str(800 * BYTES_PER_GIB)
    )
    _write_cgroup_files(
        cgroup_root / "docker.scope" / "system.slice",
        memory_max=str(900 * BYTES_PER_GIB),
    )
    _write_cgroup_files(leaf, memory_max="max")

    snapshots = read_cgroup_chain(proc_cgroup=proc_cgroup, cgroup_root=cgroup_root)
    limit, path = effective_memory_limit(snapshots)

    assert limit == 800 * BYTES_PER_GIB
    assert path == cgroup_root / "docker.scope"


def test_known_risk_profile_fails_budget(tmp_path):
    cgroup_root = tmp_path / "sys" / "fs" / "cgroup"
    leaf = cgroup_root / "docker.scope" / "system.slice" / "cron.service"
    leaf.mkdir(parents=True)
    proc_cgroup = tmp_path / "proc_self_cgroup"
    proc_cgroup.write_text(
        "0::/docker.scope/system.slice/cron.service\n",
        encoding="utf-8",
    )
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemAvailable: 2000000000 kB\n", encoding="utf-8")
    _write_cgroup_files(cgroup_root, memory_max="max")
    _write_cgroup_files(
        cgroup_root / "docker.scope", memory_max=str(800 * BYTES_PER_GIB)
    )
    _write_cgroup_files(cgroup_root / "docker.scope" / "system.slice", memory_max="max")
    _write_cgroup_files(leaf, memory_max="max")

    model_dir = tmp_path / "qwen3-coder-480b-a35b-instruct-fp8"
    model_dir.mkdir()

    report = build_memory_budget_report(
        model_dir=model_dir,
        nproc=4,
        proc_cgroup=proc_cgroup,
        cgroup_root=cgroup_root,
        meminfo=meminfo,
    )

    assert report.known_risk is True
    assert any("Known-risk profile" in warning for warning in report.warnings)


def test_non_480b_profile_is_not_known_risk(tmp_path):
    cgroup_root = tmp_path / "sys" / "fs" / "cgroup"
    leaf = cgroup_root / "job"
    leaf.mkdir(parents=True)
    proc_cgroup = tmp_path / "proc_self_cgroup"
    proc_cgroup.write_text("0::/job\n", encoding="utf-8")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemAvailable: 2000000000 kB\n", encoding="utf-8")
    _write_cgroup_files(cgroup_root, memory_max="max")
    _write_cgroup_files(leaf, memory_max=str(800 * BYTES_PER_GIB))

    model_dir = tmp_path / "qwen3-coder-32b"
    model_dir.mkdir()

    report = build_memory_budget_report(
        model_dir=model_dir,
        nproc=4,
        proc_cgroup=proc_cgroup,
        cgroup_root=cgroup_root,
        meminfo=meminfo,
    )

    assert report.known_risk is False


def test_inspect_model_dir_detects_missing_shards(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model-00001-of-00002.safetensors").write_bytes(b"abc")
    (model_dir / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "weight_map": {
                    "a": "model-00001-of-00002.safetensors",
                    "b": "model-00002-of-00002.safetensors",
                }
            }
        ),
        encoding="utf-8",
    )

    total, shard_count, missing = inspect_model_dir(model_dir)

    assert total == 3
    assert shard_count == 1
    assert missing == ["model-00002-of-00002.safetensors"]


def test_record_to_csv_row_includes_top_process_summary():
    row = _record_to_csv_row(
        {
            "timestamp": "2026-07-02T00:00:00+00:00",
            "effective_limit_gib": 800.0,
            "host_mem_available_gib": 2000.0,
            "gpu_metrics": [
                {"memory_used_mib": 10, "utilization_gpu_percent": 3},
                {"memory_used_mib": 20, "utilization_gpu_percent": 5},
            ],
            "process_metrics": [
                {
                    "rss_kib": 2048,
                    "cpu_percent": 12.5,
                    "args": "python rank0",
                },
                {
                    "rss_kib": 1024,
                    "cpu_percent": 2.0,
                    "args": "python rank1",
                },
            ],
            "cgroups": [
                {
                    "memory_current_bytes": 1024**3,
                    "memory_peak_bytes": 2 * 1024**3,
                    "memory_events": {"oom": 1, "oom_kill": 0},
                }
            ],
        }
    )

    assert row["top_rss_mib_total"] == 3
    assert row["top_rss_mib_max"] == 2
    assert row["top_cpu_percent_max"] == 12.5
    assert row["top_process_count"] == 2
    assert row["top_process"] == "python rank0"


def _write_cgroup_files(path: Path, *, memory_max: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "memory.max").write_text(f"{memory_max}\n", encoding="utf-8")
    (path / "memory.current").write_text("1\n", encoding="utf-8")
    (path / "memory.peak").write_text("2\n", encoding="utf-8")
    (path / "memory.events").write_text("oom 0\noom_kill 0\n", encoding="utf-8")
