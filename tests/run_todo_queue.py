#!/usr/bin/env python3
"""Crash-resilient queue runner for dash_cli.py experiments.

Reads a flat YAML "todo list" of experiments (default: tests/todo_queue.yaml,
see that file for schema) and runs them one at a time, top to bottom, reusing
the exact same per-run logic as seeded_agents.py (config reload, agent/seed/
ablation overrides, applied-config verification, traffic start, health-polled
wait, experiment/traffic stop).

Four kinds of queue row are supported, told apart by their keys:

  * DQN-family epistemic-action ablation rows (agent + mode + seed [+ cti_period
    / cti_confidence_threshold]) -- the original rows, run via seeded_agents.py's
    run_one / ablation_overrides.
  * Inference-model "oracle" ablation rows (inference + seed [+ agent]) -- the
    queue-able form of tests/ablating_inference_models.py, run via
    tests/inference_ablations.py's mode table and seeded_agents.py's shared
    run_experiment primitive. These default to W&B group "oracle".
  * Budget-constraint rows (budget + seed [+ agent]) -- the queue-able / live
    form of tests/budget_constraints.py and the offline smartville-controller
    sweep offline_budget_constraints.py, run via tests/budget_experiments.py's
    config table. These default to W&B group "budget_constraints".
  * CTI-delivery-fidelity rows (cti + seed [+ agent]) -- the live counterpart of
    the offline smartville-controller sweep offline_cti_fidelity.py, run via
    tests/cti_fidelity_experiments.py's config table. These default to W&B group
    "cti-fidelity".

All four kinds may be freely interleaved in one queue file, and any kind may
carry a per-row `wandb_group_name` to override the default group for that run.
The budget and CTI rows take an optional `agent` (defaults to the profile's
agent, exactly as the inference rows do); their overrides only bite when the
Decision Module is actually buying CTI, so run them against an agency-enabled
profile.

This exists because the platform this runs on sometimes crashes silently
between runs (e.g. the whole machine/container becomes unreachable, not just
the controller's inference loop -- that case is already caught by
wait_with_health_checks). When that happens this script's own process dies or
hangs along with it, with no separate progress file to consult. The recovery
procedure is manual and external to this script by design:

  1) After a crash (or a finished batch), check W&B for which of the queued
     runs actually produced a complete run.
  2) Delete those rows from the todo YAML file.
  3) Re-run this script. It has no memory of previous invocations -- it just
     runs whatever rows are still listed in the file, in order -- so the
     trimmed file *is* the resume point.

On the first unrecoverable error (a misapplied config, an unreachable
controller, a detected mid-run crash) this script aborts immediately rather
than skipping ahead, exactly like seeded_agents.py: whatever row was running
when it stopped, and everything below it, is still untouched in the YAML
file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from budget_experiments import (
    BUDGET_GROUP_NAME,
    budget_overrides,
    budget_run_name,
)
from cti_fidelity_experiments import (
    CTI_GROUP_NAME,
    cti_overrides,
    cti_run_name,
)
from inference_ablations import (
    ORACLE_GROUP_NAME,
    inference_overrides,
    inference_run_name,
)
from seeded_agents import (
    DEFAULT_CTI_CONFIDENCE_THRESHOLD,
    ablation_overrides,
    fail_loudly,
    run_experiment,
    run_one,
    run_step,
    sleep_with_spinner,
)


def load_todo(todo_path: Path) -> dict[str, Any]:
    if not todo_path.exists():
        fail_loudly(f"Todo file not found: {todo_path}")
    with todo_path.open() as f:
        data = yaml.safe_load(f)
    if not data or "queue" not in data:
        fail_loudly(f"Todo file {todo_path} has no top-level 'queue' list.")
    return data


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Run experiments listed in a YAML todo queue, one at a time, in "
            "file order. Trim completed rows out of the file (after checking "
            "W&B) and re-run this script to resume."
        )
    )
    parser.add_argument(
        "--todo-file",
        type=Path,
        default=Path(__file__).resolve().parent / "todo_queue.yaml",
        help="Path to the YAML queue file (default: tests/todo_queue.yaml).",
    )
    parser.add_argument(
        "--dash-cli-path",
        type=Path,
        default=Path(__file__).resolve().parent / "dash_cli.py",
        help="Path to dash_cli.py.",
    )
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=3,
        help="Delay before starting the queue (default: 3 seconds).",
    )
    args = parser.parse_args()

    dash_cli_path = args.dash_cli_path.resolve()
    if not dash_cli_path.exists():
        print(f"dash_cli.py not found: {dash_cli_path}")
        return 1

    todo = load_todo(args.todo_file)
    queue = todo["queue"]
    profile = todo.get("profile", "dista_tiger")
    group_name = todo.get("wandb_group_name", "agents-seeded")
    run_duration_seconds = int(todo.get("run_duration_seconds", 60 * 100))
    health_poll_interval_seconds = int(todo.get("health_poll_interval_seconds", 60))
    default_cti_period = int(todo.get("cti_period", 10))
    default_cti_confidence_threshold = float(
        todo.get("cti_confidence_threshold", DEFAULT_CTI_CONFIDENCE_THRESHOLD)
    )

    if not queue:
        print(f"[done] {args.todo_file} has an empty queue -- nothing to run.", flush=True)
        return 0

    if args.initial_delay_seconds > 0:
        sleep_with_spinner(args.initial_delay_seconds, "Sleeping before starting queue...")

    print("[step] Stopping any previous run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])

    total = len(queue)
    for idx, row in enumerate(queue, start=1):
        if not isinstance(row, dict):
            fail_loudly(f"Queue row #{idx} ({row!r}) is not a mapping.")

        try:
            seed = int(row["seed"])
        except KeyError as exc:
            fail_loudly(f"Queue row #{idx} ({row!r}) is missing required key: {exc}")
            raise AssertionError("unreachable")

        # Inference-model "oracle" ablation row: identified by the `inference`
        # key. Uses the profile's default agent unless one is given, and
        # defaults to the "oracle" W&B group. See tests/inference_ablations.py.
        if "inference" in row:
            inference_mode = row["inference"]
            overrides = inference_overrides(inference_mode)  # validates the mode
            wb_run_name_value = inference_run_name(inference_mode)
            agent = row.get("agent")  # optional; None -> profile default agent
            row_group = row.get("wandb_group_name", ORACLE_GROUP_NAME)

            print(
                f"\n===== Queue item {idx}/{total}: inference={inference_mode} "
                f"seed={seed}"
                f"{f' agent={agent}' if agent is not None else ''} "
                f"({total - idx} remaining after this) =====",
                flush=True,
            )
            run_experiment(
                dash_cli_path=dash_cli_path,
                profile=profile,
                seed=seed,
                overrides=overrides,
                wb_run_name_value=wb_run_name_value,
                group_name=row_group,
                run_duration_seconds=run_duration_seconds,
                health_poll_interval_seconds=health_poll_interval_seconds,
                agent=agent,
                log_label=f"{inference_mode}-seed{seed}",
            )
            continue

        # Budget-constraint row: identified by the `budget` key. Uses the
        # profile's default agent unless one is given, and defaults to the
        # "budget_constraints" W&B group. See tests/budget_experiments.py.
        if "budget" in row:
            budget_config = row["budget"]
            overrides = budget_overrides(budget_config)  # validates the config name
            wb_run_name_value = budget_run_name(budget_config)
            agent = row.get("agent")  # optional; None -> profile default agent
            row_group = row.get("wandb_group_name", BUDGET_GROUP_NAME)

            print(
                f"\n===== Queue item {idx}/{total}: budget={budget_config} "
                f"seed={seed}"
                f"{f' agent={agent}' if agent is not None else ''} "
                f"({total - idx} remaining after this) =====",
                flush=True,
            )
            run_experiment(
                dash_cli_path=dash_cli_path,
                profile=profile,
                seed=seed,
                overrides=overrides,
                wb_run_name_value=wb_run_name_value,
                group_name=row_group,
                run_duration_seconds=run_duration_seconds,
                health_poll_interval_seconds=health_poll_interval_seconds,
                agent=agent,
                log_label=f"{budget_config}-seed{seed}",
            )
            continue

        # CTI-delivery-fidelity row: identified by the `cti` key. Uses the
        # profile's default agent unless one is given, and defaults to the
        # "cti-fidelity" W&B group. See tests/cti_fidelity_experiments.py.
        if "cti" in row:
            cti_config = row["cti"]
            overrides = cti_overrides(cti_config)  # validates the config name
            wb_run_name_value = cti_run_name(cti_config)
            agent = row.get("agent")  # optional; None -> profile default agent
            row_group = row.get("wandb_group_name", CTI_GROUP_NAME)

            print(
                f"\n===== Queue item {idx}/{total}: cti={cti_config} "
                f"seed={seed}"
                f"{f' agent={agent}' if agent is not None else ''} "
                f"({total - idx} remaining after this) =====",
                flush=True,
            )
            run_experiment(
                dash_cli_path=dash_cli_path,
                profile=profile,
                seed=seed,
                overrides=overrides,
                wb_run_name_value=wb_run_name_value,
                group_name=row_group,
                run_duration_seconds=run_duration_seconds,
                health_poll_interval_seconds=health_poll_interval_seconds,
                agent=agent,
                log_label=f"{cti_config}-seed{seed}",
            )
            continue

        # DQN-family epistemic-action ablation row (the original schema).
        try:
            agent = row["agent"]
            mode = row["mode"]
        except KeyError as exc:
            fail_loudly(f"Queue row #{idx} ({row!r}) is missing required key: {exc}")
            raise AssertionError("unreachable")

        cti_period = int(row.get("cti_period", default_cti_period))
        cti_confidence_threshold = float(
            row.get("cti_confidence_threshold", default_cti_confidence_threshold)
        )
        overrides = ablation_overrides(mode, cti_period, cti_confidence_threshold)
        row_group = row.get("wandb_group_name", group_name)

        print(
            f"\n===== Queue item {idx}/{total}: agent={agent} mode={mode} seed={seed} "
            f"({total - idx} remaining after this) =====",
            flush=True,
        )
        run_one(
            dash_cli_path=dash_cli_path,
            profile=profile,
            agent=agent,
            mode=mode,
            overrides=overrides,
            seed=seed,
            run_duration_seconds=run_duration_seconds,
            group_name=row_group,
            health_poll_interval_seconds=health_poll_interval_seconds,
        )

    print("[done] Todo queue exhausted -- all rows ran without a detected failure.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
