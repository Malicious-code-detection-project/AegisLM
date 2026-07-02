import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "aegislm",
        "aegislm.datasets",
        "aegislm.evaluation",
        "aegislm.evaluation.harness",
        "aegislm.evaluation.validation",
        "aegislm.inference",
        "aegislm.inference.baseline",
        "aegislm.inference.adapter",
        "aegislm.prompts",
        "aegislm.schemas",
        "aegislm.training",
    ],
)
def test_scaffold_packages_are_importable(module_name: str) -> None:
    assert importlib.import_module(module_name).__name__ == module_name
