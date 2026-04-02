#!/usr/bin/env python3
"""Delayed experiment runner for dash_cli.py.

Workflow:
1) Wait 2 hours.
2) Initialize CLI state with dista_tiger profile.
3) Set intrusion_detection.agent to DQN.
4) Start experiment and traffic.
5) Wait 3 hours.
6) Stop experiment.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run_step(script: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"[step] Running: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Delayed dista_tiger Dash CLI automation")
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=2 * 60 * 60,
        help="Delay before starting workflow (default: 2 hours).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default=3 * 60 * 60,
        help="Duration between starting and stopping experiment (default: 3 hours).",
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

    print(f"[wait] Sleeping {args.initial_delay_seconds} seconds before starting workflow...", flush=True)
    time.sleep(args.initial_delay_seconds)

    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.agent", "DQN"])
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    print(f"[wait] Experiment running for {args.run_duration_seconds} seconds...", flush=True)
    time.sleep(args.run_duration_seconds)

    run_step(dash_cli_path, ["stop-experiment"])
    print("[done] Workflow completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
