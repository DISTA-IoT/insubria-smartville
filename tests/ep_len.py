#!/usr/bin/env python3
"""Experiment runner for dash_cli.py.

Workflow:
1) Initialize CLI state with some profile.
Loop:
    2) Set some additional params
    4) Start experiment and traffic.
    5) Wait 2 hours.
    6) Stop experiment and traffic.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run_step(script: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"[step] Running: dash_cli.py {' '.join(cmd[2:])}", flush=True)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smartville Tiger Test automation")
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=5,
        help="Delay before starting workflow (default: 0 seconds).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default=2 * 60 * 60,
        help="Duration between starting and stopping experiment (default: 2 hours).",
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
        sleep_with_spinner(args.initial_delay_seconds, f"[wait] Sleeping {args.initial_delay_seconds} seconds before starting workflow...")

    print("[step] Starting workflow...", flush=True)


    print("[step] Stopping previous run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    print("[done] Previous run stopped.", flush=True)


    
    print("[step] Grabing dista_tiger config...", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])


    ################################# ep len 70 ################################################

    print("[step] Setting episode len to 70", flush=True)
    run_step(dash_cli_path, ["set", "intrusion_detection.max_episode_steps", "70"])

    print("[step] Setting run name...", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "ep_len_70"])

    print("[step] Starting run...", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################


    ################################# ep len 60 ################################################

    print("[step] Setting episode len to 60", flush=True)
    run_step(dash_cli_path, ["set", "intrusion_detection.max_episode_steps", "60"])

    print("[step] Setting run name...", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "ep_len_60"])

    print("[step] Starting run...", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################

    ################################# ep len 40 ################################################
    print("[step] Setting episode len to 40", flush=True)
    run_step(dash_cli_path, ["set", "intrusion_detection.max_episode_steps", "40"])

    print("[step] Setting run name...", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "ep_len_40"])

    print("[step] Starting run...", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################

    ################################# ep len 30 ################################################
    print("[step] Setting episode len to 30", flush=True)
    run_step(dash_cli_path, ["set", "intrusion_detection.max_episode_steps", "30"])

    print("[step] Setting run name...", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "ep_len_30"])

    print("[step] Starting run...", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################


   

    print("[done] Workflows completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
