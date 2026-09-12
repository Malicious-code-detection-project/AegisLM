from pathlib import Path

from aegislm.environment import load_project_env


def test_project_env_loads_keys_without_overriding_shell(tmp_path, monkeypatch):
    Path(tmp_path, ".env").write_text(
        "WANDB_API_KEY=file-value\nHF_TOKEN=file-hf\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WANDB_API_KEY", "shell-value")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HF_HUB_DISABLE_IMPLICIT_TOKEN", "0")

    assert load_project_env(tmp_path)
    assert __import__("os").environ["WANDB_API_KEY"] == "shell-value"
    assert __import__("os").environ["HF_TOKEN"] == "file-hf"
    assert __import__("os").environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1"


def test_env_example_contains_only_supported_external_credentials():
    keys = {
        line.split("=", 1)[0]
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line
    }

    assert keys == {"WANDB_API_KEY", "HF_TOKEN", "AEGISLM_INFERENCE_API_KEY"}
