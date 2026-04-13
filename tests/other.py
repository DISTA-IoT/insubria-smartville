#!/usr/bin/env python3
"""Experiment runner for dash_cli.py.

Workflow:
1) Initialize CLI state with some profile.
Loop:
    2) Set some additional params
    4) Start experiment and traffic.
    5) Wait 30 mins.
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
    parser = argparse.ArgumentParser(description="Smartville Tiger Test automation")
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=3,
        help="Delay before starting workflow (default: 5 seconds).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default=60*60,
        help="Duration between starting and stopping experiment (default: 60 mins).",
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


    print("\n[step] Starting workflow..\n", flush=True)

    print("\n[step] Stopping previous run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    print("\n[done] Previous run stopped.\n", flush=True)


    # run_step(dash_cli_path, ["set", "wandb.wb_tracking", "false"])

    ################################ ################################################
    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.n_step_rewards", "5"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "nstep_rewards"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "nstep_rewards5"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################
    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.n_step_rewards", "1"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "nstep_rewards"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "nstep_rewards1"])


    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.n_step_rewards", "2"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "nstep_rewards"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "nstep_rewards2"])

   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.n_step_rewards", "7"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "nstep_rewards"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "nstep_rewards7"])

   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.update_target_freq", "30"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "update_target_freq"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "update_target_freq30"])

   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.update_target_freq", "40"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "update_target_freq"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "update_target_freq40"])

   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.update_target_freq", "60"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "update_target_freq"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "update_target_freq60"])

   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.update_target_freq", "70"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "update_target_freq"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "update_target_freq70"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.update_target_freq", "100"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "update_target_freq"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "update_target_freq100"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.use_soft_update", "false"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "rainbow"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "no_soft_update"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.use_per", "false"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "rainbow"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "no_per"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.use_per", "false"])
    run_step(dash_cli_path, ["set", "intrusion_detection.use_soft_update", "false"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "rainbow"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "no_per_no_soft_update"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ Scale 0.1 ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger_rewards01", "init-config"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "reward_scale"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "rewards01"])

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################

    ################################# Scale 10 ################################################
    
    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger_rewards10", "init-config"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "reward_scale"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "rewards10"])


    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ Scale 100 ################################################
    
    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger_rewards100", "init-config"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "reward_scale"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "rewards100"])


    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.useless_epistemic_penalty", "12"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "useless_epis_penalty"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "useless_epis_penalty12"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.useless_epistemic_penalty", "3"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "useless_epis_penalty"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "useless_epis_penalty3"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.useless_epistemic_penalty", "20"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "useless_epis_penalty"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "useless_epis_penalty20"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################
    
    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.agent_memory_size", "1000"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "agent_memory_size"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agent_memory_size1000"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.agent_memory_size", "100"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "agent_memory_size"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agent_memory_size100"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################

    ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.agent_memory_size", "5000"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "agent_memory_size"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agent_memory_size5000"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ###################################################################################


    # ################################ ################################################

    print("\n[step] Setting profile...\n", flush=True)
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])
    run_step(dash_cli_path, ["set", "intrusion_detection.no_epistemic_actions", "true"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "other"])
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "no_epistemic_actions"])
   

    print("\n[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("\n[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    # ###################################################################################
   
    print("\n[done] Workflows completed.\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
