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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smartville Test automation")
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=3,
        help="Delay before starting workflow (default: 3 seconds).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default= 30*60,
        help="Duration between starting and stopping experiment (default: 30 mins).",
    )
    parser.add_argument(
        "--dash-cli-path",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "dash_cli.py",
        help="Path to dash_cli.py.",
    )
    

    args = parser.parse_args()

    dash_cli_path = args.dash_cli_path.resolve()
    if not dash_cli_path.exists():
        print(f"dash_cli.py not found: {dash_cli_path}")
        return 1

    if args.initial_delay_seconds > 0:
        sleep_with_spinner(args.initial_delay_seconds, f"[wait] Sleeping {args.initial_delay_seconds} seconds before starting workflow...")



    def stop_experiment():
        print("\n[step] Stopping previous run...\n", flush=True)
        run_step(dash_cli_path, ["stop-experiment"])
        run_step(dash_cli_path, ["stop-traffic"])
        print("\n[done] Previous run stopped.\n", flush=True)


    def start_experiment():
        print("\n[step] Starting run...\n", flush=True)
        run_step(dash_cli_path, ["start-experiment"])
        run_step(dash_cli_path, ["start-traffic"])
        sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")


    def curricula_sweep(seed):

        run_step(dash_cli_path, ["--profile", "dista_pretraining_curr_b", "init-config"])
        run_step(dash_cli_path, ["set", "wandb.wb_group_name", "curricula"])
        run_step(dash_cli_path, ["set", "wandb.wb_run_name", "curr_b_"+str(seed)])
        run_step(dash_cli_path, ["set", "intrusion_detection.save_models", "false"])
        run_step(dash_cli_path, ["set", "intrusion_detection.seed", str(seed)])
        # run_step(dash_cli_path, ["set", "wandb.wb_tracking", "false"])
        start_experiment()
        stop_experiment()

        run_step(dash_cli_path, ["--profile", "dista_pretraining_curr_c", "init-config"])
        run_step(dash_cli_path, ["set", "wandb.wb_group_name", "curricula"])
        run_step(dash_cli_path, ["set", "wandb.wb_run_name", "curr_c_"+str(seed)])
        run_step(dash_cli_path, ["set", "intrusion_detection.save_models", "false"])
        run_step(dash_cli_path, ["set", "intrusion_detection.seed", str(seed)])
        # run_step(dash_cli_path, ["set", "wandb.wb_tracking", "false"])
        start_experiment()
        stop_experiment()

        run_step(dash_cli_path, ["--profile", "dista_pretraining", "init-config"])
        run_step(dash_cli_path, ["set", "wandb.wb_group_name", "curricula"])
        run_step(dash_cli_path, ["set", "wandb.wb_run_name", "curr_a_"+str(seed)])
        run_step(dash_cli_path, ["set", "intrusion_detection.save_models", "false"])
        run_step(dash_cli_path, ["set", "intrusion_detection.seed", str(seed)])
        # run_step(dash_cli_path, ["set", "wandb.wb_tracking", "false"])
        start_experiment()
        stop_experiment()

    

    print("\n[step] Starting workflow...\n", flush=True)

    stop_experiment()

    
    for seed in [555, 666, 777, 888]:
        curricula_sweep(seed)
    
   
    print("[done] Workflows completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
