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
    parser = argparse.ArgumentParser(description="Smartville Tiger Test automation")
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=3,
        help="Delay before starting workflow (default: 0 seconds).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default=60*60,
        help="Duration between starting and stopping experiment (default: 1 hour).",
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

    print("\n[step] Starting workflow...\n", flush=True)


    print("\n[step] Stopping previous run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    
    run_step(dash_cli_path, ["--profile", "dista_tiger", "init-config"])

    print("\n[step] Enabling custom inference model...\n", flush=True)
    run_step(dash_cli_path, ["set", "neural_modules.custom_inference_model_path", "true"])

    # run_step(dash_cli_path, ["set", "wandb.wb_tracking", "false"])

    ################################# simple krloss ################################################

    print("[step] Setting inference models path...\n", flush=True)
    run_step(dash_cli_path, ["set", "inference_model_variant", "simple_krloss"])

    print("[step] Setting modules path...\n", flush=True)
    run_step(dash_cli_path, ["set", "neural_modules.custom_classifier_path", "multiclass_flow_packet_classifier_pretrained_h200_simple_krloss.pt"])
    run_step(dash_cli_path, ["set", "neural_modules.custom_confidence_decoder_path", "flow_packet_confidence_decoder_pretrained_h200simple_krloss.pt"])

    print("[step] Setting run name...\n", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agency_simple_krloss"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "asap_archs"])

    print("[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################

    ################################# optim ################################################

    print("[step] Setting inference models path...\n", flush=True)
    run_step(dash_cli_path, ["set", "inference_model_variant", "optim"])


    print("[step] Setting modules path...\n", flush=True)
    run_step(dash_cli_path, ["set", "neural_modules.custom_classifier_path", "multiclass_flow_packet_classifier_pretrained_h200_optim.pt"])
    run_step(dash_cli_path, ["set", "neural_modules.custom_confidence_decoder_path", "flow_packet_confidence_decoder_pretrained_h200_optim.pt"])

    print("[step] Setting run name...\n", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agency_optim"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "asap_archs"])

    print("[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################

    ################################# dotprod KR ################################################

    print("[step] Setting inference models path...\n", flush=True)
    run_step(dash_cli_path, ["set", "inference_model_variant", "dotprod_kr"])


    print("[step] Setting modules path...\n", flush=True)
    run_step(dash_cli_path, ["set", "neural_modules.custom_classifier_path", "multiclass_flow_packet_classifier_pretrained_h200_dotprod_kr.pt"])
    run_step(dash_cli_path, ["set", "neural_modules.custom_confidence_decoder_path", "flow_packet_confidence_decoder_pretrained_h200_dotprod_kr.pt"])

    print("[step] Setting run name...\n", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agency_dotprod_kr"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "asap_archs"])

    print("[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ##################################################################################


    ################################# dotprod KR + simple krloss ############################################

    print("[step] Setting inference models path...\n", flush=True)
    run_step(dash_cli_path, ["set", "inference_model_variant", "dotprod_kr_simple_krloss"])


    print("[step] Setting modules path...\n", flush=True)
    run_step(dash_cli_path, ["set", "neural_modules.custom_classifier_path", "multiclass_flow_packet_classifier_pretrained_h200_dotprod_simple krloss.pt"])
    run_step(dash_cli_path, ["set", "neural_modules.custom_confidence_decoder_path", "flow_packet_confidence_decoder_pretrained_h200dotprod_simple krloss.pt"])

    print("[step] Setting run name...\n", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", "agency_dotprod_kr_simplekrloss"])
    run_step(dash_cli_path, ["set", "wandb.wb_group_name", "asap_archs"])


    print("[step] Starting run...\n", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(args.run_duration_seconds, f"[wait] Experiment running for {args.run_duration_seconds} seconds...")

    print("[step] Stopping run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    ####################################################################################


    print("[done] Workflows completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
