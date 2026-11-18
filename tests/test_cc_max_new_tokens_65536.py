"""Generation cap propagation, validation isolation and termination accounting."""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import run_cc_max_new_tokens_65536 as sweep


def test_budget_subset_is_balanced_deterministic_and_has_no_gold() -> None:
    rows = [
        {
            "id": f"val-{label}-{i}",
            "messages": [
                {"role": "system", "content": "Judge the code."},
                {"role": "user", "content": "int f(void) { return 0; }"},
                {"role": "assistant", "content": json.dumps({"assessment": label})},
            ],
        }
        for label in ("present", "not_observed")
        for i in range(60)
    ]
    original = deepcopy(rows)
    prompts, gold = sweep.select_rows(rows, 2)
    assert (prompts, gold) == sweep.select_rows(list(reversed(rows)), 2)
    assert len(prompts) == 2
    assert {r["expected_output"]["assessment"] for r in gold} == {
        "present",
        "not_observed",
    }
    assert [r["id"] for r in prompts] == [r["id"] for r in gold]
    assert all(
        [m["role"] for m in r["messages"]] == ["system", "user"] for r in prompts
    )
    assert rows == original


@pytest.mark.parametrize("budgets", [[128, True], [128, 65537], [512, 128], [128, 128]])
def test_invalid_budget_plans_are_rejected(tmp_path: Path, budgets: list[Any]) -> None:
    config = json.loads(Path("configs/cc_max_new_tokens_65536_v1.json").read_text())
    config["budgets"] = budgets
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="unsupported generation"):
        sweep.load_config(path)


@pytest.mark.parametrize(
    ("ids", "maximum", "elapsed", "expected"),
    [
        ([1, 200002], 2, 350.0, "eos"),
        ([1, 199999], 65536, 1.0, "eos"),
        ([1, 2], 2, 301.0, "token_limit"),
        ([1, 2], 65536, 301.0, "time_limit"),
        ([1, 2], 65536, 2.0, "other"),
    ],
)
def test_time_guard_is_not_reported_as_token_exhaustion(
    ids: list[int], maximum: int, elapsed: float, expected: str
) -> None:
    assert sweep.stop_reason(ids, maximum, elapsed, 300) == expected


class Inputs(dict[str, Any]):
    def to(self, device: str) -> Inputs:
        assert device == "cuda"
        return self


class Tokens:
    shape = (1, 3)

    def __getitem__(self, item: Any) -> Tokens:
        return self

    def tolist(self) -> list[int]:
        return [1, 2, 200002]


def test_actual_generation_receives_65536_cap_and_preserves_only_final_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def generate(**kwargs: Any) -> Tokens:
        calls.append(kwargs)
        return Tokens()

    def template(messages: Any, **kwargs: Any) -> Inputs:
        assert [m["role"] for m in messages[0]] == ["system", "user"]
        assert kwargs["reasoning_effort"] == "low"
        return Inputs(input_ids=Tokens())

    cuda = SimpleNamespace(
        synchronize=lambda: None,
        reset_peak_memory_stats=lambda: None,
        max_memory_allocated=lambda: 1024**2,
        max_memory_reserved=lambda: 2 * 1024**2,
    )
    monkeypatch.setattr(
        sweep.importlib,
        "import_module",
        lambda name: SimpleNamespace(cuda=cuda, inference_mode=nullcontext),
    )
    model = SimpleNamespace(generate=generate)
    tokenizer = SimpleNamespace(
        apply_chat_template=template,
        decode=lambda ids, **kwargs: (
            "<|channel|>analysis<|message|>reasoning"
            + sweep.FINAL
            + '{"assessment":"present"}<|return|>'
        ),
    )
    row: dict[str, Any] = {
        "id": "val",
        "messages": [{"role": "system"}, {"role": "user"}],
    }
    prediction = sweep.generate_one(model, tokenizer, row, "base", 65536, 131072, 300)
    assert calls[0]["max_new_tokens"] == 65536
    assert calls[0]["max_time"] == 300
    assert calls[0]["do_sample"] is False
    assert prediction.raw_output == '{"assessment":"present"}'
    assert prediction.generation is not None
    assert prediction.generation["max_new_tokens"] == 65536
    assert prediction.generation["stop_reason"] == "eos"
    calls.clear()
    with pytest.raises(ValueError, match="prompt plus requested output"):
        sweep.generate_one(model, tokenizer, row, "base", 65536, 65536, 300)
    assert not calls
    row["messages"].append({"role": "assistant"})
    with pytest.raises(ValueError, match="gold"):
        sweep.generate_one(model, tokenizer, row, "base", 65536, 131072, 300)
