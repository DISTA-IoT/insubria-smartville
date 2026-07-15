#!/usr/bin/env python3
"""Inference-model ("oracle") ablation configs, in queue-able form.

This is the todo-queue counterpart of tests/ablating_inference_models.py.
Where seeded_agents.py sweeps the *decision* agent (DQN-family x epistemic-
action modes), this sweep ablates the *inference* stack -- the neural
Anomaly Detection (AD), Classification (CS) and Knowledge Retrieval (KR)
modules -- by toggling intrusion_detection.use_neural_{AD,CS,KR}. Disabling a
module makes the controller fall back to that module's ground-truth ("oracle")
signal, so "perfect" (all three disabled) is the perfect-information upper
bound and each other mode isolates the contribution of one module.

The seven modes below reproduce, one-to-one, the configurations that
ablating_inference_models.py runs imperatively -- same wandb.wb_run_name and
same "oracle" W&B group -- so runs queued through here land in the same W&B
groups as the originals. The point of expressing them as data (rather than a
flat script) is that they can now be listed row-by-row in
tests/todo_queue.yaml and executed by tests/run_todo_queue.py, gaining its
crash-resilient "resume by trimming the file" behaviour, per-run seed
verification and mid-run health polling.

See tests/todo_queue.yaml for the queue-row schema and examples.
"""

from __future__ import annotations

from typing import Any

# Default W&B group for the oracle/inference sweep. Matches the hardcoded
# wandb.wb_group_name that ablating_inference_models.py uses for every one of
# these runs. A queue row may still override it with its own
# `wandb_group_name` key.
ORACLE_GROUP_NAME = "oracle"

# dash_cli.py config keys for the three neural inference modules (default True
# in config/default.yaml). Setting one to "false" swaps that module out for its
# oracle signal.
_USE_NEURAL_AD = "intrusion_detection.use_neural_AD"
_USE_NEURAL_CS = "intrusion_detection.use_neural_CS"
_USE_NEURAL_KR = "intrusion_detection.use_neural_KR"

# inference-mode key -> (wandb.wb_run_name, {config key: "false"} overrides).
#
# Any use_neural_* key NOT present in a mode's override dict keeps the profile
# default (that neural module stays enabled); a key mapped to "false" disables
# that module, falling back to its oracle signal. The run names are copied
# verbatim from ablating_inference_models.py so queued runs share W&B identity
# with the originals.
INFERENCE_MODES: dict[str, tuple[str, dict[str, str]]] = {
    # perfect information: all three neural modules replaced by oracle signals.
    "perfect": ("perfect_inference", {_USE_NEURAL_AD: "false", _USE_NEURAL_CS: "false", _USE_NEURAL_KR: "false"}),
    # exactly one neural module active, the other two oracled.
    "only_AD": ("only_neural_AD", {_USE_NEURAL_CS: "false", _USE_NEURAL_KR: "false"}),
    "only_CS": ("only_neural_CS", {_USE_NEURAL_AD: "false", _USE_NEURAL_KR: "false"}),
    "only_KR": ("only_neural_KR", {_USE_NEURAL_AD: "false", _USE_NEURAL_CS: "false"}),
    # exactly one neural module oracled, the other two active.
    "not_AD": ("not_neural_AD", {_USE_NEURAL_AD: "false"}),
    "not_CS": ("not_neural_CS", {_USE_NEURAL_CS: "false"}),
    "not_KR": ("not_neural_KR", {_USE_NEURAL_KR: "false"}),
}


def _require_mode(inference_mode: str) -> tuple[str, dict[str, str]]:
    try:
        return INFERENCE_MODES[inference_mode]
    except KeyError:
        raise ValueError(
            f"Unknown inference mode: {inference_mode!r}. "
            f"Valid modes: {sorted(INFERENCE_MODES)}"
        ) from None


def inference_run_name(inference_mode: str) -> str:
    """wandb.wb_run_name for the given inference mode (e.g. 'perfect_inference')."""
    return _require_mode(inference_mode)[0]


def inference_overrides(inference_mode: str) -> dict[str, Any]:
    """The {config key: 'false'} use_neural_* overrides for the given mode.

    Returns a fresh dict each call so callers can mutate it freely.
    """
    return dict(_require_mode(inference_mode)[1])
