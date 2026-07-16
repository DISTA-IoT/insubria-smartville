#!/usr/bin/env python3
"""CTI-delivery-fidelity experiment configs, in queue-able form.

The GNS3/live counterpart of the offline smartville-controller sweep
offline_cti_fidelity.py. Where seeded_agents.py sweeps the decision agent and
inference_ablations.py the inference stack, this sweep degrades *CTI delivery*:
purchased intelligence may arrive with noisy labels and/or after a jittered
delay, instead of the idealised clean/instant/complete delivery the base game
assumes. See smartController/cti_delivery.py (CTIDeliveryModel, reviewer
comment RC 3.4). The relevant intrusion_detection knobs are:

  - cti_label_noise       [0,1]  fraction of an acquired class's training-label
                                 draws relabelled to a wrong class.
  - cti_label_noise_mode  str    'symmetric' (flip to a uniformly-random other
                                 Known class) or 'nearest'. Only used when
                                 cti_label_noise > 0.
  - cti_quality_coupling  str    'none' | 'purity' | 'confidence'. When set, the
                                 label-noise severity scales with (1 - cluster
                                 quality) at buy time.
  - cti_delivery_delay    steps  decision steps between paying and the class
                                 becoming trainable (G2 -> Known).
  - cti_delivery_jitter   steps  +/- uniform random jitter on the delay.

Each named config maps to a wandb.wb_run_name and the CTI knob override(s) it
sets; any knob it does not name keeps the profile default ("clean" sets none --
a strict idealised-delivery baseline). Values are strings because they are
handed straight to `dash_cli.py set <key> <value>`, which parses them with YAML
semantics ("0.5" -> float, "50" -> int, "none"/"symmetric" -> str).

The five configs below mirror offline_cti_fidelity.py one-to-one so the live
and offline CTI-fidelity sweeps share W&B identity. Both label-noise configs
pin cti_label_noise_mode='symmetric' explicitly (the default.yaml default is
'nearest'). These default to W&B group "cti-fidelity"; a queue row may override
it with its own `wandb_group_name` key.

See tests/todo_queue.yaml for the queue-row schema and examples.
"""

from __future__ import annotations

from typing import Any

# Default W&B group for the CTI-delivery-fidelity sweep. A queue row may still
# override it with its own `wandb_group_name`.
CTI_GROUP_NAME = "cti-fidelity"

_LABEL_NOISE = "intrusion_detection.cti_label_noise"
_NOISE_MODE = "intrusion_detection.cti_label_noise_mode"
_COUPLING = "intrusion_detection.cti_quality_coupling"
_DELAY = "intrusion_detection.cti_delivery_delay"
_JITTER = "intrusion_detection.cti_delivery_jitter"

# cti-config name -> (wandb.wb_run_name, {config key: value} overrides).
#
# A key absent from a config's override dict keeps the profile default for that
# knob ("clean" sets none -- idealised clean/instant/complete delivery). Run
# names are copied verbatim from offline_cti_fidelity.py so live and offline
# CTI runs share W&B identity.
CTI_CONFIGS: dict[str, tuple[str, dict[str, str]]] = {
    # idealised clean/instant/complete delivery (strict no-op baseline).
    "clean": ("clean", {}),
    # a) label noise 0.5, uncoupled, symmetric flips.
    "noise0.5-none": ("noise0.5-none", {
        _LABEL_NOISE: "0.5", _COUPLING: "none", _NOISE_MODE: "symmetric"}),
    # b) label noise 1.0, purity-coupled, symmetric flips.
    "noise1-purity": ("noise1-purity", {
        _LABEL_NOISE: "1.0", _COUPLING: "purity", _NOISE_MODE: "symmetric"}),
    # c) delivery delay 50 steps, +/-15 jitter (clean labels).
    "delay50-jit15": ("delay50-jit15", {_DELAY: "50", _JITTER: "15"}),
    # d) delivery delay 70 steps, +/-30 jitter (clean labels).
    "delay70-jit30": ("delay70-jit30", {_DELAY: "70", _JITTER: "30"}),
    # e) combo of b) and d): noisy purity-coupled labels AND delayed delivery.
    "noise1-purity-delay70-jit30": ("noise1-purity-delay70-jit30", {
        _LABEL_NOISE: "1.0", _COUPLING: "purity", _NOISE_MODE: "symmetric",
        _DELAY: "70", _JITTER: "30"}),
}


def _require_config(config_name: str) -> tuple[str, dict[str, str]]:
    try:
        return CTI_CONFIGS[config_name]
    except KeyError:
        raise ValueError(
            f"Unknown CTI-fidelity config: {config_name!r}. "
            f"Valid configs: {sorted(CTI_CONFIGS)}"
        ) from None


def cti_run_name(config_name: str) -> str:
    """wandb.wb_run_name for the given CTI-fidelity config (e.g. 'noise1-purity')."""
    return _require_config(config_name)[0]


def cti_overrides(config_name: str) -> dict[str, Any]:
    """The {config key: value} CTI-delivery overrides for the given config.

    Returns a fresh dict each call so callers can mutate it freely.
    """
    return dict(_require_config(config_name)[1])
