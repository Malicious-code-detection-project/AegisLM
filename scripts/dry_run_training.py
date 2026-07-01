import sys
import os
import argparse
import json

# Ensure aegislm package can be imported from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegislm.training.config import load_config, validate_paths
from aegislm.datasets import format_sft_record


def run_dry_run(config_path: str, check_model: bool = False):
    print("=" * 60)
    print(f"Starting Training Config Dry-run for: {config_path}")
    print("=" * 60)

    # 1. Config Parsing
    try:
        config = load_config(config_path)
        print("[SUCCESS] 1. Config parsed and schema verified.")
    except Exception as e:
        print(f"[FAIL] 1. Config parsing failed: {e}")
        sys.exit(1)

    # 2. Path Validation
    # In a real run we validate everything. However, if data files don't exist yet,
    # we explain and allow verifying folder permissions only.
    train_path = config["dataset"]["train_path"]
    val_path = config["dataset"]["val_path"]

    has_dataset = os.path.exists(train_path) and os.path.exists(val_path)

    try:
        # If files don't exist, we will report it but still test if paths are writable
        validate_paths(config, ignore_dataset_missing=not has_dataset)
        print("[SUCCESS] 2. Directory writability/creation verified.")
        if has_dataset:
            print("         Dataset files are present and verified.")
        else:
            print(
                "         [WARNING] Dataset files do not exist yet. Path check passed, but actual SFT training will require these files."
            )
    except Exception as e:
        print(f"[FAIL] 2. Path validation failed: {e}")
        sys.exit(1)

    # 3. Dataset Format & Dry-run verification (Integration with [THE-68] Placeholder)
    if has_dataset:
        print("[INFO] 3. Verifying dataset sample format...")
        try:
            samples_checked = 0
            with open(train_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    formatted = format_sft_record(record)

                    if "messages" not in formatted:
                        raise KeyError(
                            "Formatted output must contain 'messages' field for SFT training."
                        )

                    if samples_checked == 0:
                        print("--- Sample SFT Messages Output ---")
                        print(
                            json.dumps(formatted, indent=2, ensure_ascii=False)[:500]
                            + "\n... (truncated)"
                        )
                        print("---------------------------------")

                    samples_checked += 1
                    if samples_checked >= 3:
                        break
            print(
                f"[SUCCESS] 3. Dataset format dry-run completed ({samples_checked} samples verified)."
            )
        except Exception as e:
            print(f"[FAIL] 3. Dataset sample format dry-run failed: {e}")
            sys.exit(1)
    else:
        print(
            "[INFO] 3. Skipping dataset format validation (Dataset files not created yet)."
        )

    # 4. Model/Tokenizer Load Verification (Optional)
    if check_model:
        model_id = config["model"]["base_model_id"]
        cache_dir = config["model"]["cache_dir"]
        print(f"[INFO] 4. Fetching/verifying tokenizer for: {model_id}...")
        try:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
            print(
                f"[SUCCESS] 4. Tokenizer successfully loaded. Vocabulary size: {len(tokenizer)}"
            )
        except ImportError:
            print(
                "[FAIL] 4. 'transformers' package not installed. Cannot verify model/tokenizer."
            )
            sys.exit(1)
        except Exception as e:
            print(f"[FAIL] 4. Failed to load tokenizer: {e}")
            sys.exit(1)
    else:
        print(
            "[INFO] 4. Model/Tokenizer load check skipped (use --check-model to enable)."
        )

    print("=" * 60)
    print("Dry-run completed successfully! Configuration is valid.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run validator for SFT training config."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/tiny_sft_config.json",
        help="Path to the config file",
    )
    parser.add_argument(
        "--check-model",
        action="store_true",
        help="Verify downloading/loading the base model tokenizer",
    )
    args = parser.parse_args()

    run_dry_run(args.config, check_model=args.check_model)


if __name__ == "__main__":
    main()
