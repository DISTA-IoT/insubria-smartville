#!/usr/bin/env python3
"""Multi-seed experiment runner for dash_cli.py.

For each agent in --agents, runs --seeds independent repetitions, varying only
intrusion_detection.seed, so paper results can report mean +/- std across
seeds instead of a single run per configuration. Every run reloads the
--profile config fresh (same pretrained inference module checkpoint every
time) before overriding the agent type and seed, so settings from a previous
agent/seed never leak into the next run.

Workflow per (agent, seed) pair:
1) Reload base profile config.
2) Set intrusion_detection.agent and intrusion_detection.seed.
3) Start experiment and traffic.
4) Wait --run-duration-seconds.
5) Stop experiment and traffic.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_AGENTS = [
    "DQN", "DDQN", "DuelingDQN", "DuelingDDQN",
    "PPO", "A2C",
    "DAI_P", "DAI_A", "DAI_SA", "DAI_F",
]

DEFAULT_SEEDS = [1, 2, 3]


def run_step(script: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"\n[step] Running: dash_cli.py {' '.join(cmd[2:])}\n", flush=True)
    subprocess.run(cmd, check=True)


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


def run_one(
    dash_cli_path: Path,
    profile: str,
    agent: str,
    seed: int,
    run_duration_seconds: int,
    group_name: str,
) -> None:
    run_name = f"{agent}-seed{seed}"
    print(f"[step] Setting up {run_name}...", flush=True)

    run_step(dash_cli_path, ["--profile", profile, "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.agent", agent])
    run_step(dash_cli_path, ["set", "intrusion_detection.seed", str(seed)])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", run_name])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", group_name])

    print(f"[step] Starting {run_name}...", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(run_duration_seconds, f"{run_name} running for {run_duration_seconds} seconds...")

    print(f"[step] Stopping {run_name}...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run multiple seeded repetitions per agent for statistical significance."
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
            "network weights."
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

    total_runs = len(args.agents) * len(args.seeds)
    run_idx = 0
    for agent in args.agents:
        for seed in args.seeds:
            run_idx += 1
            print(f"\n===== Run {run_idx}/{total_runs}: agent={agent} seed={seed} =====", flush=True)
            run_one(
                dash_cli_path=dash_cli_path,
                profile=args.profile,
                agent=agent,
                seed=seed,
                run_duration_seconds=args.run_duration_seconds,
                group_name=args.wandb_group_name,
            )

    print("[done] Seeded sweep completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
