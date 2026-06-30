import json
import os
from typing import Any, Dict
from jsonschema import validate, ValidationError

# Define the config JSON schema to ensure strict type and field compliance
CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {
            "type": "object",
            "properties": {
                "base_model_id": {"type": "string"},
                "cache_dir": {"type": "string"}
            },
            "required": ["base_model_id", "cache_dir"]
        },
        "dataset": {
            "type": "object",
            "properties": {
                "train_path": {"type": "string"},
                "val_path": {"type": "string"}
            },
            "required": ["train_path", "val_path"]
        },
        "training": {
            "type": "object",
            "properties": {
                "adapter_method": {"type": "string"},
                "output_dir": {"type": "string"},
                "checkpoint_dir": {"type": "string"},
                "learning_rate": {"type": "number"},
                "batch_size": {"type": "integer"},
                "gradient_accumulation_steps": {"type": "integer"},
                "epochs": {"type": "integer"},
                "max_seq_length": {"type": "integer"},
                "lora_r": {"type": "integer"},
                "lora_alpha": {"type": "integer"},
                "lora_dropout": {"type": "number"}
            },
            "required": [
                "adapter_method", "output_dir", "checkpoint_dir",
                "learning_rate", "batch_size", "gradient_accumulation_steps",
                "epochs", "max_seq_length", "lora_r", "lora_alpha", "lora_dropout"
            ]
        }
    },
    "required": ["model", "dataset", "training"]
}

def load_config(config_path: str) -> Dict[str, Any]:
    """Reads a JSON configuration file and validates it against the schema."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at: {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in config file: {e}")
            
    # Schema validation using jsonschema
    try:
        validate(instance=config, schema=CONFIG_SCHEMA)
    except ValidationError as e:
        raise ValueError(f"Config schema validation failed: {e.message}")
        
    return config

def is_git_safe_path(path: str) -> bool:
    """
    Checks if the path is Git-safe (either outside the git repository or in an ignored directory).
    Allowed ignored directories are defined based on the project's .gitignore policy.
    """
    abs_path = os.path.abspath(path)
    # The workspace root is the parent of 'aegislm' package
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # If the path is outside the git repository, it's naturally Git-safe
    if not abs_path.startswith(workspace_root):
        return True
        
    # Get relative path from workspace root
    rel_path = os.path.relpath(abs_path, workspace_root)
    top_dir = rel_path.split(os.sep)[0]
    
    # Allowed directories from .gitignore
    allowed_ignored_dirs = {
        "data", "raw_datasets", "artifacts", "checkpoints", 
        "adapters", "models", "outputs", "runs", "experiments"
    }
    
    return top_dir in allowed_ignored_dirs

def validate_paths(config: Dict[str, Any], ignore_dataset_missing: bool = False) -> None:
    """Checks that all paths specified in the config are valid, writable, and comply with Git-safe policies."""
    # 1. Dataset Paths Validation
    if not ignore_dataset_missing:
        for path_key in ["train_path", "val_path"]:
            path = config["dataset"][path_key]
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"Dataset file defined in config ({path_key}) does not exist at: {path}"
                )
            if not os.path.isfile(path):
                raise ValueError(
                    f"Dataset path defined in config ({path_key}) is not a file: {path}"
                )
            
    # 2. Output, Checkpoint, and Cache Path compliance with Git policies
    for path_key, path in [
        ("output_dir", config["training"]["output_dir"]),
        ("checkpoint_dir", config["training"]["checkpoint_dir"]),
        ("cache_dir", config["model"]["cache_dir"])
    ]:
        # Enforce Git exclusion policy
        if not is_git_safe_path(path):
            raise ValueError(
                f"Path violation: '{path_key}' ({path}) must be Git-ignored (e.g. inside data/, adapters/, checkpoints/, models/, etc.) or outside the workspace to prevent accidental commits."
            )
            
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            raise PermissionError(f"Failed to create directory '{path}' for '{path_key}': {e}")
            
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Directory '{path}' for '{path_key}' is not writable.")
