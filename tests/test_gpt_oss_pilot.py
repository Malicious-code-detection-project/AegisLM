from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pilot", Path(__file__).parents[1] / "scripts/gpt_oss_pilot.py"
)
assert spec and spec.loader
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_never_scores_analysis_as_final() -> None:
    assert (
        pilot.parse_final('<|channel|>analysis<|message|>{"assessment":"present"}')[0]
        is None
    )
    raw = '<|channel|>analysis<|message|>{"assessment":"present"}<|end|><|start|>assistant<|channel|>final<|message|>{"assessment":"not_observed"}<|fim_suffix|>'
    assert pilot.parse_final(raw) == ("not_observed", "valid")
    assert pilot.parse_final(
        '<|channel|>final<|message|>{"assessment":"present"}<|return|>'
    ) == ("present", "valid")


def test_rejects_extra_keys() -> None:
    assert (
        pilot.parse_final(
            '<|channel|>final<|message|>{"assessment":"present","extra":1}'
        )[0]
        is None
    )


@pytest.mark.parametrize("metadata", ["JSON", "json"])
def test_harmony_constrained_json_is_valid_final(metadata) -> None:
    raw = f'<|channel|>analysis<|message|>analysis omitted<|end|><|start|>assistant<|channel|>final <|constrain|>{metadata}<|message|>{{"assessment":"present"}}<|return|>'
    assert pilot.parse_final(raw) == ("present", "valid")


def test_final_marker_quoted_inside_analysis_is_not_scored() -> None:
    raw = '<|channel|>analysis<|message|>Example: <|channel|>final<|message|>{"assessment":"present"}<|return|>'
    assert pilot.parse_final(raw)[0] is None


def test_split_is_reproducible_balanced_and_group_disjoint() -> None:
    rows = [
        {
            "id": str(i),
            "group_id": str(i),
            "code_sha256": str(i),
            "cwe": f"CWE-{i % 3}",
            "label": "present" if i % 2 else "not_observed",
        }
        for i in range(100)
    ]
    # A pair must stay together even when its labels differ.
    rows[1]["group_id"] = rows[0]["group_id"]
    a, b = pilot.split_reviewed(rows, 3)
    assert (a, b) == pilot.split_reviewed(rows, 3)
    assert len(a) == 80 and len(b) == 20
    assert sum(r["label"] == "present" for r in b) == 10
    assert not {r["group_id"] for r in a} & {r["group_id"] for r in b}


def test_duplicate_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        pilot.split_reviewed([{"id": "x"}, {"id": "x"}], 1)


def test_mask_and_truncation_guard() -> None:
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            return [1, 2] if kwargs["add_generation_prompt"] else [1, 2, 3, 4]

    row = {"messages": [{"role": "user"}, {"role": "assistant"}]}
    assert pilot.encode_record(Tokenizer(), row, 4)["labels"] == [-100, -100, 3, 4]
    with pytest.raises(ValueError, match="truncation"):
        pilot.encode_record(Tokenizer(), row, 3)


def test_direct_and_repeated_train_are_rejected(tmp_path, monkeypatch) -> None:
    config = {"run_root": str(tmp_path)}
    with pytest.raises(RuntimeError, match="direct phases"):
        pilot.authorize_child(config, "train")
    (tmp_path / "RUN_STARTED").write_text(
        json.dumps({"pid": os.getppid(), "nonce": "test"})
    )
    (tmp_path / "status.json").write_text(
        json.dumps({"status": "running", "phase": "train", "training_runs_allowed": 1})
    )
    monkeypatch.setenv("AEGISLM_PILOT_NONCE", "test")
    pilot.authorize_child(config, "train")
    with pytest.raises(FileExistsError):
        pilot.authorize_child(config, "train")


def test_review_composition_rejects_wrong_provenance() -> None:
    with pytest.raises(ValueError, match="88/12"):
        pilot.review_composition(
            [{"review_method": "AI-assisted structured source review"}] * 100
        )


def test_runtime_version_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(pilot.importlib.metadata, "version", lambda name: "wrong")
    with pytest.raises(RuntimeError, match="runtime mismatch"):
        pilot.verify_runtime({"expected_versions": {"torch": "pinned"}})


def test_review_method_must_match_actual_cwe() -> None:
    reviews = [
        {
            "id": "x",
            "review_method": "AI-assisted structured review of CWE-191/194/195 causal evidence; not expert sign-off",
        }
    ]
    with pytest.raises(ValueError, match="unexpected CWE"):
        pilot.verify_review_cwes(reviews, {"x": {"cwe": "CWE-999"}})
    pilot.verify_review_cwes(reviews, {"x": {"cwe": "CWE-191"}})


def test_snapshot_revision_mismatch(tmp_path) -> None:
    path = tmp_path / "pilot_snapshot_attestation.json"
    path.write_text(json.dumps({"repo_id": "openai/gpt-oss-20b", "revision": "wrong"}))
    with pytest.raises(RuntimeError, match="revision mismatch"):
        pilot.verify_snapshot(
            {
                "model_root": str(tmp_path),
                "model_attestation_sha256": pilot.digest(path),
                "model_id": "openai/gpt-oss-20b",
                "model_revision": "expected",
            }
        )
