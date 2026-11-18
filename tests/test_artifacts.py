from pathlib import Path

import pytest

from aegislm.artifacts import (
    load_bounded_json_object,
    load_bounded_jsonl_objects,
    validate_artifact_path_plan,
    write_text_artifact,
)


def test_artifact_plan_rejects_tracked_and_duplicate_outputs(tmp_path):
    with pytest.raises(ValueError, match="Git-ignored"):
        validate_artifact_path_plan(
            inputs=(),
            outputs=(Path("docs/unsafe-result.json"),),
            require_new=False,
        )

    output = tmp_path / "result.json"
    with pytest.raises(ValueError, match="distinct"):
        validate_artifact_path_plan(
            inputs=(), outputs=(output, output), require_new=False
        )


def test_artifact_plan_rejects_input_alias_and_symlink(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source", encoding="utf-8")
    link = tmp_path / "result.json"
    link.symlink_to(source)

    with pytest.raises(ValueError, match="symlink"):
        validate_artifact_path_plan(
            inputs=(source,), outputs=(link,), require_new=False
        )
    with pytest.raises(ValueError, match="alias"):
        validate_artifact_path_plan(
            inputs=(source,), outputs=(source,), require_new=False
        )


def test_bounded_json_readers_reject_symlinked_parent(tmp_path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    (real_parent / "object.json").write_text("{}", encoding="utf-8")
    (real_parent / "rows.jsonl").write_text("{}\n", encoding="utf-8")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        load_bounded_json_object(
            linked_parent / "object.json", description="test object"
        )
    with pytest.raises(ValueError, match="traverse a symlink"):
        load_bounded_jsonl_objects(
            linked_parent / "rows.jsonl", description="test rows"
        )


def test_text_artifact_is_non_clobbering_and_idempotent(tmp_path):
    output = tmp_path / "result.json"
    write_text_artifact(output, "same\n", idempotent=True)
    write_text_artifact(output, "same\n", idempotent=True)

    with pytest.raises(FileExistsError, match="already exists"):
        write_text_artifact(output, "different\n", idempotent=True)
    assert output.read_text(encoding="utf-8") == "same\n"


def test_text_artifact_does_not_follow_output_symlink(tmp_path):
    target = tmp_path / "target"
    target.write_text("preserved", encoding="utf-8")
    output = tmp_path / "result"
    output.symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        write_text_artifact(output, "replacement")
    assert target.read_text(encoding="utf-8") == "preserved"


def test_text_artifact_checks_git_safety_before_identical_return():
    output = Path("docs/existing-artifact-safety-test.json")
    output.write_text("same\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="Git-ignored"):
            write_text_artifact(output, "same\n", idempotent=True)
    finally:
        output.unlink(missing_ok=True)
