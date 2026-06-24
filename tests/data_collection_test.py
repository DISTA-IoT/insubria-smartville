#!/usr/bin/env python3
"""Experiment runner for dash_cli.py -- exercises TigerBrain's data collection mode.

Workflow:
1) Stop any previous run.
2) Initialize CLI state with the `data_collection` override profile (turns on
   intrusion_detection.data_collection_mode, disables wandb tracking and
   training, see config/overrides/data_collection.yaml).
3) Start experiment + traffic.
4) Wait `--run-duration-seconds` while the controller buffers and flushes
   shards under intrusion_detection.data_collection_dir.
5) Stop experiment (this calls TigerBrain.shutdown() -> data_recorder.close(),
   flushing the final partial shard) + traffic.

After this script exits, run smartville-controller/read_collected_data.py
inside the controller container against the printed data_collection_dir to
inspect/verify what was recorded.
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
    parser = argparse.ArgumentParser(description="Smartville Tiger data collection mode test")
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=3,
        help="Delay before starting workflow (default: 3 seconds).",
    )
    parser.add_argument(
        "--run-duration-seconds",
        type=int,
        default=5 * 60,
        help="Duration between starting and stopping the capture run (default: 5 minutes).",
    )
    parser.add_argument(
        "--dash-cli-path",
        type=Path,
        default=Path(__file__).resolve().parent / "dash_cli.py",
        help="Path to dash_cli.py.",
    )
    parser.add_argument(
        "--data-collection-dir",
        default="/pox/pox/smartController/tiger_data_collection/",
        help="Value to set for intrusion_detection.data_collection_dir on the controller "
             "(path is inside the controller container's filesystem).",
    )
    parser.add_argument(
        "--shard-size",
        type=int,
        default=200,
        help="Samples buffered before a shard is flushed (intrusion_detection.data_collection_shard_size). "
             "Kept small by default so a short test run still produces multiple shards.",
    )
    parser.add_argument(
        "--use-packet-feats",
        action="store_true",
        help="Also record packet_features in each shard (intrusion_detection.data_collection_use_packet_feats).",
    )
    parser.add_argument(
        "--run-name",
        default="data_collection_smoketest",
        help="wandb.wb_run_name to tag this run with (wandb tracking itself stays disabled by the profile).",
    )

    args = parser.parse_args()

    dash_cli_path = args.dash_cli_path.resolve()
    if not dash_cli_path.exists():
        print(f"dash_cli.py not found: {dash_cli_path}")
        return 1

    if args.initial_delay_seconds > 0:
        sleep_with_spinner(args.initial_delay_seconds, "Sleeping before starting workflow...")

    print("[step] Stopping any previous run...\n", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])
    print("\n[done] Previous run stopped.\n", flush=True)

    print("[step] Initializing config from the data_collection override profile...", flush=True)
    run_step(dash_cli_path, ["--profile", "data_collection", "init-config"])

    print("[step] Setting run-specific knobs...", flush=True)
    run_step(dash_cli_path, ["set", "wandb.wb_run_name", args.run_name])
    run_step(dash_cli_path, ["set", "intrusion_detection.data_collection_dir", args.data_collection_dir])
    run_step(dash_cli_path, ["set", "intrusion_detection.data_collection_shard_size", str(args.shard_size)])
    if args.use_packet_feats:
        run_step(dash_cli_path, ["set", "intrusion_detection.data_collection_use_packet_feats", "true"])

    print("[step] Starting capture run...", flush=True)
    run_step(dash_cli_path, ["start-experiment"])
    run_step(dash_cli_path, ["start-traffic"])

    sleep_with_spinner(
        args.run_duration_seconds,
        f"Capturing traffic for {args.run_duration_seconds} seconds...",
    )

    print("[step] Stopping capture run (flushes the final partial shard)...", flush=True)
    run_step(dash_cli_path, ["stop-experiment"])
    run_step(dash_cli_path, ["stop-traffic"])

    print(
        "\n[done] Capture run complete. Inspect the recorded shards on the controller "
        f"container with:\n\n"
        f"    python3 read_collected_data.py {args.data_collection_dir} --latest\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
