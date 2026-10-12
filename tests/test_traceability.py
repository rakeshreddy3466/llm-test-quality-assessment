from testquality.traceability import (
    TraceInfo,
    declared_target,
    name_target,
    score,
    tokens,
)

CANDS = [
    "binary_sensor:ThresholdSensor",
    "binary_sensor:ThresholdSensor._update_state",
    "binary_sensor:ThresholdSensor.is_on",
    "binary_sensor:async_setup_entry",
    "__init__:async_migrate_entry",
    "config_flow:ConfigFlowHandler",
]


def test_tokens():
    assert tokens("test_sensor_upper[vals0-below]") == {"sensor", "upper"}
    assert tokens("ThresholdSensor._update_state") == {"threshold", "sensor", "update", "state"}


def test_name_target_picks_best_overlap():
    assert name_target("test_update_state_hysteresis", CANDS) == (
        "binary_sensor:ThresholdSensor._update_state"
    )
    assert name_target("test_migrate_entry", CANDS) == "__init__:async_migrate_entry"
    assert name_target("test_zzz_unrelated", CANDS) is None


def test_declared_target_resolution():
    doc = "Behaviour: x.\n\nTarget: ThresholdSensor._update_state"
    assert declared_target(doc, CANDS) == "binary_sensor:ThresholdSensor._update_state"
    assert declared_target("Target: async_setup_entry", CANDS) == "binary_sensor:async_setup_entry"
    assert declared_target("Target: `async_migrate_entry()`", CANDS) == "__init__:async_migrate_entry"
    assert declared_target("Target: nothing_here", CANDS) is None
    assert declared_target("no tag", CANDS) is None
    assert declared_target(None, CANDS) is None


def test_score_levels():
    info = TraceInfo(True, ["binary_sensor:async_setup_entry",
                            "binary_sensor:ThresholdSensor._update_state"],
                     "binary_sensor:ThresholdSensor._update_state")
    assert score("binary_sensor:ThresholdSensor._update_state", info) == 1.0
    assert score("binary_sensor:async_setup_entry", info) == 0.5      # called before assert
    assert score("binary_sensor:ThresholdSensor", info) == 0.5        # class of target
    assert score("config_flow:ConfigFlowHandler", info) == 0.0
    assert score(None, info) == 0.0
    assert score("binary_sensor:ThresholdSensor", TraceInfo(False, [], None)) == 0.0
