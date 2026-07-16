#!/usr/bin/env python3
"""Budget-constraint experiment configs, in queue-able form.

The GNS3/live counterpart of the offline smartville-controller sweep
offline_budget_constraints.py, and the queue-able form of the (mostly
commented-out) sweep hand-written in tests/budget_constraints.py. Where
seeded_agents.py sweeps the decision agent and inference_ablations.py the
inference stack, this sweep varies the DM's *budget thresholds* --
intrusion_detection.min_budget (the bankruptcy floor) and .max_budget (the
termination ceiling), see tiger_environment_new.py -- to probe how the budget
envelope shapes the learned buy policy.

Each named config maps to a wandb.wb_run_name and the min/max_budget
override(s) it sets; a config leaves whichever threshold it does not name at
the profile default (exactly as tests/budget_constraints.py only ever `set`s
the one threshold it is varying). Values are strings because they are handed
straight to `dash_cli.py set <key> <value>`, which parses them with YAML
semantics (so "-20" -> int, "35" -> int); negative values pass through argparse
as positional values fine (tests/budget_constraints.py already relies on this).

The config names / thresholds mirror offline_budget_constraints.py so the live
and offline budget sweeps share W&B identity. These default to W&B group
"budget_constraints" (the group tests/budget_constraints.py uses); a queue row
may override it with its own `wandb_group_name` key.

See tests/todo_queue.yaml for the queue-row schema and examples.
"""

from __future__ import annotations

from typing import Any

# Default W&B group for the budget-constraint sweep. Matches the
# wandb.wb_group_name tests/budget_constraints.py sets on every one of these
# runs. A queue row may still override it with its own `wandb_group_name`.
BUDGET_GROUP_NAME = "budget_constraints"

_MIN_BUDGET = "intrusion_detection.min_budget"
_MAX_BUDGET = "intrusion_detection.max_budget"

# budget-config name -> (wandb.wb_run_name, {config key: value} overrides).
#
# A key absent from a config's override dict keeps the profile default for that
# threshold ("default" sets neither -- a pure profile-budget baseline). Run
# names are copied verbatim from offline_budget_constraints.py / the run names
# in tests/budget_constraints.py so live and offline budget runs share W&B
# identity.
BUDGET_CONFIGS: dict[str, tuple[str, dict[str, str]]] = {
    # pure profile budgets, overrides nothing -- baseline column.
    "default": ("default", {}),
    "l-minus20": ("l-minus20", {_MIN_BUDGET: "-20"}),
    "l-minus5": ("l-minus5", {_MIN_BUDGET: "-5"}),
    "h-35": ("h-35", {_MAX_BUDGET: "35"}),
    "l-minus5_h-35": ("l-minus5_h-35", {_MIN_BUDGET: "-5", _MAX_BUDGET: "35"}),
    "l-minus5_h-40": ("l-minus5_h-40", {_MIN_BUDGET: "-5", _MAX_BUDGET: "40"}),
    "l-minus1": ("l-minus1", {_MIN_BUDGET: "-1"}),
}


def _require_config(config_name: str) -> tuple[str, dict[str, str]]:
    try:
        return BUDGET_CONFIGS[config_name]
    except KeyError:
        raise ValueError(
            f"Unknown budget config: {config_name!r}. "
            f"Valid configs: {sorted(BUDGET_CONFIGS)}"
        ) from None


def budget_run_name(config_name: str) -> str:
    """wandb.wb_run_name for the given budget config (e.g. 'l-minus5_h-35')."""
    return _require_config(config_name)[0]


def budget_overrides(config_name: str) -> dict[str, Any]:
    """The {config key: value} min/max_budget overrides for the given config.

    Returns a fresh dict each call so callers can mutate it freely.
    """
    return dict(_require_config(config_name)[1])
