# This file is part of the "Smartville" project.
# Copyright (c) 2024 University of Insubria
# Licensed under the Apache License 2.0.
# SPDX-License-Identifier: Apache-2.0
# For the full text of the license, visit:
# https://www.apache.org/licenses/LICENSE-2.0

# Smartville is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# Apache License 2.0 for more details.

# You should have received a copy of the Apache License 2.0
# along with Smartville. If not, see <https://www.apache.org/licenses/LICENSE-2.0>.

# Additional licensing information for third-party dependencies
# used in this file can be found in the accompanying `NOTICE` file.
import docker
import time
import subprocess
from functools import reduce
import random
from omegaconf import DictConfig, OmegaConf 
import hydra
import json
import requests
from flask import Flask, render_template, request, Response
import os
import ipaddress
import atexit
import signal
from threading import Lock, Thread 
from concurrent.futures import ThreadPoolExecutor, as_completed


containers_dict = {}
containers_external_ips = {}
containers_internal_ips = {}
internal_ips_containers = {}
traffic_dict = {}
labelled_traffic_dict = {}
internal_subnet = None
monitoring_services_lock = Lock()
ms_healthcheck_thread = None
stop_services_function = None
grafana_socat_proc = None

OmegaConf.register_new_resolver("len", lambda x: len(x))


def merge_dicts(d1: dict, d2: dict) -> dict:
        """
        Recursively merge two dictionaries.
        Values from d2 overwrite those from d1.
        """
        result = d1.copy()
        for k, v in d2.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = merge_dicts(result[k], v)
            else:
                result[k] = v
        return result


def _apply_speed_multiplier(host_info, raw_value):
    """
    Overlay a frontend-supplied speed multiplier onto a node's host_info,
    mutating it in place before it is POSTed to the node's /replay endpoint.
    Ignores None/blank/invalid values (leaving the node's configured
    multiplier untouched). The value is passed straight through to
    `tcpreplay -x <multiplier>` (see attacker_server.py/honeypot_server.py),
    which accepts fractional multipliers (e.g. 0.001 to replay at 1/1000th
    speed) as well as integers/large values -- so this stays a float, only
    floored just above 0 to rule out a 0x/negative multiplier that would
    stall or break the replay.
    """
    if raw_value is None or raw_value == "":
        return
    try:
        speed = float(raw_value)
    except (TypeError, ValueError):
        return
    host_info['speed_multiplier'] = max(1e-6, speed)


def init_traffic_stuff(cfg):
    global traffic_dict, labelled_traffic_dict

    honeypots_dict = OmegaConf.to_container(cfg.honeypots, resolve=True)
    attackers_dict = OmegaConf.to_container(cfg.attackers, resolve=True)
            

    for attacker_name, attacker_info in attackers_dict.items():
        attacker_info['dest_ip'] = containers_internal_ips[attacker_info['destination']]
        attacker_info['src_ip'] = containers_internal_ips[attacker_name]
        if 'pattern' not in attacker_info:
            attacker_info['pattern'] = random.choice(cfg.knowledge.attack_patterns + cfg.knowledge.bening_patterns)
        attacker_info['benign'] = attacker_info['pattern'] in cfg.knowledge.bening_patterns


    for honeypot_name, honeypot_info in honeypots_dict.items():
        if honeypot_info:
            if 'destination' in honeypot_info:
                assert honeypot_info['destination'] not in attackers_dict.keys(), \
                    f"Honeypot {honeypot_name} has destination {honeypot_info['destination']}, which is an attacker! "+ \
                    "A honeypot destination of a honeypot cannot be an attacker!"
                honeypot_info['dest_ip'] = containers_internal_ips[honeypot_info['destination']]
                honeypot_info['src_ip'] = containers_internal_ips[honeypot_name]
                honeypot_info['benign'] = True
                if 'pattern' not in honeypot_info:
                    honeypot_info['pattern'] = random.choice(cfg.knowledge.bening_patterns)

    # fuse the honeypots and attackers dict into a unique dict
    traffic_dict = {**honeypots_dict, **attackers_dict}

    mockserver_url = (containers_internal_ips['mockserver'] + ':' + str(cfg.topology_creator.mockserver.SERVER_PORT))
    internal_ips_str = ','.join(containers_internal_ips['all'])
    monitor_external_ip = containers_external_ips['monitor']
    for node_name, node_info in traffic_dict.items():
        node_info['kafka_endpoint'] = monitor_external_ip + ':' + str(cfg.kafka.port)
        node_info['health_params'] = OmegaConf.to_container(cfg.health, resolve=True)
        node_info['mockserver_url'] = mockserver_url
        node_info['internal_ips'] = internal_ips_str


    labelled_traffic_dict = attackers_dict
    
    # modify params for monitor ip:
    cfg.grafana.host = '0.0.0.0'
    cfg.kafka.host = containers_external_ips['monitor']
    cfg.prometheus.serverhost = containers_external_ips['monitor']
    cfg.prometheus.clienthost = containers_external_ips['pox-controller']


def append_ips_to_no_proxy():
    no_proxy_ips = ','.join(containers_external_ips.values())
    os.environ['no_proxy'] = os.environ['no_proxy']+','+no_proxy_ips
    # get the current value of no_proxy
    current_no_proxy = subprocess.check_output("echo $no_proxy", shell=True).decode('utf-8').strip()
    # Print the current value of no_proxy
    print(f"Current no_proxy value: {current_no_proxy}")


def kill_socat_grafana():
    global grafana_socat_proc

    if grafana_socat_proc is not None:
        grafana_socat_proc.terminate()
        try:
            grafana_socat_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            grafana_socat_proc.kill()
        finally:
            grafana_socat_proc = None


def socat_grafana(cfg, logger):
        global grafana_socat_proc

        if grafana_socat_proc is not None:
            kill_socat_grafana()

        monitor_external_ip = containers_external_ips['monitor']
        grafana_port = cfg.grafana.port
        socat_cmd = [
            "socat",
            f"TCP-LISTEN:{grafana_port},reuseaddr,fork",
            f"TCP:{monitor_external_ip}:{grafana_port}"
        ]
        
        # Start socat in the background
        grafana_socat_proc = subprocess.Popen(socat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Grafana should be accessible at http://localhost:{grafana_port}")


@hydra.main(config_path="../config", config_name="default", version_base="1.2")
def main(cfg: DictConfig) -> None:
    global containers_dict, containers_internal_ips, internal_subnet
    global monitoring_services, stop_services_function

    NAME = 'SmartVille'
    app = Flask(NAME)
    app.logger.name = NAME
    app.logger.setLevel('DEBUG')
    app.logger.info("IMPORTANT: Parameters are read from the default.yaml file at the config dir." )
    if cfg.override != "":
        try:
            # Load the variant specified from the command line
            config_overrides = OmegaConf.load(f'../config/overrides/{cfg.override}.yaml')
            # Merge configurations, with the variant overriding the base config
            cfg = OmegaConf.merge(cfg, config_overrides)
            app.logger.info(f'Using the configuration override: {cfg.override}')
        except:
            app.logger.error('Unsuccesfully tried to use the configuration override: {cfg.override}')
            assert 1 == 0
    else:   
        
        app.logger.info("            - You can ovverride them by using the command line: \n" +\
            "                python3 dash.py --override=your_override.yaml \n" +\
            "              Where your override file should be in the config/overrides folder. \n" +\
            "            - You might need to re-launch the app each time you restart your containers. \n\n\n")
   

    # transform cfg.attackers, which is  a list of dicts, into a dict of dicts. the key's of the outer dict should be the unique key of the inner dict
    # the value of the outer dict should be the inner dict
    cfg.attackers = {list(attacker.keys())[0]: attacker[list(attacker.keys())[0]] for attacker in cfg.attackers}
    cfg.honeypots = {list(honeypot.keys())[0]: honeypot[list(honeypot.keys())[0]] for honeypot in cfg.honeypots}
    internal_subnet = cfg.topology_creator.subnet+cfg.topology_creator.netmask


    @app.route('/', methods=['GET'])
    def home():
        rendering_params = OmegaConf.to_container(cfg, resolve=True)
        # print current working directory
        print(f"Current working directory: {os.getcwd()}")
        rendering_params['traffic_buttons'] = []
        # Per-node default speed multiplier for the traffic-speed knobs. Some
        # config entries carry a typo'd 'speed_multiplierd' key and thus no
        # real multiplier; fall back to 1 so the knob always shows a value.
        # Kept as a float (not int) since tcpreplay -x accepts fractional
        # multipliers (e.g. 0.001) as well as integers.
        rendering_params['traffic_speeds'] = {}
        for hostname, host_info in traffic_dict.items():
            rendering_params["traffic_buttons"].append(hostname)
            rendering_params["traffic_speeds"][hostname] = float(host_info.get('speed_multiplier') or 1)
        return render_template('index.html', rendering_params=rendering_params)


    @app.route('/create_topology', methods=['POST'])
    def create_topology():
        data = request.get_json(force=True)['config']
        return "This function will be implemented in the future! \n" + \
            "For now, please build your topology using the utils/star_topology script and the config files!"

    @app.route('/refresh_containers', methods=['POST'])
    def refresh_containers():
        global containers_dict, internal_subnet
        global containers_internal_ips, internal_ips_containers, containers_external_ips


        # Connect to the Docker daemon
        client = docker.from_env()
        return_str = ""
        if len(client.containers.list()) == 0:
            return_str = "No containers are running!"
            return {'msg': return_str}
        for container in client.containers.list():

            container_info = client.api.inspect_container(container.id)
            img_name = container_info['Config']['Image']
            container_name = container_info['Config']['Hostname']
            container_name = container_name.split('_')[0] 
            containers_dict[container_name] = container

            if img_name != 'openvswitch:latest':
                try:
                    return_str += f'{container_name}:\n'
                    exec_result = container.exec_run("ifconfig")
                    if exec_result.exit_code == 0:
                        cmd_output = exec_result.output.decode('utf-8')
                        # Extract IP address from ifconfig output using Python string operations
                        ip_address = None
                        for line in cmd_output.split('\n'):
                            # Look for inet addr: pattern (older ifconfig format)
                            if 'inet addr:' in line:
                                ip_part = line.split('inet addr:')[1].strip()
                                ip_address = ip_part.split()[0]
                            # Look for inet pattern (newer ifconfig format)
                            elif 'inet ' in line and '127.0.0.1' not in line:
                                parts = line.strip().split()
                                for i, part in enumerate(parts):
                                    if part == 'inet':
                                        # IP address is likely the next part
                                        if i + 1 < len(parts):
                                            ip_address = parts[i + 1].split('/')[0]
                            
                            # verify if ip_adress is inside the internal subnet 
                            if ip_address is not None:
                                if  ipaddress.ip_address(ip_address) in ipaddress.ip_network(internal_subnet, strict=False):
                                    containers_internal_ips[container_name] = ip_address 
                                    internal_ips_containers[ip_address] = container_name
                                    return_str += f' internal address: {ip_address} \n'
                                else:
                                    containers_external_ips[container_name] = ip_address
                                    return_str += f' external address: {ip_address} \n'
                            ip_address = None
                        
                except Exception as e:
                    return_str += f"Failed to get IP for {container_name}: {str(e)}\n"
            
        containers_internal_ips['all'] = [entry[1] for entry in containers_internal_ips.items() if entry[1] != '' and entry[0] != 'pox-controller']   
            

        if cfg['disable_proxy']:
            append_ips_to_no_proxy()
        return {'msg': return_str}
    

        
    @app.route('/launch_traffic', methods=['POST'])
    def launch_traffic():

        data = request.get_json(force=True)
        # Per-node speed multipliers set on the frontend knobs (may be absent
        # or partial); applied over each node's configured default below.
        speeds = data.get('speeds', {}) or {}

        def call_node(hostname, host_info):
            node_external_ip = containers_external_ips[hostname]

            host_info['health_monitoring'] = data['config_from_frontend']['health_monitoring']
            host_info['node_features'] = data['config_from_frontend']['node_features']
            host_info['health_params']['probe_metrics'] = [
                key for key, val in data['config_from_frontend']['health']['probe_metrics'].items() if val]
            _apply_speed_multiplier(host_info, speeds.get(hostname))
            port = (cfg.topology_creator.victim.SERVER_PORT
                        if hostname.startswith('victim')
                        else cfg.topology_creator.attacker.SERVER_PORT)
            try:
                response = requests.post(f"http://{node_external_ip}:{port}/replay", json=host_info)
                return hostname, response.status_code, response.json().get('message', '')
            except Exception as e:
                return hostname, 500, str(e)

        results = {}
        with ThreadPoolExecutor(max_workers=len(traffic_dict)) as executor:
            futures = {
                executor.submit(call_node, hostname, host_info): hostname
                for hostname, host_info in traffic_dict.items()
            }
            for future in as_completed(futures):
                hostname, status_code, message = future.result()
                results[hostname] = (status_code, message)

        # Build response string in a stable order
        response_str = "\n".join(
            f"{hostname}:{status_code} - {message}"
            for hostname, (status_code, message) in sorted(results.items())
        )

        return response_str


    @app.post('/launch_traffic_single')
    def launch_traffic_single():

        data = request.get_json(force=True)

        hostname = data['hostname'].split('_')[0]
        node_external_ip = containers_external_ips[hostname]
        host_info = traffic_dict[hostname]
        
        # update params from frontend configuration:
        host_info['health_monitoring'] = data['config_from_frontend']['health_monitoring']
        host_info['node_features'] = data['config_from_frontend']['node_features']
        host_info['health_params']['probe_metrics']  = [key for key, val in data['config_from_frontend']['health']['probe_metrics'].items() if val]
        _apply_speed_multiplier(host_info, data.get('speed_multiplier'))

        port = cfg.topology_creator.victim.SERVER_PORT if hostname.startswith('victim') else cfg.topology_creator.attacker.SERVER_PORT
        response = requests.post(f"http://{node_external_ip}:{port}/replay", json=host_info)
        return f"{hostname}:{response.status_code} - {response.json()['message']}"


    @app.route('/stop_traffic', methods=['POST'])
    def stop_traffic():

        def stop_node(hostname):
            node_external_ip = containers_external_ips[hostname]
            port = (
                cfg.topology_creator.victim.SERVER_PORT
                if hostname.startswith('victim')
                else cfg.topology_creator.attacker.SERVER_PORT
            )
            try:
                response = requests.post(f"http://{node_external_ip}:{port}/stop")
                return hostname, response.status_code, response.json().get('message', '')
            except Exception as e:
                return hostname, 500, str(e)

        results = {}
        with ThreadPoolExecutor(max_workers=len(traffic_dict)) as executor:
            futures = {
                executor.submit(stop_node, hostname): hostname
                for hostname in traffic_dict
            }
            for future in as_completed(futures):
                hostname, status_code, message = future.result()
                results[hostname] = (status_code, message)

        return "\n".join(
            f"{hostname}:({status_code}) {message}"
            for hostname, (status_code, message) in sorted(results.items())
        )


    @app.post('/stop_traffic_single')
    def stop_traffic_single():
        hostname = request.json['hostname'].split('_')[0]
        node_external_ip = containers_external_ips[hostname]
        port = cfg.topology_creator.victim.SERVER_PORT if hostname.startswith('victim') else cfg.topology_creator.attacker.SERVER_PORT
        response = requests.post(f"http://{node_external_ip}:{port}/stop")
        return f"{hostname}:({response.status_code}) {response.json()['message']}"
    

    @app.route('/check_traffic', methods=['POST'])
    def check_traffic():

        def check_node(hostname):
            node_external_ip = containers_external_ips[hostname]
            try:
                response = requests.get(f"http://{node_external_ip}:{cfg.topology_creator.controller.SERVER_PORT}/replay_status")
                return hostname, response.json().get('message', '')
            except Exception as e:
                return hostname, str(e)

        results = {}
        with ThreadPoolExecutor(max_workers=len(traffic_dict)) as executor:
            futures = {
                executor.submit(check_node, hostname): hostname
                for hostname in traffic_dict
            }
            for future in as_completed(futures):
                hostname, message = future.result()
                results[hostname] = message

        return "\n".join(
            f"{hostname}: {message}"
            for hostname, message in sorted(results.items())
        )


    @app.route('/flow_rewards', methods=['GET'])
    def get_flow_rewards():
        # merge all the entries in the cfg.rewards list into a unique dict:
        merged_rewards = {}
        for reward in cfg.rewards:
            for key, value in reward.items():
                if key not in merged_rewards:
                    merged_rewards[key] = value
                else:
                    merged_rewards[key] += value
        return merged_rewards

    @app.post('/start_zookeeper')
    def start_zookeeper():
        zookeeper_args = OmegaConf.to_container(cfg.zookeeper.config_file, resolve=True)
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/start_zookeeper", json=zookeeper_args)
        app.logger.debug(f"Zookeeper start answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    
    @app.post('/start_kafka')
    def start_kafka():
        kafka_args = OmegaConf.to_container(cfg.kafka.config_file, resolve=True)
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/start_kafka", json=kafka_args)
        app.logger.debug(f"Kafka start answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    
    @app.post('/start_prometheus')
    def start_prometheus():
        prometheus_args = OmegaConf.to_container(cfg.prometheus.config_file, resolve=True)
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/start_prometheus", json=prometheus_args)
        app.logger.debug(f"Prometheus start answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )

            
    @app.post('/start_grafana')
    def start_grafana():
        grafana_args = OmegaConf.to_container(cfg.grafana.config_file, resolve=True)
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/start_grafana", json=grafana_args)
        app.logger.debug(f"Grafana start answered with status code: {response.status_code}")
        if grafana_socat_proc is None:
            socat_grafana(cfg, app.logger)
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    

    @app.get('/open_grafana')
    def open_grafana():
        """
        This wont work if you're running the server on SSH....
        """
        monitor_external_ip = containers_external_ips['monitor']
        subprocess.Popen([
            cfg.browser_path,
            f"http://{monitor_external_ip}:{cfg.grafana.port}/"
        ])
        time.sleep(1)
        return "Grafana dashboard opened in browser."


    @app.post('/stop_zookeeper')  
    def stop_zookeeper():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/stop_zookeeper")
        app.logger.info(f"Zookeeper stop answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    

    @app.post('/stop_kafka')
    def stop_kafka():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/stop_kafka")
        app.logger.info(f"Kafka stop answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )


    @app.post('/stop_prometheus')
    def stop_prometheus():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/stop_prometheus")
        app.logger.info(f"Prometheus stop answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    

    @app.post('/stop_grafana')
    def stop_grafana():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/stop_grafana")
        app.logger.info(f"Grafana stop answered with status code: {response.status_code}")
        kill_socat_grafana()
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )   


    @app.route('/start_services', methods=['POST'])
    def start_services():
        global monitoring_services, monitoring_services_lock, ms_healthcheck_thread

        with monitoring_services_lock:
            monitoring_services = True
            
            zookeeper_ok = False
            kafka_ok = False
            prometheus_ok = False
            grafana_ok = False

            response_message = ""
            
            while not zookeeper_ok:
                zookeeper_response = start_zookeeper()
                zookeeper_ok = zookeeper_response.status_code == 200
                time.sleep(5)

            response_message += json.loads(zookeeper_response.data)['msg'] + "\n"

            while not kafka_ok:
                kafka_response = start_kafka()
                kafka_ok = kafka_response.status_code == 200
                time.sleep(3)

            response_message += json.loads(kafka_response.data)['msg'] + "\n"
            """
            while not prometheus_ok:
                prometheus_response = start_prometheus()
                prometheus_ok = prometheus_response.status_code == 200
                time.sleep(2)

            response_message += json.loads(prometheus_response.data)['msg'] + "\n"

            while not grafana_ok:
                grafana_response = start_grafana()
                grafana_ok = grafana_response.status_code == 200
                time.sleep(3)

            response_message += json.loads(grafana_response.data)['msg']
            """
            ms_healthcheck_thread = Thread(target=ms_health_thread_function, daemon=True)
            ms_healthcheck_thread.start()
            return {"msg": response_message, "status_code": 200}
    

    @app.route('/stop_services', methods=['POST'])
    def stop_services():
        global monitoring_services, monitoring_services_lock

        with monitoring_services_lock:
            monitoring_services = False
        
            zookeeper_ok = False
            kafka_ok = False
            prometheus_ok = False
            grafana_ok = False

            response_message = ""
            """
            while not grafana_ok:
                grafana_response = stop_grafana()
                grafana_ok = grafana_response.status_code in [200, 202]
                time.sleep(1)

            response_message += json.loads(grafana_response.data)['msg'] + "\n"

            while not prometheus_ok:
                prometheus_response = stop_prometheus()
                prometheus_ok = prometheus_response.status_code in [200, 202]
                time.sleep(1)

            response_message += json.loads(prometheus_response.data)['msg'] + "\n"
            """
            while not kafka_ok:
                kafka_response = stop_kafka()
                kafka_ok = kafka_response.status_code in [200, 202]
                time.sleep(1)

            response_message += json.loads(kafka_response.data)['msg'] + "\n"

            while not zookeeper_ok:
                zookeeper_response = stop_zookeeper()
                zookeeper_ok = zookeeper_response.status_code in [200, 202]
                time.sleep(1)

            response_message += json.loads(zookeeper_response.data)['msg'] + "\n"


            # Wipe Kafka data and Zookeeper state so the next experiment starts clean
            try:
                monitor_container = containers_dict['monitor']
                monitor_container.exec_run("rm -rf /tmp/kafka-logs")
                monitor_container.exec_run("rm -rf /tmp/zookeeper")
                response_message += "Kafka logs and Zookeeper state deleted.\n"
                app.logger.info("Sent command to wipe Kafka logs and Zookeeper state...")
            except KeyError:
                app.logger.warning("Monitor container not found in containers_dict — skipping Kafka log cleanup.")
                response_message += "Warning: could not delete Kafka logs (monitor container not found).\n"
            except Exception as e:
                app.logger.error(f"Error deleting Kafka logs: {e}")
                response_message += f"Warning: error deleting Kafka logs: {e}\n"
            

            return {"msg": response_message, "status_code": 200}
    
    stop_services_function = stop_services
    

    @app.route('/initialize_controller', methods=['POST'])
    def initialize_controller():
        global controller_init_args

        data = request.get_json(force=True)
        config_from_frontend = data['config_from_frontend']

        # pass log levels from frontend
        controller_init_args = merge_dicts(controller_init_args, config_from_frontend)
        # fix:
        controller_init_args['health']['probe_metrics']  = [key for key, val in config_from_frontend['health']['probe_metrics'].items() if val] 

        controller_external_ip = containers_external_ips['pox-controller']
        response = requests.post(f"http://{controller_external_ip}:{cfg.topology_creator.controller.SERVER_PORT}/initialize", json=controller_init_args)
        app.logger.info(f"Replay from controller answered with status code: {response.status_code}")
        # Forward the controller's real HTTP status, not a blanket 200: the
        # controller now returns proper error statuses on init failure, and
        # collapsing everything to 200 here would silently hide that from
        # any caller (CLI sweep scripts included) that checks HTTP status.
        return response.json(), response.status_code


    @app.route('/stop_controller', methods=['POST'])
    def stop_controller():
        controller_external_ip = containers_external_ips['pox-controller']
        response = requests.post(f"http://{controller_external_ip}:{cfg.topology_creator.controller.SERVER_PORT}/stop")
        response = response.json()
        app.logger.info(f"Replay from controller answered with status code: {response['status_code']}")
        return response


    @app.route('/controller_health', methods=['GET'])
    def controller_health():
        controller_external_ip = containers_external_ips['pox-controller']
        response = requests.get(f"http://{controller_external_ip}:{cfg.topology_creator.controller.SERVER_PORT}/health")
        return response.json(), response.status_code


    @app.route('/pending_packet_feats_stats', methods=['GET'])
    def pending_packet_feats_stats():
        """
        Proxy the controller's live pending_packet_feats utilisation to the
        dashboard's packet-queue gauges (polled every few seconds by dash.js).
        The controller may be unreachable (not started yet / between
        experiments); surface that as a normal payload with reachable=False so
        the gauges can show an idle state instead of the poll throwing.
        """
        try:
            controller_external_ip = containers_external_ips['pox-controller']
        except KeyError:
            return {"reachable": False, "initialized": False,
                    "msg": "pox-controller IP not known yet (refresh containers?)",
                    "classes": {}, "flows": []}
        try:
            response = requests.get(
                f"http://{controller_external_ip}:{cfg.topology_creator.controller.SERVER_PORT}/pending_packet_feats_stats",
                timeout=3)
            payload = response.json()
            payload["reachable"] = True
            return payload, response.status_code
        except Exception as e:
            return {"reachable": False, "initialized": False,
                    "msg": f"controller unreachable: {e}",
                    "classes": {}, "flows": []}


    @app.route('/attach_controller',  methods=['POST'])
    def  attach_controller():
        switch_container = containers_dict['openvswitch-1']
        controller_ip = containers_internal_ips['pox-controller']
        attaching_command = f"ovs-vsctl set-controller br0 tcp:{controller_ip}:6633"
        
        exec_result = switch_container.exec_run(
                    f"sh -c '{attaching_command} & echo $!'", 
                    detach=True)
        if exec_result.exit_code == 0:
            return {'status_code':200, 'msg':'Switch and controller attached!'}
        else:
            return {'status_code':500, 'msg':'Error attaching the switch to the controller!'}


    def ms_health_thread_function():
        global monitoring_services_lock, monitoring_services

        while monitoring_services:
            monitor_external_ip = containers_external_ips['monitor']
            with monitoring_services_lock:
                if monitoring_services:
                    response = requests.get(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/check_zookeeper")
                    response_content = json.loads(response.content)
                    if response.status_code == 200:
                        if not response_content['running']:
                            app.logger.debug(f"Zookeeper died with exitcode {response_content['last_exit_status']}. Now restarting...")
                            restart_response = start_zookeeper()
                            if restart_response.status_code == 200:
                                app.logger.debug(f"Zookeeper restarted")
                            else:
                                app.logger.error(f"Zookeeper restart failed with status code: {restart_response.status_code}")
                        else:
                            app.logger.debug(f"Zookeeper running healthy with pid: {response_content['pid']}")
                    else:
                        app.logger.error(f"Zookeeper check failed with status code: {response.status_code}")

            time.sleep(1)
            with monitoring_services_lock:
                if monitoring_services:
                    response = requests.get(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/check_kafka")
                    response_content = json.loads(response.content)
                    if response.status_code == 200:
                        if not response_content['running']:
                            app.logger.debug(f"Kafka died with exitcode {response_content['last_exit_status']}. Now restarting...")
                            restart_response = start_kafka()
                            if restart_response.status_code == 200:
                                app.logger.debug(f"Kafka restarted")
                            else:
                                app.logger.error(f"Kafka restart failed with status code: {restart_response.status_code}")
                        else:
                            app.logger.debug(f"Kafka running healthy with pid: {response_content['pid']}")
                    else:
                        app.logger.error(f"Kafka check failed with status code: {response.status_code}")

            time.sleep(1)
            """
            with monitoring_services_lock:
                if monitoring_services:
                    response = requests.get(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/check_grafana")
                    response_content = json.loads(response.content)
                    if response.status_code == 200:
                        if not response_content['running']:
                            app.logger.debug(f"Grafana died with exitcode {response_content['last_exit_status']}. Now restarting...")
                            restart_response = start_grafana()
                            if restart_response.status_code == 200:
                                app.logger.debug(f"Grafana restarted")
                            else:
                                app.logger.error(f"Grafana restart failed with status code: {restart_response.status_code}")
                        else:
                            app.logger.debug(f"Grafana running healthy with pid: {response_content['pid']}")
                    else:
                        app.logger.error(f"Grafana check failed with status code: {response.status_code}")

            time.sleep(1)
            with monitoring_services_lock:
                if monitoring_services:
                    response = requests.get(f"http://{monitor_external_ip}:{cfg.topology_creator.monitor.SERVER_PORT}/check_prometheus")
                    response_content = json.loads(response.content)
                    if response.status_code == 200:
                        if not response_content['running']:
                            app.logger.debug(f"Prometheus died with exitcode {response_content['last_exit_status']}. Now restarting...")
                            restart_response = start_prometheus()
                            if restart_response.status_code == 200:
                                app.logger.debug(f"Prometheus restarted")
                            else:
                                app.logger.error(f"Prometheus restart failed with status code: {restart_response.status_code}")
                        else:
                            app.logger.debug(f"Prometheus running healthy with pid: {response_content['pid']}")
                    else:
                        app.logger.error(f"Prometheus check failed with status code: {response.status_code}")
            """
            time.sleep(5)

        app.logger.debug(f"Monitoring services stopped")


    def init_controller_args():
        global controller_init_args
        controller_init_args = OmegaConf.to_container(cfg, resolve=True)
        del controller_init_args['rewards']
        rewards = reduce(lambda a, b: {**a, **b}, OmegaConf.to_container(cfg.rewards, resolve=True), {}).copy()
        controller_init_args['rewards'] = rewards
        controller_init_args['container_ips'] = containers_internal_ips
        controller_init_args['ips_containers'] = internal_ips_containers
        controller_init_args['traffic_dict'] = traffic_dict
        controller_init_args['monitor_ip'] = containers_external_ips['monitor']


    refresh_containers() 
    init_traffic_stuff(cfg)
    attach_controller()   
    init_controller_args() 

    # Run the Flask app
    app.run(host='0.0.0.0',port=cfg['dashboard_port'])



    

def cleanup():
    global ms_healthcheck_thread, monitoring_services
    print("Cleaning up before exit...")
    
    # 1. Kill the socat process immediately
    kill_socat_grafana()
    
    # 2. Set the flag to False so the thread loop breaks
    with monitoring_services_lock:
        monitoring_services = False
        
    """
    # 3. Call your stop services (ensure this has a timeout on its requests!)
    if stop_services_function:
        try:
            stop_services_function()
        except:
            pass
    """
    print("Forcing exit.")
    os._exit(0) # This will force the main process to die NOW


def handle_sigterm(signum, frame):
      cleanup()
      os._exit(0)


if __name__ == "__main__":
    # Register signals BEFORE running the app
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    try:
        main()
    except KeyboardInterrupt:
        cleanup()