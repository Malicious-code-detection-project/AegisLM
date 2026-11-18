"""The default entrypoint must not require ignored datasets or ML assets."""

import main as entrypoint
import pytest


def test_default_main_is_independent_of_local_assets(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        entrypoint,
        "inspect_training_example",
        lambda *_: pytest.fail("default main must not inspect training data"),
    )
    entrypoint.main([])
    assert "AegisLM scaffold is ready." in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_main_requires_explicit_inspection_for_tokenizer():
    with pytest.raises(SystemExit):
        entrypoint.main(["--tokenizer", "missing-adapter"])


def test_main_inspection_is_explicit_and_tokenizer_optional(monkeypatch):
    requests = []
    monkeypatch.setattr(
        entrypoint,
        "inspect_training_example",
        lambda *args: requests.append(args),
    )
    entrypoint.main(["--inspect-training-example", "--dataset", "fixture.jsonl"])
    assert str(requests[0][0]) == "fixture.jsonl"
    assert requests[0][1] is None
