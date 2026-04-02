#!/usr/bin/env python3
"""CLI client for SmartVille dashboard endpoints.

This tool mirrors the HTTP requests sent by dashboard/static/js/dash.js,
while making configuration editable from the command line and persisted on disk.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig, OmegaConf

DEFAULT_STATE_PATH = Path.home() / ".smartville" / "dash_cli_state.yaml"
DEFAULT_CONFIG_DIR = (Path(__file__).resolve().parents[1] / "config").resolve()

OmegaConf.register_new_resolver("len", lambda x: len(x), replace=True)

# Keep parity with the checkboxes in dashboard/templates/index.html
KNOWN_HEALTH_METRICS = [
    "CPU",
    "RAM",
    "external_http_rtt",
    "icmp_min_rtt_ms",
    "icmp_max_rtt_ms",
    "icmp_avg_rtt_ms",
    "icmp_loss_percent",
    "http_min_rtt_ms",
    "http_max_rtt_ms",
    "http_avg_rtt_ms",
    "http_loss_percent",
    "inbound_MBps",
    "outbound_MBps",
    "inbound_packets_per_second",
    "outbound_packets_per_second",
]


@dataclass
class HttpResult:
    method: str
    url: str
    status: int
    body: Any


class DashboardCLI:
    def __init__(self, base_url: str, state_file: Path, config_dir: Path, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.state_file = state_file
        self.config_dir = config_dir
        self.timeout = timeout
        self.session = requests.Session()

    def load_hydra_config(self, profile: str | None, hydra_overrides: list[str]) -> DictConfig:
        overrides = list(hydra_overrides)
        if profile:
            overrides.append(f"override={profile}")

        with initialize_config_dir(config_dir=str(self.config_dir), version_base="1.2"):
            return compose(config_name="default", overrides=overrides)

    def build_frontend_config(self, cfg: DictConfig) -> dict[str, Any]:
        conf = OmegaConf.to_container(cfg, resolve=True)
        assert isinstance(conf, dict)

        # GUI sends rewards as a flattened dict produced from form names like rewards.echo
        rewards = conf.get("rewards", [])
        if isinstance(rewards, list):
            merged_rewards: dict[str, Any] = {}
            for entry in rewards:
                if isinstance(entry, dict):
                    merged_rewards.update(entry)
            conf["rewards"] = merged_rewards

        # GUI sends health.probe_metrics as boolean map, not as list.
        health = conf.setdefault("health", {})
        selected = set(health.get("probe_metrics", [])) if isinstance(health.get("probe_metrics"), list) else set()
        health["probe_metrics"] = {metric: (metric in selected) for metric in KNOWN_HEALTH_METRICS}

        return conf

    def load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {}
        return yaml.safe_load(self.state_file.read_text()) or {}

    def save_state(self, data: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(yaml.safe_dump(data, sort_keys=False))

    def http(self, method: str, path: str, *, json_payload: Any | None = None) -> HttpResult:
        url = f"{self.base_url}{path}"
        response = self.session.request(method=method, url=url, json=json_payload, timeout=self.timeout)

        try:
            body: Any = response.json()
        except Exception:
            body = response.text

        return HttpResult(method=method.upper(), url=url, status=response.status_code, body=body)


def infer_value(raw: str) -> Any:
    """Parse CLI value with YAML semantics, fallback to raw string."""
    try:
        return yaml.safe_load(raw)
    except Exception:
        return raw


def set_by_dotpath(data: dict[str, Any], dotpath: str, value: Any) -> None:
    keys = dotpath.split(".")
    cursor: dict[str, Any] = data
    for key in keys[:-1]:
        node = cursor.get(key)
        if not isinstance(node, dict):
            node = {}
            cursor[key] = node
        cursor = node
    cursor[keys[-1]] = value


def delete_by_dotpath(data: dict[str, Any], dotpath: str) -> bool:
    keys = dotpath.split(".")
    cursor: dict[str, Any] = data
    for key in keys[:-1]:
        node = cursor.get(key)
        if not isinstance(node, dict):
            return False
        cursor = node
    return cursor.pop(keys[-1], None) is not None


def pretty_print_result(result: HttpResult) -> None:
    print(f"\n=== {result.method} {result.url} ===")
    print(f"Status: {result.status}")
    print("Response:")
    if isinstance(result.body, (dict, list)):
        print(json.dumps(result.body, indent=2, sort_keys=True))
    else:
        print(result.body)


def read_wandb_api_key(repo_root: Path) -> str | None:
    """
    Read WANDB_API_KEY from env first, then from <repo_root>/.env.
    """
    env_key = os.environ.get("WANDB_API_KEY")
    if env_key:
        return env_key.strip()

    env_file = repo_root / ".env"
    if not env_file.exists():
        return None

    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "WANDB_API_KEY":
            return value.strip().strip("'\"")
    return None


def query_wandb_run(entity: str, project: str, run_name: str, api_key: str, top_n_runs: int = 50) -> dict[str, Any] | None:
    endpoint = "https://api.wandb.ai/graphql"
    query = """
    query ProjectRuns($entity: String!, $project: String!, $first: Int!) {
      project(name: $project, entityName: $entity) {
        runs(first: $first, order: "-created_at") {
          edges {
            node {
              id
              name
              displayName
              state
              updatedAt
              summaryMetrics
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {"entity": entity, "project": project, "first": top_n_runs},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    edges = (data.get("data", {}).get("project", {}) or {}).get("runs", {}).get("edges", [])
    for edge in edges:
        node = edge.get("node", {})
        if node.get("displayName") == run_name or node.get("name") == run_name:
            return node
    return None


def summarize_wandb_metrics(summary_metrics: dict[str, Any], max_metrics: int = 25) -> dict[str, float]:
    numeric = {
        k: float(v)
        for k, v in summary_metrics.items()
        if not k.startswith("_") and isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    ordered = dict(sorted(numeric.items(), key=lambda kv: kv[0])[:max_metrics])
    return ordered


def print_wandb_summary(run: dict[str, Any], max_metrics: int) -> None:
    summary = summarize_wandb_metrics(run.get("summaryMetrics", {}), max_metrics=max_metrics)
    print("\n=== Weights & Biases run monitor ===")
    print(f"Run id: {run.get('id')}")
    print(f"Run name: {run.get('name')}")
    print(f"Run displayName: {run.get('displayName')}")
    print(f"Run state: {run.get('state')}")
    print(f"Updated at: {run.get('updatedAt')}")
    if not summary:
        print("No numeric metrics found in W&B summaryMetrics yet.")
        return
    print("Metric summary (latest numeric values from summaryMetrics):")
    print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="SmartVille dashboard CLI client")
    parser.add_argument("--base-url", default="http://127.0.0.1:7777", help="Dashboard HTTP base URL")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH, help="Persistent config state file")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR, help="Hydra config directory")
    parser.add_argument("--profile", default="", help="config/overrides/<profile>.yaml to merge")
    parser.add_argument(
        "--hydra-override",
        action="append",
        default=[],
        help="Additional Hydra override (repeatable), e.g. --hydra-override intrusion_detection.agent=DQN",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-config", help="(Re)initialize local state from Hydra config")
    sub.add_parser("show-config", help="Print current persisted frontend-like config")

    p_set = sub.add_parser("set", help="Set a config value using dot path")
    p_set.add_argument("key")
    p_set.add_argument("value", help="YAML/JSON scalar/object/list")

    p_del = sub.add_parser("unset", help="Unset a config value using dot path")
    p_del.add_argument("key")

    p_start_one = sub.add_parser("start-traffic-single", help="Call /launch_traffic_single")
    p_start_one.add_argument("hostname", help="Host name, e.g. attacker-1 or attacker-1_start_traffic")

    p_stop_one = sub.add_parser("stop-traffic-single", help="Call /stop_traffic_single")
    p_stop_one.add_argument("hostname", help="Host name, e.g. attacker-1 or attacker-1_stop_traffic")

    # Endpoint wrappers (same routes used by dash.js)
    sub.add_parser("refresh-containers")
    sub.add_parser("start-experiment")
    sub.add_parser("stop-experiment")
    sub.add_parser("attach-controller")
    sub.add_parser("start-traffic")
    sub.add_parser("stop-traffic")
    sub.add_parser("check-traffic")
    sub.add_parser("start-services")
    sub.add_parser("stop-services")
    sub.add_parser("start-zookeeper")
    sub.add_parser("stop-zookeeper")
    sub.add_parser("start-kafka")
    sub.add_parser("stop-kafka")
    sub.add_parser("start-prometheus")
    sub.add_parser("stop-prometheus")
    sub.add_parser("start-grafana")
    sub.add_parser("stop-grafana")
    sub.add_parser("open-grafana")
    p_wandb = sub.add_parser("wandb-monitor", help="Poll W&B for current experiment metrics and print summary")
    p_wandb.add_argument("--top-n-runs", type=int, default=50, help="How many recent runs to scan in project")
    p_wandb.add_argument("--max-metrics", type=int, default=25, help="Maximum number of metrics in summary output")
    p_wandb.add_argument("--watch", action="store_true", help="Continuously poll and print summaries")
    p_wandb.add_argument("--interval-secs", type=int, default=10, help="Polling interval in seconds when --watch is set")

    args = parser.parse_args()
    client = DashboardCLI(args.base_url, args.state_file, args.config_dir, timeout=args.timeout)

    if args.command == "init-config":
        cfg = client.load_hydra_config(args.profile or None, args.hydra_override)
        state = client.build_frontend_config(cfg)
        client.save_state(state)
        print(f"Initialized config state at: {args.state_file}")
        print("Tip: use `show-config`, `set`, and `unset` to tune values before sending requests.")
        return 0

    state = client.load_state()
    if not state and args.command not in {"show-config", "refresh-containers"}:
        cfg = client.load_hydra_config(args.profile or None, args.hydra_override)
        state = client.build_frontend_config(cfg)
        client.save_state(state)
        print(f"No state file found. Auto-initialized from Hydra into: {args.state_file}")

    if args.command == "show-config":
        if not state:
            print("No persisted state found. Run `init-config` first.")
            return 1
        print(yaml.safe_dump(state, sort_keys=False))
        return 0

    if args.command == "set":
        set_by_dotpath(state, args.key, infer_value(args.value))
        client.save_state(state)
        print(f"Set `{args.key}` and saved {args.state_file}")
        return 0

    if args.command == "unset":
        removed = delete_by_dotpath(state, args.key)
        client.save_state(state)
        if removed:
            print(f"Unset `{args.key}` and saved {args.state_file}")
            return 0
        print(f"Key `{args.key}` was not present.")
        return 1

    if args.command == "wandb-monitor":
        api_key = read_wandb_api_key(Path(__file__).resolve().parents[1])
        if not api_key:
            print(
                "WANDB_API_KEY was not found. Set it in environment or in repository .env "
                "(e.g. WANDB_API_KEY=...)."
            )
            return 1

        wandb_cfg = state.get("wandb", {})
        project = wandb_cfg.get("wb_project_name")
        run_name = wandb_cfg.get("wb_run_name")
        entity = wandb_cfg.get("entity")
        tracking_enabled = wandb_cfg.get("wb_tracking", False)

        if not project or not run_name or not entity:
            print("Missing wandb.entity / wandb.wb_project_name / wandb.wb_run_name in CLI state.")
            return 1

        if not tracking_enabled:
            print("Warning: wandb.wb_tracking is false in config; monitoring may find no active run.")

        def do_poll() -> None:
            run = query_wandb_run(
                entity=entity,
                project=project,
                run_name=run_name,
                api_key=api_key,
                top_n_runs=args.top_n_runs,
            )
            if not run:
                print(f"No W&B run found for entity/project/name: {entity}/{project}/{run_name}")
                return
            print_wandb_summary(run, max_metrics=args.max_metrics)

        if args.watch:
            try:
                while True:
                    do_poll()
                    time.sleep(args.interval_secs)
            except KeyboardInterrupt:
                print("\nStopped W&B monitoring.")
            return 0

        do_poll()
        return 0

    route_table: dict[str, tuple[str, str, bool]] = {
        "refresh-containers": ("POST", "/refresh_containers", False),
        "start-experiment": ("POST", "/initialize_controller", True),
        "stop-experiment": ("POST", "/stop_controller", False),
        "attach-controller": ("POST", "/attach_controller", False),
        "start-traffic": ("POST", "/launch_traffic", True),
        "stop-traffic": ("POST", "/stop_traffic", False),
        "check-traffic": ("POST", "/check_traffic", False),
        "start-services": ("POST", "/start_services", False),
        "stop-services": ("POST", "/stop_services", False),
        "start-zookeeper": ("POST", "/start_zookeeper", False),
        "stop-zookeeper": ("POST", "/stop_zookeeper", False),
        "start-kafka": ("POST", "/start_kafka", False),
        "stop-kafka": ("POST", "/stop_kafka", False),
        "start-prometheus": ("POST", "/start_prometheus", False),
        "stop-prometheus": ("POST", "/stop_prometheus", False),
        "start-grafana": ("POST", "/start_grafana", False),
        "stop-grafana": ("POST", "/stop_grafana", False),
        "open-grafana": ("GET", "/open_grafana", False),
    }

    if args.command in route_table:
        method, path, use_config = route_table[args.command]
        payload = {"config_from_frontend": state} if use_config else None
        result = client.http(method, path, json_payload=payload)
        pretty_print_result(result)
        return 0 if 200 <= result.status < 300 else 2

    if args.command == "start-traffic-single":
        payload = {
            "hostname": args.hostname,
            "config_from_frontend": state,
        }
        result = client.http("POST", "/launch_traffic_single", json_payload=payload)
        pretty_print_result(result)
        return 0 if 200 <= result.status < 300 else 2

    if args.command == "stop-traffic-single":
        payload = {
            "hostname": args.hostname,
            "origin": "MANUALLY",
        }
        result = client.http("POST", "/stop_traffic_single", json_payload=payload)
        pretty_print_result(result)
        return 0 if 200 <= result.status < 300 else 2

    print(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
