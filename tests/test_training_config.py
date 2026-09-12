import os
import json
import pytest
from aegislm.training import config as training_config
from aegislm import paths as path_policy
from aegislm.training.config import load_config, validate_paths

# A valid mock config structure for testing
VALID_CONFIG_DATA = {
    "model": {"base_model_id": "test/model-id", "cache_dir": "test_cache"},
    "dataset": {"train_path": "test_train.jsonl", "val_path": "test_val.jsonl"},
    "training": {
        "adapter_method": "lora",
        "output_dir": "test_output",
        "checkpoint_dir": "test_checkpoint",
        "learning_rate": 2e-4,
        "batch_size": 2,
        "gradient_accumulation_steps": 4,
        "epochs": 1,
        "max_seq_length": 512,
        "lora_r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
    },
}


def test_load_config_valid(tmp_path):
    """Test that a valid config is loaded and verified successfully."""
    config_file = tmp_path / "valid_config.json"
    config_file.write_text(json.dumps(VALID_CONFIG_DATA), encoding="utf-8")

    config = load_config(str(config_file))
    assert config["model"]["base_model_id"] == "test/model-id"
    assert config["training"]["learning_rate"] == 0.0002


def test_load_config_invalid_schema(tmp_path):
    """Test that an invalid schema raises a ValueError."""
    invalid_config = VALID_CONFIG_DATA.copy()
    del invalid_config["model"]

    config_file = tmp_path / "invalid_schema.json"
    config_file.write_text(json.dumps(invalid_config), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_config(str(config_file))
    assert "Config schema validation failed" in str(excinfo.value)


def test_load_config_invalid_json(tmp_path):
    """Test that non-JSON content raises a ValueError."""
    config_file = tmp_path / "invalid_json.json"
    config_file.write_text("invalid json contents", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_config(str(config_file))
    assert "Invalid JSON format" in str(excinfo.value)


@pytest.mark.parametrize("numeric", ["NaN", "Infinity", "1e999"])
def test_load_config_rejects_nonfinite_numbers(tmp_path, numeric):
    config_file = tmp_path / "nonfinite.json"
    payload = json.dumps(VALID_CONFIG_DATA).replace("0.0002", numeric)
    config_file.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite|non-standard"):
        load_config(str(config_file))


def test_validate_paths_missing_dataset():
    """Test that validation fails if dataset files do not exist."""
    config = VALID_CONFIG_DATA.copy()
    config["dataset"] = {
        "train_path": "non_existent_file_12345.jsonl",
        "val_path": "non_existent_file_67890.jsonl",
    }

    with pytest.raises(FileNotFoundError) as excinfo:
        validate_paths(config, ignore_dataset_missing=False)
    assert "Dataset file defined in config" in str(excinfo.value)


def test_validate_paths_success_with_temp_files(tmp_path):
    """Test that path validation succeeds when files and directories are valid."""
    train_file = tmp_path / "train.jsonl"
    val_file = tmp_path / "val.jsonl"

    # Touch files
    train_file.touch()
    val_file.touch()

    config = {
        "model": {
            "base_model_id": "test/model-id",
            "cache_dir": str(tmp_path / "cache"),
        },
        "dataset": {"train_path": str(train_file), "val_path": str(val_file)},
        "training": {
            "adapter_method": "lora",
            "output_dir": str(tmp_path / "output"),
            "checkpoint_dir": str(tmp_path / "checkpoint"),
        },
    }

    validate_paths(config)

    assert os.path.exists(config["model"]["cache_dir"])
    assert os.path.exists(config["training"]["output_dir"])
    assert os.path.exists(config["training"]["checkpoint_dir"])


def test_validate_paths_git_policy_violation():
    """Test that path validation fails if output paths are NOT git-ignored."""
    config = VALID_CONFIG_DATA.copy()
    config["training"] = {
        "adapter_method": "lora",
        "output_dir": "aegislm/my_temp_adapter",  # 'aegislm' directory is not git-ignored
        "checkpoint_dir": "test_checkpoint",
    }
    config["model"] = {"base_model_id": "test/model-id", "cache_dir": "test_cache"}

    with pytest.raises(ValueError) as excinfo:
        validate_paths(config, ignore_dataset_missing=True)
    assert "Path violation" in str(excinfo.value)


def test_git_safe_path_resolves_ignored_directory_symlinks(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    module_path = repository / "aegislm" / "training" / "config.py"
    module_path.parent.mkdir(parents=True)
    module_path.touch()
    docs = repository / "docs"
    docs.mkdir()
    outputs = repository / "outputs"
    outputs.mkdir()
    (outputs / "escape").symlink_to(docs, target_is_directory=True)
    policy_path = repository / "aegislm" / "paths.py"
    monkeypatch.setattr(path_policy, "__file__", str(policy_path))

    assert not training_config.is_git_safe_path(str(outputs / "escape" / "raw"))
