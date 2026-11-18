"""Run the preserved training scripts with the original rendered prompt date."""

import argparse
import functools
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "outputs/b200-step100-v1"


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "train"))
    args = parser.parse_args()
    if args.action == "train":
        if (TRAIN / "training-runtime.json").exists():
            raise RuntimeError("Preserve this training attempt; do not rerun it")
        # Unsloth must patch before Transformers imports.
        import unsloth  # noqa: F401
    from transformers import PreTrainedTokenizerBase

    original = PreTrainedTokenizerBase.apply_chat_template

    @functools.wraps(original)
    def fixed_date(self, *values, **kwargs):
        kwargs.setdefault("strftime_now", lambda _: "2026-10-04")
        return original(self, *values, **kwargs)

    # Preserve the original tutorial AST and masking. Only its dynamic date is frozen.
    PreTrainedTokenizerBase.apply_chat_template = fixed_date
    os.chdir(TRAIN)
    sys.path.insert(0, str(TRAIN))
    runpy.run_path(str(TRAIN / f"{args.action}.py"), run_name="__main__")


if __name__ == "__main__":
    main()
