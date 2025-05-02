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
import json
import random
import yaml
from omegaconf import DictConfig, OmegaConf 
import hydra
import json
import logging
from curricula import CLASS_LABELS, ZDA_LABELS, TEST_ZDA_LABELS
from flask import Flask, render_template, request



config_dict = {
    'base_params': {
        'container_manager_replay_from_file': True,
        'container_manager_curricula_from_file': True,
        'browser_path': '/usr/bin/firefox',
        'terminal_issuer_path': './terminal_issuer.sh'
    },
    'intrusion_detection': {
        'eval': False,
        'device': 'cpu',
        'seed': 777,
        'ai_debug': True,
        'multi_class': True,
        'use_packet_feats': True,
        'packet_buffer_len': 1,
        'flow_buff_len': 10,
        'node_features': False,
        'metric_buffer_len': 10,
        'inference_freq_secs': 60,
        'grafana_user': 'admin',
        'grafana_password': 'admin',
        'max_kafka_conn_retries': 5,
        'curriculum': 1,
        'wb_tracking': False,
        'wb_project_name': 'SmartVille',
        'wb_run_name': 'My new run',
        'FLOWSTATS_FREQ_SECS': 5,
        'flow_idle_timeout': 10,
        'arp_timeout': 120,
        'max_buffered_packets': 5,
        'max_buffering_secs' : 5,
        'arp_req_exp_secs': 4
    }
}

containers_dict = {}
containers_ips = {}
TRAFFIC_DICT ={}
TERMINAL_ISSUER_PATH = None

start_zookeeper_command = "zookeeper-server-start.sh pox/smartController/zookeeper.properties"
start_kafka_command = "kafka-server-start.sh pox/smartController/kafka_server.properties"
start_prometheus_command = "prometheus --config.file=pox/smartController/prometheus.yml --storage.tsdb.path=pox/smartController/PrometheusLogs/"
start_grafana_command = "grafana-server -homepath /usr/share/grafana"
start_training_command = "./pox.py samples.pretty_log smartController.smartController"


def read_config(file_path):
        
    try:
        # Read configuration from YAML file
        with open(file_path, 'r') as file:
            file_confg_dict = yaml.safe_load(file)
        
        # Update default configuration with values from the file
        if file_confg_dict:
            for key in config_dict.keys():
                if key in file_confg_dict:
                    config_dict[key].update(file_confg_dict[key])
        return config_dict

    except FileNotFoundError:
        print(f"Error: Configuration file '{file_path}' not found.")
        return config_dict

    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return config_dict


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


def start_training(controller_container):

    training_args = get_cmd_line_args(config_dict['intrusion_detection'])
    training_command = f"{start_training_command} {training_args}"
    print(f"Training command: {training_command}")
    print(f"Now launching training")
    command = [TERMINAL_ISSUER_PATH, f"{controller_container.id}:TRAINING:{training_command}"]
    launch_detached_command(command)


def launch_brower_consoles(controller_container):
    ifconfig_output = run_command_in_container(
        controller_container, 
        "ifconfig")
    accessible_ip = ifconfig_output.split('eth1')[1].split('inet ')[1].split(' ')[0]
    # url = "http://"+accessible_ip+":9090"  # Prometheus
    # subprocess.Popen([config_dict['base_params']['browser_path'], url])
    url = "http://"+accessible_ip+":3000"  # Grafana
    subprocess.Popen([config_dict['base_params']['browser_path'], url])
    time.sleep(5)
    print('\nBrowser launched, press enter to continue\n')

def delete_kafka_logs(controller_container):
    print('Deleting Kafka logs...')
    return run_command_in_container(
        controller_container, 
        "rm -rf /opt/kafka/logs")


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
    launch_brower_consoles(controller_container)


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


def launch_traffic_single(container_key, command_to_run):
    container_obj = containers_dict[container_key]
    pattern, target_ip = command_to_run.split(' ')[2:4]

    exec_result = container_obj.exec_run(
                f"sh -c '{command_to_run} & echo $!'", 
                detach=True)
    if exec_result.exit_code == 0:
        log_str = f"Started {pattern} traffic from {container_key} ({container_obj.name}) to {target_ip}"
        
    else:
        log_str = f"Failed to start pattern {pattern} in {container_key} ({container_obj.name}). Exit code: {exec_result.exit_code}"
        if exec_result.output:
            print(f"Error output: {exec_result.output.decode('utf-8')}")
    
    print(log_str)
    return log_str


def init_traffic_stuff():
    global TRAFFIC_DICT
    from_file = config_dict['base_params']['container_manager_replay_from_file']  
    if from_file:
        print('traffic will be replayed from file')
        # Read dictionary from a file in JSON format
        # Modify this file to adjust it to your topology and desired pattern replay dynamics.
        with open('../utils/preset_traffic.json', 'r') as file:
            TRAFFIC_DICT = json.load(file)
    else: 
        attacks = ['cc_heartbeat', 'generic_ddos', 'h_scan', 'hakai',  'torii', 'mirai', 'gafgyt', 'hajime', 'okiru', 'muhstik'] 
        benign_patterns =['echo', 'doorlock', 'hue']
        victim_ips = [item[1] for item in containers_ips.items() if 'victim' in item[0]]

        for container_key in containers_dict:
            if 'attacker' in container_key:
                TRAFFIC_DICT[container_key] = f"python3 replay.py {random.choice(attacks)} {random.choice(victim_ips)} --repeat 10"
            elif 'victim' in container_key:
                des_ips = list(set(victim_ips)  - set([containers_ips[container_key]]))
                TRAFFIC_DICT[container_key] = f"python3 replay.py {random.choice(benign_patterns)} {random.choice(des_ips)} --repeat 10" 




@hydra.main(config_path="../config", config_name="default", version_base="1.2")
def main(cfg: DictConfig) -> None:
    global containers_dict, containers_ips, TRAFFIC_DICT, TERMINAL_ISSUER_PATH

    NAME = 'SmartVille'
    app = Flask(NAME)
    app.logger.name = NAME
    app.logger.setLevel('DEBUG')

    if cfg.override != "":
        try:
            # Load the variant specified from the command line
            config_overrides = OmegaConf.load(hydra.utils.get_original_cwd() + f'/config/overrides/{cfg.override}.yaml')
            # Merge configurations, with the variant overriding the base config
            cfg = OmegaConf.merge(cfg, config_overrides)
        except:
            app.logger.error('Unsuccesfully tried to use the configuration override: ',cfg.override)
            assert 1 == 0

    app.logger.info("\nIMPORTANT: Parameters are read from the default.yaml file at the config dir. \n" +\
        "            - You can ovverride them by using the command line: \n" +\
        "                python3 dash.py --override=your_override.yaml \n" +\
        "              Where your override file should be in the config/overrides folder. \n" +\
        "            - You might need to re-launch the app each time you restart your containers. \n\n\n")
   

    TERMINAL_ISSUER_PATH = cfg['base_params']['terminal_issuer_path'] 
    
    


    @app.route('/', methods=['GET'])
    def home():
        rendering_params = {'foo': 'bar'}
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
            # Extract the IP address of the container from its network settings
            container_info_str = container_info['Config']['Hostname']
            container_img_name = container_info_str.split('(')[0]
            container_ip = container_info_str.split('(')[-1][:-1].split('/')[0]
            # append sring to the return string
            return_str += f'{container_img_name} is {container.name} with ip {container_ip}\n'
            containers_dict[container_img_name] = container
            containers_ips[container_img_name] = container_ip 
        
        return {'msg': return_str}
    

    @app.route('/launch_traffic', methods=['POST'])
    def launch_traffic():
        response_str = ""
        args =[] 
        for container_key, container_obj in containers_dict.items():
            if 'attacker' in container_key or 'victim' in container_key:
                # Get the proper command
                command_to_run = TRAFFIC_DICT[container_key] 
                print(f"{container_key} ({container_obj.name}) will launch {command_to_run}")
                args.append(f"{container_obj.id}:{container_key}:{command_to_run}")
        print('Now launching traffic:')

        # Run the command from the SSH tunnel
        for args_line in args:
            container_key, command_to_run = args_line.split(':')[1:3]
            launch_traffic_single(container_key, command_to_run)
            response_str += args_line.split(':')[1] + ' ' + args_line.split(':')[2]  + "\n"
        return response_str

    
    @app.route('/stop_traffic', methods=['POST'])
    def stop_traffic():

        str_report = ""
        for container_key, container_obj in containers_dict.items():
            
            try:
                # Find and kill the Python process running the replay script
                exec_result = container_obj.exec_run(
                    cmd=['sh', '-c', "pkill -f 'python3 replay.py'"],
                    detach=True
                )
                str_report += f"Stopped eventual python3 replay.py process from {container_key}\n"
                print(f"Stopped eventual python3 replay.py process from {container_key}")
                
            except Exception as e:
                str_report += f"Error stopping pattern from {container_key}: {str(e)}\n"
                print(f"Error stopping pattern  from {container_key}: {str(e)}")
        
        return str_report
    

    @app.route('/fix_traffic', methods=['POST'])
    def fix_traffic(restart=False):
        """Verify if the pattern is actually running in the container"""
        
        str_report = ""

        for container_key, container_obj in containers_dict.items():
            if 'openvswitch' not in container_key and 'controller' not in container_key:
                # Find and kill the Python process running the replay script
                exec_result = container_obj.exec_run(
                    cmd=['sh', '-c', "pgrep -f 'python3 replay.py'"],
                    detach=False
                )
                answer = str(exec_result.output, 'utf-8').split('\n')
                if answer[1]  != '':
                # print(f"{container_key} ({container_obj.name}) is replaying traffic in process {answer[0]}")
                    print('')
                else:
                    str_report += f"{container_key} ({container_obj.name}) is not replaying any traffic!\n"
                    print(f"{container_key} ({container_obj.name}) is not replaying any traffic!\n")
                    if restart:
                        str_report += f"{container_key} ({container_obj.name}) will now restart its traffic!\n"
                        print('will now restart its traffic!')
                        launch_traffic_single(container_key, TRAFFIC_DICT[container_key])
        
        return str_report
    

    @app.route('/labels', methods=['GET'])
    def create_init_labels_dict():
        init_labels_dict = {}
        for container_key, ip_addr in containers_ips.items():
            curr_label = ''
            if 'controller' not in container_key and 'switch' not in container_key:
                curr_label = TRAFFIC_DICT[container_key].split(' ')[2]
                if 'victim' in container_key:
                    curr_label += ' (Benign)'
                init_labels_dict[ip_addr] = curr_label
        return init_labels_dict


    @app.route('/flow_rewards', methods=['GET'])
    def get_flow_rewards():
        with open('../utils/flow_rewards_hard.json', 'r') as file:
            response_obj = json.load(file)
        return response_obj


    @app.route('/curricula', methods=['GET'])
    def get_curricula():
        curricula = {}

        from_file = cfg['base_params']['container_manager_curricula_from_file']  
        if from_file:
            print('curricula will be read from file')
            curricula['CLASS_LABELS'] =  CLASS_LABELS
            curricula['ZDA_LABELS'] = ZDA_LABELS
            curricula['TEST_ZDA_LABELS'] = TEST_ZDA_LABELS   
        else:
            print('Random curricula is not yet implemented!')
            assert 1 == 0
        return curricula


    @app.route('/attach_controller',  methods=['POST'])
    def  attach_controller():
        switch_container = containers_dict['openvswitch-1']
        attaching_command = "ovs-vsctl set-controller br0 tcp:192.168.1.1:6633"
        
        exec_result = switch_container.exec_run(
                    f"sh -c '{attaching_command} & echo $!'", 
                    detach=True)
        if exec_result.exit_code == 0:
            return 'Switch and controller attached!'
        else:
            return 'Error attaching the switch to the controller!'

    refresh_containers() 
    init_traffic_stuff()

    # Run the Flask app
    app.run() 


if __name__ == "__main__":
    main()