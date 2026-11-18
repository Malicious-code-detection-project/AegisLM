from scripts.download_hf_model import _matches_patterns


def test_matches_patterns_defaults():
    assert _matches_patterns("config.json", None, default=True) is True
    assert _matches_patterns("config.json", None, default=False) is False


def test_matches_patterns_with_globs():
    assert _matches_patterns("config.json", ["*.json"], default=False) is True
    assert _matches_patterns("model.safetensors", ["*.json"], default=False) is False
