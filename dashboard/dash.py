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
import threading
import time
import subprocess
from functools import reduce
import random
from omegaconf import DictConfig, OmegaConf 
import hydra
import json
import requests
from flask import Flask, render_template
import os

containers_dict = {}
containers_ips = {}
TERMINAL_ISSUER_PATH = None

start_zookeeper_command = "zookeeper-server-start.sh pox/smartController/zookeeper.properties"
start_kafka_command = "kafka-server-start.sh pox/smartController/kafka_server.properties"
start_prometheus_command = "prometheus --config.file=pox/smartController/prometheus.yml --storage.tsdb.path=pox/smartController/PrometheusLogs/"
start_grafana_command = "grafana-server -homepath /usr/share/grafana"
start_training_command = "./pox.py samples.pretty_log smartController.smartController"


# Function to continuously print output of a command
def print_output(container, command, thread_name):
    # Execute the command in the container and stream the output
    return_tuple = container.exec_run(command, stream=True, tty=True, stdin=True)
    for line in return_tuple[1]:
        print(thread_name+": "+line.decode().strip())  # Print the output line by line


def launch_detached_command(command):
    # Run the command on a new pseudo TTY
    try:
        # Run the command and capture the output
        output = subprocess.check_output(command, stderr=subprocess.STDOUT)
        print(output.decode('utf-8'))  # Decode the output bytes to UTF-8 and print it
    except subprocess.CalledProcessError as e:
        # Handle errors if the command exits with a non-zero status
        print("Error:", e)


def launch_prometheus(controller_container):
    print(run_command_in_container(controller_container, "python3 pox/smartController/set_prometheus.py"))
    time.sleep(1)
    output_thread = threading.Thread(
        target=print_output, 
        args=(controller_container, start_prometheus_command, 'PROMETHEUS'))
    output_thread.start()


def launch_prometheus_detached(controller_container):
    # Build the command to execute your Bash script with its arguments
    command = [TERMINAL_ISSUER_PATH, f"{controller_container.id}:PROMETHEUS:{start_prometheus_command}"]
    launch_detached_command(command)


def launch_grafana(controller_container):
    output_thread = threading.Thread(
        target=print_output, 
        args=(controller_container, start_grafana_command, 'GRAFANA'))
    output_thread.start()


def launch_grafana_detached(controller_container):
    # Build the command to execute your Bash script with its arguments
    command = [TERMINAL_ISSUER_PATH, f"{controller_container.id}:GRAFANA:{start_grafana_command}"]
    launch_detached_command(command)
    print('Waiting for Grafana to start...')
    time.sleep(10)
    # print('Linking Grafana to Prometheus...')
    # print(run_command_in_container(controller_container, "python3 pox/smartController/link_grafana_to_prometheus.py"))
    time.sleep(1)


def launch_zookeeper(controller_container):
    output_thread = threading.Thread(
        target=print_output, 
        args=(controller_container, start_zookeeper_command, 'ZOOKEEPER'))
    output_thread.start()


def launch_zookeeper_detached(controller_container):
    # Build the command to execute your Bash script with its arguments
    command = [TERMINAL_ISSUER_PATH, f"{controller_container.id}:ZOOKEEPER:{start_zookeeper_command}"]
    launch_detached_command(command)


def launch_kafka(controller_container):
    output_thread = threading.Thread(
        target=print_output, 
        args=(controller_container, start_kafka_command, 'KAFKA'))
    output_thread.start()


def launch_kafka_detached(controller_container):
    delete_kafka_logs(controller_container)
    time.sleep(2)
    delete_kafka_logs(controller_container)
    time.sleep(1)
    # Build the command to execute your Bash script with its arguments
    command = [TERMINAL_ISSUER_PATH, f"{controller_container.id}:KAFKA:{start_kafka_command}"]
    launch_detached_command(command)



def get_cmd_line_args(config_dict):
    args_str = ""
    for key, value in config_dict.items():
        args_str += f" --{key}={value}"
    return args_str



def delete_kafka_logs(controller_container):
    print('Deleting Kafka logs...')
    return run_command_in_container(
        controller_container, 
        "rm -rf /opt/kafka/logs")



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
    attacks = ['cc_heartbeat', 'generic_ddos', 'h_scan', 'hakai',  'torii', 'mirai', 'gafgyt', 'hajime', 'okiru', 'muhstik'] 
    benign_patterns =['echo', 'doorlock', 'hue']

    for honeypot_monodict in cfg.honeypots:
        honeypot_name = list(honeypot_monodict.keys())[0]
        honeypot_info = list(honeypot_monodict.values())[0]
        honeypot_info = dict(honeypot_info)
        honeypot_info['dest_ip'] = containers_ips[honeypot_info['destination']]
        if 'pattern' not in honeypot_info:
            honeypot_info['pattern'] = random.choice(benign_patterns)
        honeypot_monodict[honeypot_name] = honeypot_info

    for attacker_monodict in cfg.attackers:
        attacker_name = list(attacker_monodict.keys())[0]
        attacker_info = list(attacker_monodict.values())[0]
        attacker_info = dict(attacker_info)
        attacker_info['dest_ip'] = containers_ips[attacker_info['destination']]
        if 'pattern' not in attacker_info:
            attacker_info['pattern'] = random.choice(attacks)
        attacker_monodict[attacker_name] = attacker_info


def append_ips_to_no_proxy():
    no_proxy_ips = ','.join(containers_ips.values())
    os.environ['no_proxy'] = os.environ['no_proxy']+','+no_proxy_ips
    # get the current value of no_proxy
    current_no_proxy = subprocess.check_output("echo $no_proxy", shell=True).decode('utf-8').strip()
    # Print the current value of no_proxy
    print(f"Current no_proxy value: {current_no_proxy}")


@hydra.main(config_path="../config", config_name="default", version_base="1.2")
def main(cfg: DictConfig) -> None:
    global containers_dict, containers_ips, TERMINAL_ISSUER_PATH

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
    
    


    @app.route('/', methods=['GET'])
    def home():
        rendering_params = {'foo': 'bar'}
        # print current working directory
        print(f"Current working directory: {os.getcwd()}")
        return render_template('index.html', rendering_params=rendering_params)


    @app.route('/refresh_containers', methods=['POST'])
    def refresh_containers():
        global containers_dict
        global containers_ips
        # Connect to the Docker daemon
        client = docker.from_env()
        return_str = ""
        if len(client.containers.list()) == 0:
            return_str = "No containers are running!"
            return {'msg': return_str}
        for container in client.containers.list():

            container_info = client.api.inspect_container(container.id)
            
            container_img_name = container_info['Config']['Hostname']
            container_img_name = container_img_name.split('(')[0]            
            containers_dict[container_img_name] = container

            try:
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
                            break
                        # Look for inet pattern (newer ifconfig format)
                        elif 'inet ' in line and '127.0.0.1' not in line:
                            parts = line.strip().split()
                            for i, part in enumerate(parts):
                                if part == 'inet':
                                    # IP address is likely the next part
                                    if i + 1 < len(parts):
                                        ip_address = parts[i + 1].split('/')[0]
                                        break
                            if ip_address:
                                break
                    
                    container_ip = ip_address if ip_address else "IP not available"
                    return_str += f' {container_img_name} is alive with ip {ip_address} \n'
            except Exception as e:
                container_ip = "IP not available"
                return_str += f"Failed to get IP for {container_img_name}: {str(e)}\n"
        
           
            containers_ips[container_img_name] = container_ip 
        
        if cfg['base_params']['disable_proxy']:
            append_ips_to_no_proxy()
        return {'msg': return_str}
    

    @app.route('/launch_traffic', methods=['POST'])
    def launch_traffic():
        response_str = ""

        for attacker_monodict in cfg.attackers:
            attacker_name = list(attacker_monodict.keys())[0]
            traffic_info = list(attacker_monodict.values())[0]
            attacker_ip = containers_ips[attacker_name]
            traffic_info = dict(traffic_info) # Otherwise OmegaConfig won't support overwrites.
            response = requests.post(f"http://{attacker_ip}:8000/replay", json=traffic_info)
            response_str += f"Replay from {attacker_name} answered with status code: {response.status_code}\n"
            if response.json() is not None:
                response_str += f"message: {response.json()['message']}\n"


        for honeypot_monodict in cfg.honeypots:
            honeypot_name = list(honeypot_monodict.keys())[0]
            traffic_info = list(honeypot_monodict.values())[0]
            honeypot_ip = containers_ips[honeypot_name]
            traffic_info = dict(traffic_info)
            response = requests.post(f"http://{honeypot_ip}:8000/replay", json=traffic_info)
            response_str += f"Replay from {honeypot_name} answered with status code: {response.status_code}\n"
            if response.json() is not None:
                response_str += f"message: {response.json()['message']}\n"
        
        return response_str

    
    @app.route('/stop_traffic', methods=['POST'])
    def stop_traffic():

        response_str = ""

        for attacker_monodict in cfg.attackers:
            attacker_name = list(attacker_monodict.keys())[0]
            attacker_ip = containers_ips[attacker_name]
            response = requests.post(f"http://{attacker_ip}:8000/stop")
            response_str += f"Replay from {attacker_name} answered with status code: {response.status_code}\n"
            if response.json() is not None:
                response_str += f"message: {response.json()['message']}\n"


        for honeypot_monodict in cfg.honeypots:
            honeypot_name = list(honeypot_monodict.keys())[0]
            honeypot_ip = containers_ips[honeypot_name]
            response = requests.post(f"http://{honeypot_ip}:8000/stop")
            response_str += f"Replay from {honeypot_name} answered with status code: {response.status_code}\n"
            if response.json() is not None:
                response_str += f"message: {response.json()['message']}\n"
        
        return response_str

    
    @app.route('/check_traffic', methods=['POST'])
    def check_traffic():

        response_str = ""

        for attacker_monodict in cfg.attackers:
            attacker_name = list(attacker_monodict.keys())[0]
            attacker_ip = containers_ips[attacker_name]
            response = requests.get(f"http://{attacker_ip}:8000/replay_status")
            response_str += f"Replay from {attacker_name} answered with status code: {response.status_code}\n"
            if response.json() is not None:
                response_str += f"message: {response.json()['message']}\n"


        for honeypot_monodict in cfg.honeypots:
            honeypot_name = list(honeypot_monodict.keys())[0]
            honeypot_ip = containers_ips[honeypot_name]
            response = requests.get(f"http://{honeypot_ip}:8000/replay_status")
            response_str += f"Replay from {honeypot_name} answered with status code: {response.status_code}\n"
            if response.json() is not None:
                response_str += f"message: {response.json()['message']}\n"
        
        return response_str
    

    @app.route('/labels', methods=['GET'])
    def create_init_labels_dict():
        init_labels_dict = {}

        for honeypot_monodict in cfg.honeypots:
            honeypot_name = list(honeypot_monodict.keys())[0]
            honeypot_info = list(honeypot_monodict.values())[0]
            honeypot_pattern = honeypot_info['pattern']
            honeypot_ip = containers_ips[honeypot_name]
            init_labels_dict[honeypot_ip] = honeypot_pattern + ' (Benign)'

        for attacker_monodict in cfg.attackers:
            attacker_name = list(attacker_monodict.keys())[0]
            attacker_info = list(attacker_monodict.values())[0]
            attacker_pattern = attacker_info['pattern']
            attacker_ip = containers_ips[attacker_name]
            init_labels_dict[attacker_ip] = attacker_pattern

        return init_labels_dict


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


    @app.route('/initialize_controller', methods=['POST'])
    def initialize_controller():
        init_args = OmegaConf.to_container(cfg)
        init_args['container_ips'] = containers_ips
        del init_args['topology_creator']
        del init_args['base_params']
        rewards = reduce(lambda a, b: {**a, **b}, OmegaConf.to_container(cfg.rewards), {}).copy()
        del init_args['rewards']
        init_args['rewards'] = rewards

        response = requests.post(f"http://192.168.1.1:8000/initialize", json=init_args)
        app.logger.info(f"Replay from controller answered with status code: {response.status_code}")
        return response.json()


    @app.route('/attach_controller',  methods=['POST'])
    def  attach_controller():
        switch_container = containers_dict['openvswitch-1']
        controller_ip = containers_ips['pox-controller']
        attaching_command = f"ovs-vsctl set-controller br0 tcp:{controller_ip}:6633"
        
        exec_result = switch_container.exec_run(
                    f"sh -c '{attaching_command} & echo $!'", 
                    detach=True)
        if exec_result.exit_code == 0:
            return {'status_code':200, 'msg':'Switch and controller attached!'}
        else:
            return {'status_code':500, 'msg':'Error attaching the switch to the controller!'}


    @app.route('/start_training', methods=['POST'])
    def start_training(controller_container):

        training_args = get_cmd_line_args(cfg['intrusion_detection'])
        training_command = f"{start_training_command} {training_args}"
        print(f"Training command: {training_command}")
        print(f"Now launching training")
        command = [TERMINAL_ISSUER_PATH, f"{controller_container.id}:TRAINING:{training_command}"]
        launch_detached_command(command)



    @app.route('/launch_controller_processes', methods=['POST'])
    def launch_controller_processes(controller_container):
        launch_zookeeper_detached(controller_container)
        print('Zookeeper launched on controller! please wait...')
        time.sleep(1)
        launch_prometheus_detached(controller_container)
        print('Prometheus launched on controller! please wait...')
        time.sleep(1)
        launch_grafana_detached(controller_container)
        print('Grafana launched on controller! please wait...')
        time.sleep(1)
        launch_kafka_detached(controller_container)
        print('Kafka launched on controller! please wait...')
        time.sleep(1)
        print('Launching Grafanfa dashboard on host...')
        launch_browser_consoles(cfg, controller_container)

    refresh_containers() 
    init_traffic_stuff(cfg)

    # Run the Flask app
    app.run(host='0.0.0.0',port=cfg['base_params']['dashboard_port'])


if __name__ == "__main__":
    main()