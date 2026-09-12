import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from aegislm.tracking.receipt import (
    build_tracking_receipt,
    finish_with_tracking_receipt,
    mark_tracking_logging_started,
    prepare_tracking_receipt,
    release_active_tracking_claims,
    tracking_payload_sha256,
    tracking_run_id,
    write_tracking_receipt,
)


def _tracking_reference(base):
    run_id = f"source-v2-{base['kind']}-{base['identity']}"
    return {
        "project": "aegislm",
        "run_id": run_id,
        "run_url": f"https://wandb.example/aegislm/runs/{run_id}",
    }


def test_tracking_receipt_first_attempt_recovery_and_complete_noop(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "a" * 64)

    first_claim = prepare_tracking_receipt(path, base)
    assert first_claim is not None and first_claim.resume == "never"
    first_claim.close()
    recovery_claim = prepare_tracking_receipt(path, base)
    assert recovery_claim is not None and recovery_claim.resume == "allow"
    mark_tracking_logging_started(recovery_claim)
    finish_with_tracking_receipt(
        recovery_claim,
        _tracking_reference(base),
        lambda exit_code: None,
    )
    assert json.loads(path.read_text())["status"] == "complete"
    assert prepare_tracking_receipt(path, base) is None


def test_tracking_receipt_finish_failure_preserves_recovery_state(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("comparison", "b" * 64)

    def fail_finish(_exit_code: int) -> None:
        raise RuntimeError("finish failed")

    claim = prepare_tracking_receipt(path, base)
    assert claim is not None
    mark_tracking_logging_started(claim)
    with pytest.raises(RuntimeError, match="finish failed"):
        finish_with_tracking_receipt(
            claim,
            _tracking_reference(base),
            fail_finish,
        )

    assert json.loads(path.read_text())["status"] == "logged_pending_finish"
    recovery_claim = prepare_tracking_receipt(path, base)
    assert recovery_claim is not None and recovery_claim.resume == "allow"
    assert recovery_claim.needs_logging is False
    assert recovery_claim.tracking == _tracking_reference(base)
    calls = ["init"]
    if recovery_claim.needs_logging:
        calls.append("log")
    finish_with_tracking_receipt(
        recovery_claim,
        _tracking_reference(base),
        lambda _exit_code: calls.append("finish"),
    )
    assert calls == ["init", "finish"]
    assert json.loads(path.read_text())["status"] == "complete"


def test_active_claim_is_retained_until_error_finish_and_explicit_release(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "8" * 64)
    claim = prepare_tracking_receipt(path, base)
    assert claim is not None
    del claim

    with pytest.raises(RuntimeError, match="already owned"):
        prepare_tracking_receipt(path, base)

    events: list[str] = []
    try:
        events.append("error-finish")
    finally:
        release_active_tracking_claims()
        events.append("claim-release")

    recovery = prepare_tracking_receipt(path, base)
    assert recovery is not None
    recovery.close()
    assert events == ["error-finish", "claim-release"]


def test_receipt_claim_excludes_a_competing_process(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "7" * 64)
    claim = prepare_tracking_receipt(path, base)
    assert claim is not None
    script = (
        "from pathlib import Path\n"
        "from aegislm.tracking import build_tracking_receipt, "
        "prepare_tracking_receipt\n"
        f"path = Path({str(path)!r})\n"
        "base = build_tracking_receipt('evaluation', '7' * 64)\n"
        "try:\n"
        "    prepare_tracking_receipt(path, base)\n"
        "except RuntimeError:\n"
        "    raise SystemExit(23)\n"
        "raise SystemExit(24)\n"
    )

    result = subprocess.run([sys.executable, "-c", script], check=False)

    claim.close()
    assert result.returncode == 23


def test_tracking_receipt_does_not_follow_predictable_temp_symlink(tmp_path):
    path = tmp_path / "tracking.json"
    target = tmp_path / "do-not-overwrite"
    target.write_text("preserved", encoding="utf-8")
    path.with_name(path.name + ".tmp").symlink_to(target)

    base = build_tracking_receipt("evaluation", "c" * 64)
    write_tracking_receipt(path, {**base, "status": "pending"})

    assert target.read_text(encoding="utf-8") == "preserved"
    assert json.loads(path.read_text(encoding="utf-8")) == {**base, "status": "pending"}


def test_tracking_receipt_concurrent_writes_never_publish_partial_json(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "d" * 64)
    payloads = [
        {**base, "status": "pending", "writer": index, "padding": "x" * 8_192}
        for index in range(32)
    ]
    write_tracking_receipt(path, payloads[0])
    reader_started = Event()
    stop_reader = Event()

    def read_while_writing() -> int:
        reads = 0
        reader_started.set()
        while not stop_reader.is_set():
            assert json.loads(path.read_text(encoding="utf-8")) in payloads
            reads += 1
        return reads

    with ThreadPoolExecutor(max_workers=8) as pool:
        reader = pool.submit(read_while_writing)
        assert reader_started.wait(timeout=1)
        try:
            list(
                pool.map(
                    lambda payload: write_tracking_receipt(path, payload), payloads
                )
            )
        finally:
            stop_reader.set()
        assert reader.result(timeout=1) > 0

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved in payloads
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_tracking_receipt_first_acquisition_is_exclusive(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "e" * 64)

    def acquire(_index):
        try:
            return prepare_tracking_receipt(path, base)
        except RuntimeError as exc:
            assert "already owned" in str(exc)
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire, range(32)))

    claims = [claim for claim in results if claim is not None]
    assert len(claims) == 1
    assert claims[0].resume == "never"
    claims[0].close()
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "pending"


def test_concurrent_remote_work_has_exactly_one_owner(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "9" * 64)
    owner_ready = Event()
    release_owner = Event()
    calls: list[str] = []

    def upload() -> str:
        try:
            claim = prepare_tracking_receipt(path, base)
        except RuntimeError:
            return "busy"
        if claim is None:
            return "complete"
        calls.append("init")
        owner_ready.set()
        assert release_owner.wait(timeout=2)
        mark_tracking_logging_started(claim)
        calls.append("log")
        finish_with_tracking_receipt(
            claim,
            _tracking_reference(base),
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
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "complete"


@pytest.mark.parametrize(
    "receipt",
    [
        {"status": "complete"},
        {
            **build_tracking_receipt("evaluation", "f" * 64),
            "status": "complete",
            "tracking": {"run_id": "only-id"},
        },
    ],
)
def test_tracking_receipt_rejects_malformed_complete_state(tmp_path, receipt):
    path = tmp_path / "tracking.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ValueError):
        prepare_tracking_receipt(path, build_tracking_receipt("evaluation", "f" * 64))


def test_tracking_receipt_rejects_unrelated_run_identity(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "a" * 64)

    with pytest.raises(ValueError, match="run ID"):
        claim = prepare_tracking_receipt(path, base)
        assert claim is not None
        mark_tracking_logging_started(claim)
        finish_with_tracking_receipt(
            claim,
            {
                "run_id": "unrelated-run",
                "run_url": "https://wandb.example/runs/unrelated-run",
            },
            lambda _exit_code: None,
        )


def test_ambiguous_remote_log_requires_explicit_no_relog_resolution(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "6" * 64)
    claim = prepare_tracking_receipt(path, base)
    assert claim is not None
    mark_tracking_logging_started(claim)
    remote_calls = ["log-acknowledged"]
    claim.close()

    with pytest.raises(RuntimeError, match="outcome is ambiguous"):
        prepare_tracking_receipt(path, base)

    recovery = prepare_tracking_receipt(path, base, ambiguous_resolution="finish-only")
    assert recovery is not None and recovery.needs_logging is False
    remote_calls.append("init")
    if recovery.needs_logging:
        remote_calls.append("log")
    finish_with_tracking_receipt(
        recovery,
        _tracking_reference(base),
        lambda _exit_code: remote_calls.append("finish"),
    )

    assert remote_calls == ["log-acknowledged", "init", "finish"]
    assert json.loads(path.read_text())["status"] == "complete"


def test_remote_init_failure_leaves_ambiguous_receipt(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "3" * 64)
    claim = prepare_tracking_receipt(path, base)
    assert claim is not None
    mark_tracking_logging_started(claim)

    with pytest.raises(RuntimeError, match="simulated init failure"):
        try:
            raise RuntimeError("simulated init failure")
        finally:
            claim.close()

    assert json.loads(path.read_text())["status"] == "logging_ambiguous"
    with pytest.raises(RuntimeError, match="outcome is ambiguous"):
        prepare_tracking_receipt(path, base)


def test_ambiguous_remote_log_can_be_explicitly_retried(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "5" * 64)
    claim = prepare_tracking_receipt(path, base)
    assert claim is not None
    mark_tracking_logging_started(claim)
    claim.close()

    retry = prepare_tracking_receipt(path, base, ambiguous_resolution="retry-logging")
    assert retry is not None and retry.needs_logging is True
    assert json.loads(path.read_text())["status"] == "pending"
    retry.close()


def test_reconciliation_flag_requires_existing_ambiguous_receipt(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("evaluation", "4" * 64)

    with pytest.raises(ValueError, match="existing logging_ambiguous"):
        prepare_tracking_receipt(path, base, ambiguous_resolution="finish-only")

    assert not path.exists()


@pytest.mark.parametrize("kind", ["training", "gate"])
def test_training_and_gate_receipts_have_deterministic_run_ids(kind):
    digest = tracking_payload_sha256({"recipe": "unsloth_v2", "stage": "canary"})
    base = build_tracking_receipt(kind, digest)

    assert tracking_run_id(base) == f"source-v2-{kind}-{base['identity']}"


def test_tracking_receipt_rejects_clobber_and_status_regression(tmp_path):
    path = tmp_path / "tracking.json"
    path.write_text("unrelated", encoding="utf-8")
    base = build_tracking_receipt("training", "1" * 64)
    with pytest.raises(ValueError, match="invalid W&B receipt"):
        write_tracking_receipt(path, {**base, "status": "pending"})

    path.unlink()
    reference = _tracking_reference(base)
    write_tracking_receipt(path, {**base, "status": "complete", "tracking": reference})
    with pytest.raises(ValueError, match="cannot move backwards"):
        write_tracking_receipt(path, {**base, "status": "pending"})


def test_tracking_receipt_rejects_git_tracked_destination():
    base = build_tracking_receipt("training", "2" * 64)

    with pytest.raises(ValueError, match="Git-ignored"):
        write_tracking_receipt(
            Path("docs/unsafe-wandb-receipt.json"), {**base, "status": "pending"}
        )


def test_concurrent_receipt_updates_cannot_downgrade_complete(tmp_path):
    path = tmp_path / "tracking.json"
    base = build_tracking_receipt("gate", "3" * 64)
    reference = _tracking_reference(base)
    pending = {**base, "status": "pending"}
    logged = {**base, "status": "logged_pending_finish", "tracking": reference}
    complete = {**logged, "status": "complete"}
    write_tracking_receipt(path, pending)

    def attempt(payload):
        try:
            write_tracking_receipt(path, payload)
        except ValueError as exc:
            assert "cannot move backwards" in str(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(attempt, [logged, complete] * 32))

    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "complete"
