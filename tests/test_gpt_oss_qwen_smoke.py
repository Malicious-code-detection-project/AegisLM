"""CPU checks for bounded smoke and transport normalization."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("qwen_smoke", SCRIPTS / "gpt_oss_qwen_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_provenance_accepts_record_id_and_detects_conflict(tmp_path):
    path = tmp_path / "metadata.jsonl"
    first = {"record_id": "one", "group_id": "group", "code_sha256": "abc"}
    path.write_text(json.dumps(first) + "\n", encoding="utf-8")
    result, _ = smoke.groups({"group_metadata": [str(path)]})
    assert result == {"one": ("group", "abc")}
    for second in (
        dict(first, code_sha256="def"),
        dict(first, group_id="other"),
        dict(first, id="two"),
        dict(first, code_sha256=None),
    ):
        path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            smoke.groups({"group_metadata": [str(path)]})


def test_transport_strips_one_terminal_marker():
    assert smoke.normalize_completion(' {"assessment":"present"}<|return|>\n') == '{"assessment":"present"}'
    assert smoke.normalize_completion('{}<|return|>') == '{}'


def test_transport_retains_invalid_control_tokens_and_analysis():
    for raw in ('{}<|fim_suffix|>', '{}<|return|><|pad|>', '<|channel|>analysis<|message|>{}', '```json\n{}\n```', '{} trailing'):
        assert smoke.normalize_completion(raw) == raw
    assert smoke.normalize_completion('{}<|return|><|return|>') == '{}<|return|>'


def test_eos_uses_only_validated_native_token():
    class Tokenizer:
        eos_token = "<|return|>"
        eos_token_id = 200002

        def convert_tokens_to_ids(self, token):
            raise AssertionError("alternate EOS tokens must never be queried")

    tokenizer = Tokenizer()
    assert smoke.validated_eos_id(tokenizer) == 200002
    for invalid in (None, -1, "200002", True):
        tokenizer.eos_token_id = invalid
        with pytest.raises(ValueError):
            smoke.validated_eos_id(tokenizer)
    tokenizer.eos_token_id = 200002
    tokenizer.eos_token = "<|fim_suffix|>"
    with pytest.raises(ValueError):
        smoke.validated_eos_id(tokenizer)


def test_execution_budget_cannot_expand():
    config = dict(max_steps=5, gradient_accumulation_steps=32, max_wall_seconds=3600, gpu=0, max_length=4096, generation_limits={"decision":128,"evidence":512})
    smoke.bounded(config)
    for key, value in (("max_steps",6),("max_wall_seconds",3601),("max_wall_seconds",0),("gradient_accumulation_steps",4),("gpu",1),("full_training_approved",True)):
        with pytest.raises(ValueError):
            smoke.bounded(dict(config, **{key:value}))
