import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any

import aegislm.tracking
import pytest
from scripts import import_source_canary_to_wandb as importer


class ImportRun:
    id = "import-run"
    url = "https://wandb.invalid/import-run"

    def __init__(self):
        self.logged: list[tuple[dict[str, Any], int | None]] = []
        self.summary: dict[str, Any] = {}

    def log(self, payload: dict[str, Any], step: int | None = None) -> None:
        self.logged.append((payload, step))


def test_historical_import_logs_curve_and_no_raw_predictions(tmp_path, monkeypatch):
    state = tmp_path / "trainer_state.json"
    manifest = tmp_path / "manifest.json"
    gate = tmp_path / "gate.json"
    receipt = tmp_path / "receipt.json"
    state.write_text(
        json.dumps(
            {
                "log_history": [
                    {
                        "step": 1,
                        "loss": 1.0,
                        "learning_rate": 0.1,
                        "grad_norm": 2.0,
                        "epoch": 0.5,
                    },
                    {
                        "step": 2,
                        "loss": 0.5,
                        "learning_rate": 0.0,
                        "grad_norm": 1.0,
                        "epoch": 1.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "stage": "canary",
                "base_model_id": importer.EXPECTED_BASE_MODEL_ID,
                "base_model_revision": None,
                "resolved_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
                "resolved_model_revision": importer.EXPECTED_RUNTIME_REVISION,
                "train_record_count": 1000,
                "validation_record_count": 40,
                "training_loss": 0.5,
                "elapsed_seconds": 10.0,
                "peak_vram_gb": 1.0,
                "expert_adapter_tensors_present": True,
                "train_records_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    gate.write_text(
        json.dumps(
            {
                "adapter_reload": True,
                "passed": False,
                "schema_pass_rate": 0.0,
                "minimum_schema_pass_rate": 0.9,
                "record_count": 40,
                "runtime_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
                "runtime_model_revision": importer.EXPECTED_RUNTIME_REVISION,
                "train_records_sha256": "a" * 64,
                "validation_records_sha256": "b" * 64,
                "config_sha256": "c" * 64,
                "raw_generation": "must not upload",
            }
        ),
        encoding="utf-8",
    )
    run = ImportRun()
    init_calls: list[dict[str, Any]] = []
    finish_codes: list[int] = []

    def fake_init(**kwargs: Any) -> ImportRun:
        init_calls.append(kwargs)
        run.id = kwargs["run_id"]
        run.url = f"https://wandb.invalid/aegislm/runs/{run.id}"
        return run

    monkeypatch.setattr(aegislm.tracking, "init_wandb_run", fake_init)

    def fake_finish(exit_code: int) -> None:
        assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == (
            "logged_pending_finish"
        )
        finish_codes.append(exit_code)

    monkeypatch.setattr(aegislm.tracking, "finish_active_wandb", fake_finish)
    monkeypatch.setattr(aegislm.tracking, "require_wandb_api_key", lambda: None)
    monkeypatch.setattr(
        aegislm.tracking,
        "git_reference",
        lambda _repo_root: {"commit": "a" * 40, "dirty": True},
    )
    monkeypatch.setattr(importer, "EXPECTED_HISTORY_STEPS", 2)
    monkeypatch.setattr(importer, "EXPECTED_TRAIN_RECORDS_SHA256", "a" * 64)
    monkeypatch.setattr(importer, "EXPECTED_VALIDATION_RECORDS_SHA256", "b" * 64)
    monkeypatch.setattr(importer, "EXPECTED_GATE_CONFIG_SHA256", "c" * 64)
    monkeypatch.setattr(
        importer,
        "EXPECTED_SOURCE_DIGESTS",
        {
            "trainer_state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "gate_report_sha256": hashlib.sha256(gate.read_bytes()).hexdigest(),
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_source_canary_to_wandb.py",
            "--trainer-state",
            str(state),
            "--manifest",
            str(manifest),
            "--gate-report",
            str(gate),
            "--receipt",
            str(receipt),
            "--wandb",
        ],
    )

    importer.main()

    assert [step for _, step in run.logged] == [1, 2]
    assert init_calls[0]["resume"] == "never"
    assert init_calls[0]["run_id"].startswith("source-v2-canary-import-")
    assert "must not upload" not in repr(init_calls + run.logged)
    assert run.summary["gate/passed"] is False
    assert finish_codes == [0]
    saved_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved_receipt["history_step_count"] == 2
    assert saved_receipt["status"] == "complete"

    importer.main()
    assert len(init_calls) == 1


@pytest.mark.parametrize("bad_value", ["sensitive", True, float("nan"), float("inf")])
def test_historical_import_rejects_nonfinite_or_nonnumeric_loss(bad_value):
    with pytest.raises(ValueError, match="finite number"):
        importer._validated_history_row(
            {
                "step": 1,
                "loss": bad_value,
                "learning_rate": 0.1,
                "grad_norm": 1.0,
                "epoch": 1.0,
            }
        )


def test_historical_import_rejects_inconsistent_gate():
    manifest = {
        "validation_record_count": 40,
        "resolved_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "resolved_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
    }
    gate = {
        "adapter_reload": True,
        "passed": False,
        "schema_pass_rate": 1.0,
        "minimum_schema_pass_rate": 0.9,
        "record_count": 40,
        "runtime_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "runtime_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
        "validation_records_sha256": importer.EXPECTED_VALIDATION_RECORDS_SHA256,
        "config_sha256": importer.EXPECTED_GATE_CONFIG_SHA256,
    }

    with pytest.raises(ValueError, match="passing schema rate"):
        importer._validated_gate(gate, manifest)


def test_historical_import_requires_explicit_wandb_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["import_source_canary_to_wandb.py"])

    with pytest.raises(SystemExit) as exc_info:
        importer.main()

    assert exc_info.value.code == 2


@pytest.mark.parametrize("count", [124, 126])
def test_historical_import_requires_exact_frozen_step_count(count):
    rows = [
        {
            "step": step,
            "loss": 0.1,
            "learning_rate": 0.1,
            "grad_norm": 0.1,
            "epoch": 1.0,
        }
        for step in range(1, count + 1)
    ]

    with pytest.raises(ValueError, match="125 steps"):
        importer._validated_history(rows)


def test_historical_gate_rejects_validation_or_config_digest_drift():
    manifest = {
        "validation_record_count": 40,
        "resolved_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "resolved_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
    }
    base_gate = {
        "adapter_reload": True,
        "passed": False,
        "schema_pass_rate": 0.0,
        "minimum_schema_pass_rate": 0.9,
        "record_count": 40,
        "runtime_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "runtime_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
        "validation_records_sha256": importer.EXPECTED_VALIDATION_RECORDS_SHA256,
        "config_sha256": importer.EXPECTED_GATE_CONFIG_SHA256,
    }
    for field in ("validation_records_sha256", "config_sha256"):
        drifted = {**base_gate, field: "f" * 64}
        with pytest.raises(ValueError, match="frozen canary"):
            importer._validated_gate(drifted, manifest)


def test_historical_gate_requires_exact_integer_record_count():
    manifest = {
        "validation_record_count": 40,
        "resolved_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "resolved_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
    }
    gate = {
        "adapter_reload": True,
        "passed": False,
        "schema_pass_rate": 0.0,
        "minimum_schema_pass_rate": 0.9,
        "record_count": 40.0,
        "runtime_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "runtime_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
        "validation_records_sha256": importer.EXPECTED_VALIDATION_RECORDS_SHA256,
        "config_sha256": importer.EXPECTED_GATE_CONFIG_SHA256,
    }

    with pytest.raises(ValueError, match="record count"):
        importer._validated_gate(gate, manifest)


def test_historical_manifest_rejects_unbounded_base_revision():
    manifest = {
        "stage": "canary",
        "base_model_id": importer.EXPECTED_BASE_MODEL_ID,
        "base_model_revision": "int private_source(void);",
        "resolved_model_id": importer.EXPECTED_RUNTIME_MODEL_ID,
        "resolved_model_revision": importer.EXPECTED_RUNTIME_REVISION,
        "train_record_count": 1000,
        "validation_record_count": 40,
        "training_loss": 0.1,
        "elapsed_seconds": 1.0,
        "peak_vram_gb": 1.0,
        "expert_adapter_tensors_present": True,
        "train_records_sha256": importer.EXPECTED_TRAIN_RECORDS_SHA256,
    }

    with pytest.raises(ValueError, match="40 lowercase hex"):
        importer._validated_manifest(manifest)


def test_historical_json_is_hashed_from_one_bounded_stream_read(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    content = b'{"log_history":[]}'
    path.write_bytes(content)
    calls = 0
    original_open = type(path).open

    def counted_open(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", counted_open)

    value, digest = importer._load_object_with_sha256(path)

    assert value == {"log_history": []}
    assert digest == hashlib.sha256(content).hexdigest()
    assert calls == 1


def test_historical_import_rejects_source_artifact_digest_drift():
    drifted = {**importer.EXPECTED_SOURCE_DIGESTS, "manifest_sha256": "f" * 64}

    with pytest.raises(ValueError, match="source digests"):
        importer._require_frozen_source_digests(drifted)


def _historical_receipt_base() -> dict[str, Any]:
    source_digests = {
        "trainer_state_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "gate_report_sha256": "c" * 64,
    }
    identity = hashlib.sha256(
        json.dumps(source_digests, sort_keys=True).encode()
    ).hexdigest()[:12]
    return {
        "historical_import": True,
        "identity": identity,
        "source_digests": source_digests,
        "history_step_count": importer.EXPECTED_HISTORY_STEPS,
        "gate_passed": False,
    }


def _historical_tracking_reference(base: dict[str, Any]) -> dict[str, str]:
    run_id = f"source-v2-canary-import-{base['identity']}"
    return {
        "run_id": run_id,
        "run_url": f"https://wandb.example/aegislm/runs/{run_id}",
    }


def test_historical_receipt_supports_safe_retry_and_idempotent_completion(tmp_path):
    receipt = tmp_path / "receipt.json"
    base = _historical_receipt_base()

    first_claim = importer._prepare_receipt(receipt, base)
    assert first_claim is not None and first_claim.resume == "never"
    first_claim.close()
    recovery_claim = importer._prepare_receipt(receipt, base)
    assert recovery_claim is not None and recovery_claim.resume == "allow"
    importer._mark_logging_started(recovery_claim)
    complete = {
        **base,
        "status": "logged_pending_finish",
        "tracking": _historical_tracking_reference(base),
    }
    importer._finish_with_receipt(
        recovery_claim,
        complete,
        lambda _exit_code: None,
    )
    assert importer._prepare_receipt(receipt, base) is None


def test_historical_receipt_writer_is_atomic_for_its_distinct_schema(tmp_path):
    path = tmp_path / "receipt.json"
    value = {**_historical_receipt_base(), "status": "pending"}
    importer._write_receipt(path, value)

    assert json.loads(path.read_text(encoding="utf-8")) == value


def test_historical_receipt_concurrency_cannot_downgrade_complete(tmp_path):
    path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    reference = _historical_tracking_reference(base)
    pending = {**base, "status": "pending"}
    logged = {**base, "status": "logged_pending_finish", "tracking": reference}
    complete = {**logged, "status": "complete"}
    importer._write_receipt(path, pending)

    def attempt(payload):
        try:
            importer._write_receipt(path, payload)
        except ValueError as exc:
            assert "cannot move backwards" in str(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(attempt, [logged, complete] * 32))

    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "complete"


def test_historical_receipt_failure_happens_before_remote_init(tmp_path):
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("blocked", encoding="utf-8")

    with pytest.raises(FileExistsError):
        importer._prepare_receipt(
            blocked_parent / "receipt.json",
            _historical_receipt_base(),
        )


def test_historical_finish_failure_leaves_recoverable_receipt(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    receipt = {
        **base,
        "status": "logged_pending_finish",
        "tracking": _historical_tracking_reference(base),
    }

    def fail_finish(_exit_code: int) -> None:
        raise RuntimeError("finish failed")

    claim = importer._prepare_receipt(receipt_path, base)
    assert claim is not None
    importer._mark_logging_started(claim)
    with pytest.raises(RuntimeError, match="finish failed"):
        importer._finish_with_receipt(claim, receipt, fail_finish)

    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == (
        "logged_pending_finish"
    )
    recovery_claim = importer._prepare_receipt(receipt_path, base)
    assert recovery_claim is not None and recovery_claim.resume == "allow"
    assert recovery_claim.needs_logging is False
    assert recovery_claim.tracking == _historical_tracking_reference(base)
    mismatched = {
        **receipt,
        "tracking": {
            **_historical_tracking_reference(base),
            "run_url": (
                "https://different.example/aegislm/runs/"
                f"source-v2-canary-import-{base['identity']}"
            ),
        },
    }
    with pytest.raises(ValueError, match="recovery reference"):
        importer._finish_with_receipt(
            recovery_claim, mismatched, lambda _exit_code: None
        )


def test_historical_concurrent_remote_work_has_exactly_one_owner(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    owner_ready = Event()
    release_owner = Event()
    calls: list[str] = []

    def upload() -> str:
        try:
            claim = importer._prepare_receipt(receipt_path, base)
        except RuntimeError:
            return "busy"
        assert claim is not None
        calls.append("init")
        owner_ready.set()
        assert release_owner.wait(timeout=2)
        importer._mark_logging_started(claim)
        calls.append("log")
        importer._finish_with_receipt(
            claim,
            {
                **base,
                "status": "logged_pending_finish",
                "tracking": _historical_tracking_reference(base),
            },
            lambda _exit_code: calls.append("finish"),
        )
        return "uploaded"

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(upload)
        assert owner_ready.wait(timeout=1)
        competitor = pool.submit(upload)
        assert competitor.result(timeout=1) == "busy"
        release_owner.set()
        assert owner.result(timeout=2) == "uploaded"

    assert calls == ["init", "log", "finish"]
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "complete"


def test_historical_ambiguous_log_requires_explicit_resolution(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    claim = importer._prepare_receipt(receipt_path, base)
    assert claim is not None
    importer._mark_logging_started(claim)
    claim.close()

    with pytest.raises(RuntimeError, match="outcome is ambiguous"):
        importer._prepare_receipt(receipt_path, base)

    recovery = importer._prepare_receipt(
        receipt_path,
        base,
        ambiguous_resolution="finish-only",
    )
    assert recovery is not None and recovery.needs_logging is False
    recovery.close()


def test_historical_receipt_rejects_complete_state_without_tracking(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    receipt_path.write_text(
        json.dumps(
            {
                **base,
                "status": "complete",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tracking linkage"):
        importer._prepare_receipt(
            receipt_path,
            base,
        )


def test_historical_receipt_rejects_unbound_tracking_url(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    receipt_path.write_text(
        json.dumps(
            {
                **base,
                "status": "logged_pending_finish",
                "tracking": {
                    "run_id": f"source-v2-canary-import-{base['identity']}",
                    "run_url": "https://wandb.example/run",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="run URL"):
        importer._prepare_receipt(receipt_path, base)


def test_historical_receipt_rejects_wrong_run_or_base_fields(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    base = _historical_receipt_base()
    wrong_run = {
        **base,
        "status": "complete",
        "tracking": {
            "run_id": "different-run",
            "run_url": "https://wandb.example/run",
        },
    }
    receipt_path.write_text(json.dumps(wrong_run), encoding="utf-8")
    with pytest.raises(ValueError, match="run ID"):
        importer._prepare_receipt(receipt_path, base)

    wrong_base = {**base, "gate_passed": True}
    receipt_path.write_text(
        json.dumps(
            {
                **wrong_base,
                "status": "complete",
                "tracking": {
                    "run_id": f"source-v2-canary-import-{base['identity']}",
                    "run_url": (
                        "https://wandb.example/aegislm/runs/"
                        f"source-v2-canary-import-{base['identity']}"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different inputs"):
        importer._prepare_receipt(receipt_path, base)
