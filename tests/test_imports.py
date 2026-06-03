import importlib
import unittest


class ImportSmokeTest(unittest.TestCase):
    def test_scaffold_packages_are_importable(self) -> None:
        module_names = [
            "aegislm",
            "aegislm.datasets",
            "aegislm.evaluation",
            "aegislm.inference",
            "aegislm.prompts",
            "aegislm.training",
        ]

        for module_name in module_names:
            with self.subTest(module_name=module_name):
                self.assertEqual(importlib.import_module(module_name).__name__, module_name)


if __name__ == "__main__":
    unittest.main()
