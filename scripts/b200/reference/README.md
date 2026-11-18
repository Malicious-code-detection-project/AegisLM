# Preserved source for the B200 reproduction

These files are source dependencies of the 2026-10-04 official-tutorial
100-step experiment. They are preserved byte-for-byte; the B200 launcher copies
them into a new ignored output directory and does not execute the historical
two-case generation workflow.

- `training/original.py`: Unsloth GPT-OSS-20B tutorial Python source, notebooks
  commit `92e38e86308748d18fc4cd4b104c4c6d3db1d67e`, SHA-256
  `74ff47bb9212f482f7378d86f27bc088973e924ae427cc84891d87663131895a`.
  Original attribution and LGPL-3.0 notice remain in the file; `LICENSE` and
  `COPYING` contain the LGPLv3 and GPLv3 texts.
- `training/{prepare,train,common,score}.py`: AegisLM preparation, original-AST
  execution, result persistence and Harmony scoring used in that experiment.
- `cc-official-tutorial-v5-token-caps-20261004-v1/adapted-training.py`: historical
  30-step AST comparison reference. The driver normalizes its old dataset path
  before comparison; it never loads the old absolute path.
- `unsloth-official-tutorial-generation-64-20261004-v1/run.py`: historical observer.
  The driver imports only its read-only parameter hashing and AST lookup helpers;
  its `main()` is not run.

Ruff excludes this reference directory to retain the exact source. Maintained
launchers in `scripts/b200/` remain linted. Dataset rows, gold, generated audit
records and package observations stay in the separate Git-ignored data export.
See [the recipe](../../../docs/B200_REPRODUCTION_RECIPE.md).
