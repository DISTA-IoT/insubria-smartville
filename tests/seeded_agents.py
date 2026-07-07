#!/usr/bin/env python3
"""Multi-seed DQN-ablation experiment runner for dash_cli.py.

Sweeps only the value-learning (DQN-family) agents -- DQN, DDQN, DuelingDQN,
DuelingDDQN -- across the three mutually-exclusive epistemic-action ablation
modes described in drl_description.md / tiger_brain_new.py's
`_select_unknown_cluster_action`:

- "baseline":     learned policy decides action 2 (buy CTI) on its own,
                   i.e. greedy_cti=False, cti_period=-1, no_epistemic_actions=False
                   (the config/default.yaml ablation-knob defaults).
- "no_epistemic": intrusion_detection.no_epistemic_actions=True -- any agent-chosen
                   action 2 is remapped to 1 (block); epistemic actions are
                   effectively disabled.
- "periodic_cti": intrusion_detection.cti_period=<N> -- action is hard-forced to 2
                   every N steps, otherwise the agent is queried but its own 2's
                   are remapped to 1.
- "greedy_cti":   intrusion_detection.greedy_cti=True -- action is forced to 2
                   whenever an unbought G2 class is available, otherwise the
                   agent is queried but its own 2's are remapped to 1.
- "fixed_threshold": intrusion_detection.fixed_threshold_cti=True -- action is
                   forced to 2 whenever the cluster confidence is below
                   cti_confidence_threshold, otherwise the agent is queried but
                   its own 2's are remapped to 1.

For each (agent, mode) config, runs --seeds independent repetitions, varying
only intrusion_detection.seed, so paper results can report mean +/- std
across seeds instead of a single run per configuration. Every run reloads
the --profile config fresh (same pretrained inference module checkpoint
every time) before overriding the agent type, ablation mode, and seed, so
settings from a previous run never leak into the next one.

Sweep order: seeds are the OUTERMOST loop, configs (agent x mode) the
innermost -- i.e. every (agent, mode) config is run once with seed[0] before
any config is run with seed[1], and so on. This way, if the sweep is
interrupted partway through, every seed that was started has a complete set
of configs to compare, rather than some seeds having full coverage and the
in-progress seed having only a few configs.

Workflow per (seed, agent, mode) triple:
1) Reload base profile config (this also resets all ablation knobs to the
   profile's defaults).
2) Set intrusion_detection.agent and intrusion_detection.seed, plus whichever
   single ablation knob this mode turns on ("baseline" sets none, leaving the
   profile defaults in place).
3) Start experiment, then verify from the controller's own response that
   the seed/agent it actually applied match what was requested. Aborts the
   whole sweep loudly (non-zero exit, clear message) on any mismatch or
   error, rather than continuing on a misconfigured run.
4) Start traffic.
5) Wait --run-duration-seconds, polling /controller_health every
   --health-poll-interval-seconds; aborts loudly as soon as a crash is
   detected instead of waiting out the rest of the duration.
6) Stop experiment and traffic.

Requires the controller-side /initialize echo of applied_seed/applied_agent
and the /health route (smartville-controller branch claude/seed-before-agent-init
or later) and dash.py's /controller_health proxy + --raw-json support in
dash_cli.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_AGENTS = ["DQN", "DDQN", "DuelingDQN", "DuelingDDQN"]

DEFAULT_SEEDS = [1, 2, 3]
DEFAULT_HEALTH_POLL_INTERVAL_SECONDS = 60
DEFAULT_CTI_PERIOD = 10
DEFAULT_CTI_CONFIDENCE_THRESHOLD = 0.5

# The three ablation knobs in tiger_brain_new.py's
# `_select_unknown_cluster_action` are mutually exclusive, so "baseline"
# leaves all of them at the profile's defaults (greedy_cti=False,
# cti_period=-1, no_epistemic_actions=False) and each ablation mode below
# sets exactly one of them.
ABLATION_MODES = ["baseline", "no_epistemic", "periodic_cti", "greedy_cti", "fixed_threshold"]

# wandb.wb_run_name uses these short labels instead of the agent name whenever
# mode != "baseline", so that W&B's "group by name" groups all agents sharing
# an ablation together (the agent itself is still recorded in the run's
# wandb config dict, same as the seed, so neither is lost -- just not in the
# run name).
ABLATION_RUN_NAME = {
    "no_epistemic": "no_epis",
    "periodic_cti": "periodic",
    "greedy_cti": "greedy",
    "fixed_threshold": "fixed_thr",
}


def wb_run_name(agent: str, mode: str) -> str:
    if mode == "baseline":
        return agent
    return ABLATION_RUN_NAME[mode]


def ablation_overrides(mode: str, cti_period: int, cti_confidence_threshold: float) -> dict[str, Any]:
    if mode == "baseline":
        return {}
    if mode == "no_epistemic":
        return {"intrusion_detection.no_epistemic_actions": "true"}
    if mode == "periodic_cti":
        return {"intrusion_detection.cti_period": str(cti_period)}
    if mode == "greedy_cti":
        return {"intrusion_detection.greedy_cti": "true"}
    if mode == "fixed_threshold":
        return {"intrusion_detection.fixed_threshold_cti": "true",
                "intrusion_detection.cti_confidence_threshold": str(cti_confidence_threshold)}
    raise ValueError(f"Unknown ablation mode: {mode!r}")


def fail_loudly(message: str) -> None:
    """
    Abort the whole sweep immediately and unmissably, instead of silently
    skipping a broken run or sleeping out a multi-hour duration that's
    already known to be invalid.
    """
    banner = "!" * 78
    print(f"\n{banner}\n[ABORT] {message}\n{banner}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def run_step(script: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"\n[step] Running: dash_cli.py {' '.join(cmd[2:])}\n", flush=True)
    subprocess.run(cmd, check=True)


def run_step_json(script: Path, args: list[str]) -> dict[str, Any]:
    """
    Like run_step, but via --raw-json so the response body can be inspected
    programmatically. Used for the calls whose actual effect (not just
    "the HTTP request didn't error") needs verifying: did the controller
    apply the seed/agent we asked for, and is it still alive.
    """
    cmd = [sys.executable, str(script), "--raw-json", *args]
    print(f"\n[step] Running: dash_cli.py --raw-json {' '.join(args)}\n", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    if result.returncode != 0:
        fail_loudly(f"dash_cli.py {' '.join(args)} exited with code {result.returncode}")

    try:
        last_line = result.stdout.strip().splitlines()[-1]
        parsed = json.loads(last_line)
        return parsed["body"]
    except (json.JSONDecodeError, IndexError, KeyError) as exc:
        fail_loudly(f"dash_cli.py {' '.join(args)} produced no parseable --raw-json output: {exc}")
        raise AssertionError("unreachable")  # for type-checkers; fail_loudly never returns


def sleep_with_spinner(seconds: int, label: str) -> None:
    spinner = "|/-\\"
    start = time.monotonic()
    tick = 0
    while True:
        elapsed = time.monotonic() - start
        if elapsed >= seconds:
            break
        remaining = max(0, int(seconds - elapsed))
        frame = spinner[tick % len(spinner)]
        sys.stdout.write(f"\r[wait] {label} {frame} ({remaining}s remaining)")
        sys.stdout.flush()
        tick += 1
        time.sleep(0.1)
    sys.stdout.write(f"\r[done] {label} complete.{' ' * 20}\n")
    sys.stdout.flush()


def wait_with_health_checks(
    dash_cli_path: Path,
    total_seconds: int,
    run_name: str,
    poll_interval_seconds: int,
) -> None:
    """
    Sleeps out total_seconds in poll_interval_seconds chunks, polling
    /controller_health between chunks. A daemon thread crashing inside the
    controller leaves the process up and answering requests, so without this
    a dead run would otherwise look identical to a healthy one until the
    full multi-hour duration had already been wasted.
    """
    elapsed = 0.0
    while elapsed < total_seconds:
        chunk = min(poll_interval_seconds, total_seconds - elapsed)
        sleep_with_spinner(int(round(chunk)), f"{run_name} running ({int(elapsed + chunk)}/{total_seconds}s)...")
        elapsed += chunk

        body = run_step_json(dash_cli_path, ["check-controller-health"])
        if body.get("status") == "crashed":
            crash_info = body.get("crash_info", {})
            fail_loudly(
                f"{run_name}: controller's inference loop crashed mid-run at check "
                f"#{crash_info.get('check_count')} after {int(elapsed)}s: {crash_info.get('error')}"
            )
        elif body.get("status") != "ok":
            fail_loudly(f"{run_name}: unexpected controller health status: {body}")


def run_one(
    dash_cli_path: Path,
    profile: str,
    agent: str,
    mode: str,
    overrides: dict[str, Any],
    seed: int,
    run_duration_seconds: int,
    group_name: str,
    health_poll_interval_seconds: int,
) -> None:
    # run_name is just for console/log messages and error reporting, so it
    # stays fully descriptive. wb_run_name is what actually gets sent to
    # W&B, and is intentionally collapsed to just the agent (mode=="baseline")
    # or just the ablation label (otherwise) for grouping; agent and seed are
    # both still recorded in the run's wandb config dict regardless.
    run_name = f"{agent}-{mode}-seed{seed}"
    print(f"[step] Setting up {run_name}...", flush=True)

    run_step(dash_cli_path, ["--profile", profile, "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.agent", agent])
    run_step(dash_cli_path, ["set", "intrusion_detection.seed", str(seed)])
    for key, value in overrides.items():
        run_step(dash_cli_path, ["set", key, value])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", wb_run_name(agent, mode)])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", group_name])

    print(f"[step] Starting {run_name} and verifying applied config...", flush=True)
    body = run_step_json(dash_cli_path, ["start-experiment"])

    if body.get("status_code") != 200:
        fail_loudly(f"{run_name}: controller rejected /initialize: {body.get('msg')}")
    if str(body.get("applied_seed")) != str(seed):
        fail_loudly(
            f"{run_name}: requested seed {seed!r} but controller reports applied_seed="
            f"{body.get('applied_seed')!r} -- the seed was NOT transmitted/applied correctly."
        )
    if body.get("applied_agent") != agent:
        fail_loudly(
            f"{run_name}: requested agent {agent!r} but controller reports applied_agent="
            f"{body.get('applied_agent')!r}."
        )
    print(f"[ok] Confirmed controller applied seed={body['applied_seed']} agent={body['applied_agent']}", flush=True)

    run_step(dash_cli_path, ["start-traffic"])

    wait_with_health_checks(dash_cli_path, run_duration_seconds, run_name, health_poll_interval_seconds)

    print(f"[step] Stopping {run_name}...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run multiple seeded repetitions of DQN-family agents x epistemic-"
            "action ablation modes for statistical significance."
        )
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=DEFAULT_AGENTS,
        help=f"Agent types to sweep (default: {DEFAULT_AGENTS}).",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=DEFAULT_SEEDS,
        help=(
            f"Seeds to run per agent (default: {DEFAULT_SEEDS}). Each run starts "
            "from the same pretrained inference module checkpoint; the seed only "
            "controls exploration/sampling order and the DM agent's initial "
            "network weights. Seeds are the outermost loop: every (agent, "
            "ablation-mode) config is run once per seed before moving to the "
            "next seed."
        ),
    )
    parser.add_argument(
        "--ablation-modes",
        nargs="+",
        default=ABLATION_MODES,
        choices=ABLATION_MODES,
        help=(
            f"Epistemic-action ablation modes to sweep (default: {ABLATION_MODES}). "
            "'baseline' leaves greedy_cti/cti_period/no_epistemic_actions at the "
            "profile's defaults (i.e. the learned policy decides action 2 on its "
            "own); the other three each force exactly one of those mutually-"
            "exclusive override knobs in tiger_brain_new.py."
        ),
    )
    parser.add_argument(
        "--cti-period",
        type=int,
        default=DEFAULT_CTI_PERIOD,
        help=(
            f"Value of intrusion_detection.cti_period used by the 'periodic_cti' "
            f"ablation mode (default: {DEFAULT_CTI_PERIOD})."
        ),
    )
    parser.add_argument(
        "--cti-confidence-threshold",
        type=float,
        default=DEFAULT_CTI_CONFIDENCE_THRESHOLD,
        help=(
            f"Value of intrusion_detection.cti_confidence_threshold used by the "
            f"'fixed_threshold' ablation mode (default: {DEFAULT_CTI_CONFIDENCE_THRESHOLD})."
        ),
    )
    parser.add_argument(
        "--profile",
        default="dista_tiger",
        help="config/overrides/<profile>.yaml to (re)load before each run (default: dista_tiger).",
    )
    parser.add_argument(
        "--wandb-group-name",
        default="agents-seeded",
        help="W&B group name shared by all runs in this sweep, for later aggregation (default: agents-seeded).",
    )
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=3,
        help="Delay before starting the sweep (default: 3 seconds).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default=60 * 60,
        help="Duration of each individual seeded run (default: 60 minutes).",
    )
    parser.add_argument(
        "--health-poll-interval-seconds",
        type=int,
        default=DEFAULT_HEALTH_POLL_INTERVAL_SECONDS,
        help=(
            "How often to poll /controller_health during a run (default: "
            f"{DEFAULT_HEALTH_POLL_INTERVAL_SECONDS}s). A crash is detected and the whole "
            "sweep is aborted at the next poll, instead of after the full run duration."
        ),
    )
    parser.add_argument(
        "--dash-cli-path",
        type=Path,
        default=Path(__file__).resolve().parent / "dash_cli.py",
        help="Path to dash_cli.py.",
    )

    args = parser.parse_args()

    dash_cli_path = args.dash_cli_path.resolve()
    if not dash_cli_path.exists():
        print(f"dash_cli.py not found: {dash_cli_path}")
        return 1

    if args.initial_delay_seconds > 0:
        sleep_with_spinner(args.initial_delay_seconds, "Sleeping before starting sweep...")

    print("[step] Stopping any previous run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])

    total_runs = len(args.seeds) * len(args.agents) * len(args.ablation_modes)
    run_idx = 0
    for seed in args.seeds:
        for agent in args.agents:
            for mode in args.ablation_modes:
                run_idx += 1
                overrides = ablation_overrides(mode, args.cti_period, args.cti_confidence_threshold)
                print(
                    f"\n===== Run {run_idx}/{total_runs}: "
                    f"seed={seed} agent={agent} mode={mode} =====",
                    flush=True,
                )
                run_one(
                    dash_cli_path=dash_cli_path,
                    profile=args.profile,
                    agent=agent,
                    mode=mode,
                    overrides=overrides,
                    seed=seed,
                    run_duration_seconds=args.run_duration_seconds,
                    group_name=args.wandb_group_name,
                    health_poll_interval_seconds=args.health_poll_interval_seconds,
                )

    print("[done] Seeded sweep completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
