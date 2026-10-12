import re

import pytest

from testquality.prompts import PARAPHRASES, USER_V1, VERSIONS, build_prompt
from tests.test_generate import fake_settings

REQUIRED = [
    r"\{module\}", r"\{component\}", r"\{sources\}", r"Behaviour:", r"Target:",
    r"`hass`", r"MockConfigEntry", r"async_setup_component", r"HomeAssistant", r"patch",
    r"syrupy", r"network", r"sleep", r"boundary", r"error", r"options", r"```python",
    r"one sentence", r"importable",
]


@pytest.mark.parametrize("name", sorted(PARAPHRASES))
def test_paraphrase_keeps_every_requirement(name):
    for pattern in REQUIRED:
        assert re.search(pattern, PARAPHRASES[name], re.IGNORECASE), (name, pattern)
        assert re.search(pattern, USER_V1, re.IGNORECASE), pattern  # same list holds for v1


@pytest.mark.parametrize("name", sorted(PARAPHRASES))
def test_paraphrase_is_actually_different(name):
    assert PARAPHRASES[name] != USER_V1
    assert len(set(PARAPHRASES.values())) == len(PARAPHRASES)


def test_paraphrases_differ_only_in_prose_not_in_placeholder_set():
    for text in PARAPHRASES.values():
        assert set(re.findall(r"\{(\w+)\}", text)) == {"module", "component", "sources"}


@pytest.mark.parametrize("version", VERSIONS)
def test_every_version_builds_without_leaking(tmp_path, version):
    s = fake_settings(tmp_path)
    comp = s.ha_core_dir / s.config["ha"]["component_dir"]
    p = build_prompt(component="threshold", module="binary_sensor.py", target="binary_sensor",
                     component_dir=comp, version=version)
    assert "X = 1" in p.user or version in ("mr2", "mr3", "mr4")
    assert "test_secret_developer_case" not in p.text
    assert p.version == version


def test_source_transforms_change_the_shown_source(tmp_path):
    s = fake_settings(tmp_path)
    comp = s.ha_core_dir / s.config["ha"]["component_dir"]
    (comp / "binary_sensor.py").write_text(
        "def f(a):\n    # note\n    result = a\n    return result\n\n\ndef g():\n    return 1\n"
    )
    shown = {
        v: build_prompt(component="threshold", module="binary_sensor.py", target="t",
                        component_dir=comp, version=v).user
        for v in ("v1", "mr2", "mr3", "mr4")
    }
    assert "loc_result" in shown["mr2"] and "loc_result" not in shown["v1"]
    assert "# note" in shown["v1"] and "# note" not in shown["mr4"]
    assert shown["mr3"].index("def g") < shown["mr3"].index("def f")
