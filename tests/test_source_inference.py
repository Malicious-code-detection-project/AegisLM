import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import aegislm.inference.source as source_inference

from aegislm.evaluation.harness import load_predictions
from aegislm.inference.adapter import (
    adapter_directory_sha256,
    make_unsloth_response_generator,
    validate_unsloth_runtime_identity,
)
from aegislm.inference.source import (
    SOURCE_GENERATION_PROTOCOL_VERSION,
    make_openai_compatible_source_generator,
    run_source_inference,
    source_generation_protocol_metadata,
)


class _HTTPResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def read(self, limit: int) -> bytes:
        assert limit == source_inference.MAX_OPENAI_RESPONSE_BYTES + 1
        return self.body[:limit]


def _install_http_response(monkeypatch, body: bytes):
    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 3.0
            assert request.get_header("Authorization") == "Bearer local-secret"
            return _HTTPResponse(body)

    def build_opener(*handlers):
        assert len(handlers) == 2
        assert isinstance(handlers[0], source_inference.urllib.request.ProxyHandler)
        assert handlers[0].proxies == {}
        assert isinstance(handlers[1], source_inference._NoRedirectHandler)
        return Opener()

    monkeypatch.setattr(source_inference.urllib.request, "build_opener", build_opener)


def test_openai_compatible_generator_disables_redirects_and_bounds_response(
    monkeypatch,
):
    monkeypatch.setenv("AEGISLM_INFERENCE_API_KEY", "local-secret")
    body = json.dumps(
        {"choices": [{"message": {"content": '{"assessment":"present"}'}}]}
    ).encode()
    _install_http_response(monkeypatch, body)
    generator = make_openai_compatible_source_generator(
        base_url="http://127.0.0.1:8000",
        model_id="local-model",
        max_new_tokens=512,
        temperature=0.0,
        constrained=False,
        timeout_seconds=3.0,
    )

    assert generator([]) == '{"assessment":"present"}'
    assert (
        source_inference._NoRedirectHandler().redirect_request(
            None, None, 302, "redirect", {}, "https://untrusted.invalid"
        )
        is None
    )


def test_openai_compatible_generator_rejects_oversized_or_deep_response(
    monkeypatch,
):
    monkeypatch.setenv("AEGISLM_INFERENCE_API_KEY", "local-secret")
    generator = make_openai_compatible_source_generator(
        base_url="http://127.0.0.1:8000",
        model_id="local-model",
        max_new_tokens=512,
        temperature=0.0,
        constrained=False,
        timeout_seconds=3.0,
    )
    _install_http_response(
        monkeypatch, b"x" * (source_inference.MAX_OPENAI_RESPONSE_BYTES + 1)
    )
    with pytest.raises(ValueError, match="response exceeds"):
        generator([])

    nested = '{"choices":' + "[" * 200 + "0" + "]" * 200 + "}"
    _install_http_response(monkeypatch, nested.encode())
    with pytest.raises(ValueError, match="invalid JSON"):
        generator([])


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.example.com",
        "http://10.0.0.8:8000",
        "http://localhost:8000",
        "http://localhost.evil.invalid:8000",
        "http://user:password@127.0.0.1:8000",
        "http://[::1%25lo]:8000",
        "http://[::1%lo]:8000",
        "file:///tmp/model.sock",
    ],
)
def test_openai_compatible_generator_rejects_non_loopback_endpoints(base_url):
    with pytest.raises(ValueError, match="loopback"):
        make_openai_compatible_source_generator(
            base_url=base_url,
            model_id="local-model",
            max_new_tokens=512,
            temperature=0.0,
            constrained=False,
        )


@pytest.mark.parametrize(
    "base_url",
    ["http://127.0.0.1:8000", "http://127.99.1.2:8000", "http://[::1]:8000"],
)
def test_openai_compatible_generator_accepts_explicit_loopback_endpoints(base_url):
    generator = make_openai_compatible_source_generator(
        base_url=base_url,
        model_id="local-model",
        max_new_tokens=512,
        temperature=0.0,
        constrained=False,
    )

    assert callable(generator)


def test_openai_compatible_generator_disables_ambient_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://untrusted.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8080")
    monkeypatch.setenv("AEGISLM_INFERENCE_API_KEY", "local-secret")
    body = json.dumps(
        {"choices": [{"message": {"content": '{"assessment":"present"}'}}]}
    ).encode()
    _install_http_response(monkeypatch, body)
    generator = make_openai_compatible_source_generator(
        base_url="http://127.0.0.1:8000",
        model_id="local-model",
        max_new_tokens=512,
        temperature=0.0,
        constrained=False,
        timeout_seconds=3.0,
    )

    assert generator([]) == '{"assessment":"present"}'


def test_source_inference_never_requires_gold(tmp_path):
    dataset = tmp_path / "challenge.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case",
                "messages": [
                    {"role": "system", "content": "Return JSON."},
                    {
                        "role": "user",
                        "content": (
                            '{"scope":{"target_cwe":"CWE-120"},'
                            '"source_code":"return 0;"}'
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    count = run_source_inference(
        dataset_path=dataset,
        predictions_path=predictions,
        model_id="mock",
        run_id="smoke",
        generate_response=lambda _messages: '{"assessment":"not_observed"}',
    )

    output = json.loads(predictions.read_text(encoding="utf-8"))
    assert count == 1
    assert output["record_id"] == "case"
    assert "expected_output" not in output
    assert len(output["metadata"]["challenge_file_sha256"]) == 64
    assert len(output["metadata"]["challenge_records_sha256"]) == 64

    original = predictions.read_bytes()
    with pytest.raises(FileExistsError):
        run_source_inference(
            dataset_path=dataset,
            predictions_path=predictions,
            model_id="mock",
            run_id="rerun",
            generate_response=lambda _messages: '{"assessment":"present"}',
        )
    assert predictions.read_bytes() == original


def test_source_inference_preserves_harmony_and_finish_metadata(tmp_path):
    dataset = tmp_path / "challenge.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case",
                "messages": [
                    {"role": "system", "content": "Return JSON."},
                    {
                        "role": "user",
                        "content": (
                            '{"scope":{"target_cwe":"CWE-120"},"source_code":"x;"}'
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def generate(_messages):
        return '{"assessment":"not_observed"}'

    setattr(
        generate,
        "aegislm_last_generation",
        {
            "raw_generation": (
                "<|channel|>analysis<|message|>ok"
                '<|channel|>final<|message|>{"assessment":"not_observed"}'
                "<|return|>"
            ),
            "scoreable_output": '{"assessment":"not_observed"}',
            "generated_token_count": 9,
            "finish_reason": "eos",
            "eos_token_id": 200002,
        },
    )

    run_source_inference(
        dataset_path=dataset,
        predictions_path=predictions,
        model_id="mock",
        run_id="smoke",
        generate_response=generate,
    )

    output = json.loads(predictions.read_text(encoding="utf-8"))
    assert output["raw_output"] == '{"assessment":"not_observed"}'
    assert output["scoreable_output"] == output["raw_output"]
    assert output["raw_generation"].startswith("<|channel|>analysis")
    assert output["generation"] == {
        "generated_token_count": 9,
        "finish_reason": "eos",
        "eos_token_id": 200002,
    }
    loaded = load_predictions(predictions)[0]
    assert loaded.raw_generation == output["raw_generation"]
    assert loaded.generation == output["generation"]
    assert loaded.predictions_sha256 is not None
    assert len(loaded.predictions_sha256) == 64


def test_unsloth_source_generator_uses_canonical_protocol(monkeypatch):
    tokenizer = _FakeTokenizer()
    model = _FakeModel()

    class FakeFastLanguageModel:
        @staticmethod
        def from_pretrained(**kwargs):
            assert kwargs["max_seq_length"] == 2048
            return model, tokenizer

        @staticmethod
        def for_inference(runtime_model):
            assert runtime_model is model

    fake_unsloth = SimpleNamespace(FastLanguageModel=FakeFastLanguageModel)
    fake_transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(
            from_pretrained=lambda *_args, **_kwargs: tokenizer
        )
    )
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            get_device_properties=lambda _index: SimpleNamespace(name="test-gpu"),
            get_device_capability=lambda _index: (9, 0),
        ),
        version=SimpleNamespace(cuda="test-cuda"),
    )

    def fake_import(name):
        return {
            "transformers": fake_transformers,
            "unsloth": fake_unsloth,
            "torch": fake_torch,
        }[name]

    monkeypatch.setattr(
        "aegislm.inference.adapter.importlib.import_module", fake_import
    )
    generator = make_unsloth_response_generator(
        adapter_path=None,
        revision="a" * 40,
        expected_base_model_id="runtime/model",
    )

    output = generator([{"role": "user", "content": "inspect"}])

    assert output == '{"assessment":"not_observed"}'
    assert tokenizer.padding_side == "left"
    assert tokenizer.template_kwargs == {
        "tokenize": True,
        "add_generation_prompt": True,
        "padding": True,
        "return_tensors": "pt",
        "return_dict": True,
        "reasoning_effort": "low",
    }
    assert model.generation_kwargs["max_new_tokens"] == 512
    assert model.generation_kwargs["do_sample"] is False
    assert model.generation_kwargs["pad_token_id"] == 200017
    assert model.generation_kwargs["eos_token_id"] == [200002, 199999]
    assert tokenizer.decoded_token_ids == [[10, 200002], [10, 200002]]
    assert getattr(generator, "aegislm_last_generation") == {
        "raw_generation": tokenizer.raw_generation,
        "scoreable_output": '{"assessment":"not_observed"}',
        "generated_token_count": 2,
        "finish_reason": "eos",
        "eos_token_id": 200002,
        "generated_token_ids": [10, 200002],
        "harmony_prefix": True,
        "harmony_final": True,
    }
    provenance = getattr(generator, "aegislm_provenance")
    assert provenance["generation_protocol_version"] == (
        SOURCE_GENERATION_PROTOCOL_VERSION
    )
    assert len(provenance["generation_protocol_sha256"]) == 64


def test_source_cli_defaults_to_512_tokens(tmp_path):
    dataset = tmp_path / "challenge.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case",
                "messages": [
                    {"role": "system", "content": "Return JSON."},
                    {
                        "role": "user",
                        "content": (
                            '{"scope":{"target_cwe":"CWE-120"},"source_code":"x;"}'
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/run_source_inference.py",
            "--dataset",
            str(dataset),
            "--predictions",
            str(predictions),
            "--model-id",
            "mock",
            "--run-id",
            "defaults",
            "--backend",
            "mock",
            "--mock-raw-output",
            '{"assessment":"not_observed"}',
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(predictions.read_text(encoding="utf-8"))
    assert output["metadata"]["max_new_tokens"] == 512
    assert output["metadata"]["max_seq_length"] == 2048
    assert len(output["metadata"]["generation_protocol_sha256"]) == 64


def test_unsloth_protocol_rejects_sampling():
    with pytest.raises(ValueError, match="must be deterministic"):
        source_generation_protocol_metadata(
            backend="unsloth",
            mode="raw",
            max_new_tokens=512,
            max_seq_length=2048,
            temperature=0.1,
        )


@pytest.mark.parametrize(
    ("max_new_tokens", "max_seq_length", "message"),
    ((511, 2048, "max_new_tokens=512"), (512, 1024, "max_seq_length=2048")),
)
def test_unsloth_protocol_rejects_noncanonical_limits(
    max_new_tokens, max_seq_length, message
):
    with pytest.raises(ValueError, match=message):
        source_generation_protocol_metadata(
            backend="unsloth",
            mode="raw",
            max_new_tokens=max_new_tokens,
            max_seq_length=max_seq_length,
            temperature=0.0,
        )


def test_adapter_directory_digest_covers_config_and_rejects_symlinks(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    config = adapter / "adapter_config.json"
    config.write_text('{"revision":"one"}', encoding="utf-8")
    adapter.joinpath("adapter_model.safetensors").write_bytes(b"weights")
    before = adapter_directory_sha256(adapter)

    config.write_text('{"revision":"two"}', encoding="utf-8")
    assert adapter_directory_sha256(adapter) != before

    adapter.joinpath("escaped").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="unsafe entry"):
        adapter_directory_sha256(adapter)


def test_adapter_directory_digest_rejects_symlinked_parent(tmp_path):
    real_parent = tmp_path / "real-parent"
    adapter = real_parent / "adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        adapter_directory_sha256(linked_parent / "adapter")


def test_legacy_unsloth_generator_reaches_legacy_loader_with_1024_tokens(
    tmp_path, monkeypatch
):
    adapter = tmp_path / "legacy-adapter"
    adapter.mkdir()
    (adapter / "weights.bin").write_bytes(b"legacy")

    class LegacyLoader:
        @staticmethod
        def from_pretrained(**kwargs):
            assert kwargs["model_name"] == str(adapter)
            assert kwargs["max_seq_length"] == 1024
            raise RuntimeError("legacy loader reached")

    monkeypatch.setattr(
        "aegislm.inference.adapter.importlib.import_module",
        lambda name: (
            SimpleNamespace(FastLanguageModel=LegacyLoader)
            if name == "unsloth"
            else None
        ),
    )

    with pytest.raises(RuntimeError, match="legacy loader reached"):
        make_unsloth_response_generator(
            adapter_path=adapter,
            max_seq_length=1024,
            max_new_tokens=1024,
        )


def test_unsloth_runtime_identity_rejects_resolved_revision_drift(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    adapter.joinpath("adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": "runtime/model",
                "revision": "a" * 40,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="resolved revision mismatch"):
        validate_unsloth_runtime_identity(
            adapter_path=adapter,
            expected_base_model_id="runtime/model",
            expected_revision="a" * 40,
            resolved_model_id="runtime/model",
            resolved_revision="b" * 40,
        )


def test_unsloth_runtime_identity_rejects_unknown_or_wrong_adapter_base(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    adapter.joinpath("adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": "wrong/model",
                "revision": "a" * 40,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the request"):
        validate_unsloth_runtime_identity(
            adapter_path=adapter,
            expected_base_model_id="runtime/model",
            expected_revision="a" * 40,
            resolved_model_id="runtime/model",
            resolved_revision=None,
        )

    adapter.joinpath("adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": "runtime/model",
                "revision": "a" * 40,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="did not expose"):
        validate_unsloth_runtime_identity(
            adapter_path=adapter,
            expected_base_model_id="runtime/model",
            expected_revision="a" * 40,
            resolved_model_id="runtime/model",
            resolved_revision=None,
        )


def test_unsloth_runtime_identity_rejects_resolved_model_drift():
    with pytest.raises(RuntimeError, match="resolved model mismatch"):
        validate_unsloth_runtime_identity(
            adapter_path=Path("remote/model"),
            expected_base_model_id="runtime/model",
            expected_revision="a" * 40,
            resolved_model_id="wrong/model",
            resolved_revision="a" * 40,
        )


def test_unsloth_generator_rejects_trackable_or_symlinked_cache_before_loading(
    tmp_path,
):
    with pytest.raises(ValueError, match="Git-ignored"):
        make_unsloth_response_generator(
            adapter_path=None,
            cache_dir="aegislm/downloads",
            revision="a" * 40,
            expected_base_model_id="runtime/model",
        )

    real_cache = tmp_path / "real-cache"
    real_cache.mkdir()
    linked_cache = tmp_path / "linked-cache"
    linked_cache.symlink_to(real_cache, target_is_directory=True)
    with pytest.raises(ValueError, match="traverse a symlink"):
        make_unsloth_response_generator(
            adapter_path=None,
            cache_dir=linked_cache,
            revision="a" * 40,
            expected_base_model_id="runtime/model",
        )


@pytest.mark.parametrize(
    ("adapter_path", "revision", "expected_base_model_id"),
    [(None, "a" * 40, "runtime/model"), ("missing-adapter", None, None)],
)
def test_unsloth_generator_rejects_implicit_cache_before_pinned_or_legacy_loader(
    adapter_path, revision, expected_base_model_id
):
    with pytest.raises(ValueError, match="explicit Git-safe model cache"):
        make_unsloth_response_generator(
            adapter_path=adapter_path,
            cache_dir=None,
            revision=revision,
            expected_base_model_id=expected_base_model_id,
        )


class _FakeTensor:
    shape = (1, 2)


class _FakeBatch(dict):
    def __init__(self):
        super().__init__(input_ids=_FakeTensor(), attention_mask=_FakeTensor())
        self.device = None

    def to(self, device):
        self.device = device
        return self


class _FakeGenerated:
    def __init__(self, token_ids):
        self.token_ids = token_ids

    def __getitem__(self, item):
        return _FakeGenerated(self.token_ids[item])

    def tolist(self):
        return list(self.token_ids)


class _FakeModel:
    def __init__(self):
        self.config = SimpleNamespace(
            _name_or_path="runtime/model", _commit_hash="a" * 40
        )
        self.generation_kwargs: dict[str, Any] = {}

    def generate(self, **kwargs):
        self.generation_kwargs = kwargs
        return [_FakeGenerated([101, 102, 10, 200002, 77])]


class _FakeBackendTokenizer:
    @staticmethod
    def to_str():
        return "{}"


class _FakeTokenizer:
    def __init__(self):
        self.padding_side = "right"
        self.pad_token_id = 200017
        self.eos_token_id = 200002
        self.chat_template = "fake-template"
        self.special_tokens_map = {"eos_token": "<|return|>"}
        self.backend_tokenizer = _FakeBackendTokenizer()
        self.template_kwargs = None
        self.decoded_token_ids = []
        self.raw_generation = (
            "<|channel|>analysis<|message|>reason"
            '<|channel|>final<|message|>{"assessment":"not_observed"}'
            "<|return|>"
        )

    def apply_chat_template(self, _messages, **kwargs):
        self.template_kwargs = kwargs
        return _FakeBatch()

    def decode(self, token_ids, *, skip_special_tokens):
        self.decoded_token_ids.append(token_ids)
        if skip_special_tokens:
            return '{"assessment":"not_observed"}'
        return self.raw_generation
