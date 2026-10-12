from pathlib import Path

from testquality.config import load_config, load_settings


def test_config_has_required_sections():
    cfg = load_config()
    for key in ("ha", "llm", "execution", "mutation", "review", "paths"):
        assert key in cfg


def test_config_models_and_k():
    llm = load_config()["llm"]
    assert llm["main_model"] == "claude-sonnet-5-5"
    assert llm["cheap_model"] == "claude-haiku-5-5"
    assert llm["samples_per_prompt"] == 5


def test_config_never_sets_sampling_params():
    llm = load_config()["llm"]
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in llm


def test_settings_read_env_file(tmp_path: Path, monkeypatch):
    for var in ("HA_CORE_DIR", "HA_PYTHON"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".env").write_text("HA_CORE_DIR=/x/ha\nHA_PYTHON=/x/ha/.venv/bin/python\n")
    (tmp_path / "config.yaml").write_text((Path(__file__).parents[1] / "config.yaml").read_text())
    s = load_settings(tmp_path)
    assert s.ha_core_dir == Path("/x/ha")
    assert s.ha_python == Path("/x/ha/.venv/bin/python")
    assert s.developer_tests_dir == Path("/x/ha/tests/components/threshold")


def test_gitignore_keeps_env_ignored():
    text = (Path(__file__).parents[1] / ".gitignore").read_text().splitlines()
    assert ".env" in text
