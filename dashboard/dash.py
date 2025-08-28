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

containers_dict = {}
containers_external_ips = {}
containers_internal_ips = {}
internal_ips_containers = {}
traffic_dict = {}

TERMINAL_ISSUER_PATH = None
internal_subnet = None
monitoring_services_lock = Lock()
ms_healthcheck_thread = None
stop_services_function = None
HEALTH_MONITORING = None
KAFKA_PORT = None

def launch_metrics():
    for container_name, container_obj in containers_dict.items():
        if container_name.startswith('victim'):
            # Build the command to execute your Bash script with its arguments
            command = [TERMINAL_ISSUER_PATH, f"{container_obj.id}:{container_name}-METRICS:python3 producer.py"]
            launch_detached_command(command)


def run_command_in_container(container, command):
    # Run the command in the container shell to obtain the PID
    exec_result = container.exec_run(f"sh -c '{command} & echo $!'")
    pid = exec_result.output.decode("utf-8").strip()
    return pid


def launch_traffic_single(target_ip, command_to_run):
    # send a get request to target_ip port 8000
    response = requests.get(f"http://{target_ip}:8000")
    if response.status_code == 200:
        result = f"GET request to {target_ip} was successful."
    else:
        result = f"GET request to {target_ip} failed with status code: {response.status_code}"

    return result


def launch_browser_consoles(cfg, controller_container):
        ifconfig_output = run_command_in_container(
            controller_container, 
            "ifconfig")
        accessible_ip = ifconfig_output.split('eth1')[1].split('inet ')[1].split(' ')[0]
        # url = "http://"+accessible_ip+":9090"  # Prometheus
        # subprocess.Popen([config_dict['base_params']['browser_path'], url])
        url = "http://"+accessible_ip+":3000"  # Grafana
        subprocess.Popen([cfg['base_params']['browser_path'], url])
        time.sleep(5)
        print('\nBrowser launched, press enter to continue\n')


def init_traffic_stuff(cfg):
    global traffic_dict

    honeypots_dict = OmegaConf.to_container(cfg.honeypots, resolve=True)
    attackers_dict = OmegaConf.to_container(cfg.attackers, resolve=True)

    for honeypot_name, honeypot_info in honeypots_dict.items():
        honeypot_info['dest_ip'] = containers_internal_ips[honeypot_info['destination']]
        honeypot_info['src_ip'] = containers_internal_ips[honeypot_name]
        honeypot_info['benign'] = True
        honeypot_info['speed_multiplier'] = cfg.base_params.replay_speed
        if 'pattern' not in honeypot_info:
            honeypot_info['pattern'] = random.choice(cfg.knowledge.bening_patterns)
            

    for attacker_name, attacker_info in attackers_dict.items():
        attacker_info['dest_ip'] = containers_internal_ips[attacker_info['destination']]
        attacker_info['benign'] = False
        attacker_info['src_ip'] = containers_internal_ips[attacker_name]
        attacker_info['speed_multiplier'] = cfg.base_params.replay_speed
        if 'pattern' not in attacker_info:
            attacker_info['pattern'] = random.choice(cfg.knowledge.attack_patterns)
            

    # fuse the honeypots and attackers dict into a unique dict
    traffic_dict = {**honeypots_dict, **attackers_dict}
    
    # modify params for monitor ip:
    cfg.grafana.host = containers_external_ips['monitor']
    cfg.kafka.host = containers_external_ips['monitor']
    cfg.prometheus.serverhost = containers_external_ips['monitor']

def append_ips_to_no_proxy():
    no_proxy_ips = ','.join(containers_external_ips.values())
    os.environ['no_proxy'] = os.environ['no_proxy']+','+no_proxy_ips
    # get the current value of no_proxy
    current_no_proxy = subprocess.check_output("echo $no_proxy", shell=True).decode('utf-8').strip()
    # Print the current value of no_proxy
    print(f"Current no_proxy value: {current_no_proxy}")


@hydra.main(config_path="../config", config_name="default", version_base="1.2")
def main(cfg: DictConfig) -> None:
    global containers_dict, containers_internal_ips, TERMINAL_ISSUER_PATH, internal_subnet
    global monitoring_services, stop_services_function, HEALTH_MONITORING, KAFKA_PORT

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
        except:
            app.logger.error('Unsuccesfully tried to use the configuration override: ',cfg.override)
            assert 1 == 0
    else:   
        
        app.logger.info("            - You can ovverride them by using the command line: \n" +\
            "                python3 dash.py --override=your_override.yaml \n" +\
            "              Where your override file should be in the config/overrides folder. \n" +\
            "            - You might need to re-launch the app each time you restart your containers. \n\n\n")
   

    TERMINAL_ISSUER_PATH = cfg['base_params']['terminal_issuer_path'] 
    HEALTH_MONITORING = cfg.intrusion_detection.node_features
    if HEALTH_MONITORING:
        try:
            KAFKA_PORT = int(cfg.kafka.port) 
        except (ValueError, IndexError):
            app.logger.error('Error parsing Kafka port from the configuration file."')
            assert 1 == 0

    # transform cfg.attackers, which is  a list of dicts, into a dict of dicts. the key's of the outer dict should be the unique key of the inner dict
    # the value of the outer dict should be the inner dict
    cfg.attackers = {list(attacker.keys())[0]: attacker[list(attacker.keys())[0]] for attacker in cfg.attackers}
    cfg.honeypots = {list(honeypot.keys())[0]: honeypot[list(honeypot.keys())[0]] for honeypot in cfg.honeypots}
    internal_subnet = cfg.topology_creator.subnet+cfg.topology_creator.netmask


    @app.route('/', methods=['GET'])
    def home():
        rendering_params = {'traffic_buttons': []}
        # print current working directory
        print(f"Current working directory: {os.getcwd()}")
        for hostname, host_info in traffic_dict.items():
            rendering_params["traffic_buttons"].append(hostname)
        return render_template('index.html', rendering_params=rendering_params)


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
            container_name = container_name.split('(')[0] 
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
            

        if cfg['base_params']['disable_proxy']:
            append_ips_to_no_proxy()
        return {'msg': return_str}
    

    @app.route('/launch_traffic', methods=['POST'])
    def launch_traffic():
        global HEALTH_MONITORING, KAFKA_PORT
        
        response_str = ""
        for hostname, host_info in traffic_dict.items():
            node_external_ip = containers_external_ips[hostname]
            host_info['node_features'] = HEALTH_MONITORING
            host_info['kafka_endpoint'] = containers_internal_ips['pox-controller']+":"+str(KAFKA_PORT)
            host_info['health_params'] = cfg.health
            response = requests.post(f"http://{node_external_ip}:8000/replay", json=host_info)
            if response.json() is not None:
                response_str += f"{hostname}:{response.status_code} - {response.json()['message']}\n"

        
        return response_str


    @app.post('/launch_traffic_single')
    def launch_traffic_single():
        global HEALTH_MONITORING, KAFKA_PORT

        hostname = request.json['hostname'].split('_')[0]
        node_external_ip = containers_external_ips[hostname]
        host_info = traffic_dict[hostname]
        host_info['node_features'] = HEALTH_MONITORING
        host_info['kafka_endpoint'] = containers_internal_ips['pox-controller']+":"+str(KAFKA_PORT)
        host_info['health_params'] = OmegaConf.to_container(cfg.health, resolve=True)
        response = requests.post(f"http://{node_external_ip}:8000/replay", json=host_info)
        return f"{hostname}:{response.status_code} - {response.json()['message']}"


    @app.route('/stop_traffic', methods=['POST'])
    def stop_traffic():

        response_str = ""

        for hostname, host_info in traffic_dict.items():
            node_external_ip = containers_external_ips[hostname]
            response = requests.post(f"http://{node_external_ip}:8000/stop")
            if response.json() is not None:
                response_str += f"{hostname}:({response.status_code}) {response.json()['message']}\n"
        
        return response_str


    @app.post('/stop_traffic_single')
    def stop_traffic_single():
        hostname = request.json['hostname'].split('_')[0]
        node_external_ip = containers_external_ips[hostname]
        response = requests.post(f"http://{node_external_ip}:8000/stop")
        return f"{hostname}:({response.status_code}) {response.json()['message']}"
    

    @app.route('/check_traffic', methods=['POST'])
    def check_traffic():

        response_str = ""

        for hostname, host_info in traffic_dict.items():
            node_external_ip = containers_external_ips[hostname]
            response = requests.get(f"http://{node_external_ip}:8000/replay_status")
            if response.json() is not None:
                response_str += f"{hostname}: {response.json()['message']}\n"


        return response_str


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
        response = requests.post(f"http://{monitor_external_ip}:8000/start_zookeeper", json=zookeeper_args)
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
        response = requests.post(f"http://{monitor_external_ip}:8000/start_kafka", json=kafka_args)
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
        response = requests.post(f"http://{monitor_external_ip}:8000/start_prometheus", json=prometheus_args)
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
        response = requests.post(f"http://{monitor_external_ip}:8000/start_grafana", json=grafana_args)
        app.logger.debug(f"Grafana start answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    

    @app.post('/stop_zookeeper')  
    def stop_zookeeper():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:8000/stop_zookeeper")
        app.logger.info(f"Zookeeper stop answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    

    @app.post('/stop_kafka')
    def stop_kafka():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:8000/stop_kafka")
        app.logger.info(f"Kafka stop answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )


    @app.post('/stop_prometheus')
    def stop_prometheus():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:8000/stop_prometheus")
        app.logger.info(f"Prometheus stop answered with status code: {response.status_code}")
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    

    @app.post('/stop_grafana')
    def stop_grafana():
        monitor_external_ip = containers_external_ips['monitor']
        response = requests.post(f"http://{monitor_external_ip}:8000/stop_grafana")
        app.logger.info(f"Grafana stop answered with status code: {response.status_code}")
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
            

            return {"msg": response_message, "status_code": 200}
    
    stop_services_function = stop_services

    @app.route('/initialize_controller', methods=['POST'])
    def initialize_controller():
        init_args = OmegaConf.to_container(cfg, resolve=True)
        init_args['container_ips'] = containers_internal_ips
        init_args['ips_containers'] = internal_ips_containers
        del init_args['topology_creator']
        del init_args['base_params']
        del init_args['honeypots']
        del init_args['attackers']
        init_args['traffic_dict'] = traffic_dict
        rewards = reduce(lambda a, b: {**a, **b}, OmegaConf.to_container(cfg.rewards, resolve=True), {}).copy()
        del init_args['rewards']
        init_args['rewards'] = rewards
        init_args['monitor_ip'] = containers_external_ips['monitor']
        controller_external_ip = containers_external_ips['pox-controller']
        response = requests.post(f"http://{controller_external_ip}:8000/initialize", json=init_args)
        app.logger.info(f"Replay from controller answered with status code: {response.status_code}")
        return response.json()


    @app.route('/stop_controller', methods=['POST'])
    def stop_controller():
        controller_external_ip = containers_external_ips['pox-controller']
        response = requests.post(f"http://{controller_external_ip}:8000/stop")
        response = response.json()
        app.logger.info(f"Replay from controller answered with status code: {response['status_code']}")
        return response

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
                    response = requests.get(f"http://{monitor_external_ip}:8000/check_zookeeper")
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
                    response = requests.get(f"http://{monitor_external_ip}:8000/check_kafka")
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
            with monitoring_services_lock:
                if monitoring_services:
                    response = requests.get(f"http://{monitor_external_ip}:8000/check_grafana")
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
                    response = requests.get(f"http://{monitor_external_ip}:8000/check_prometheus")
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

            time.sleep(5)

        app.logger.debug(f"Monitoring services stopped")
        
            

    refresh_containers() 
    init_traffic_stuff(cfg)
    attach_controller()    

    # Run the Flask app
    app.run(host='0.0.0.0',port=cfg['base_params']['dashboard_port'])


def cleanup():
    global ms_healthcheck_thread, monitoring_services
    print("Cleaning up before exit")
    if ms_healthcheck_thread is not None:
        with monitoring_services_lock:
            monitoring_services = False
            print("Stopping monitoring services...")
            stop_services_function()
        ms_healthcheck_thread.join()


def handle_sigterm(signum, frame):
      cleanup()
      os._exit(0)

if __name__ == "__main__":
    main()

    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)