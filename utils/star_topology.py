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
from gns3util import *
import gns3fy as gfy
import logging
from omegaconf import DictConfig, OmegaConf 
import hydra
import subprocess
import re


PROJECT_NAME = None
ENV_STR = None
GNS3_HOST = None
GNS3_PORT = None

ATTACKER_NODE_COUNT = None
VICTIM_NODE_COUNT = None
ATTACKER_SERVER_COMMAND = 'python attacker_server.py'
HONEYPOT_SERVER_COMMAND = 'python honeypot_server.py'
ATTACH_CONTROLLER_COMMAND = 'ovs-vsctl set-controller br0 tcp:192.168.1.1:6633 & sh'
CONTROLLER_IMG_NAME = None
SWITCH_IMG_NAME = None
VICTIM_IMG_NAME = None
ATTACKER_IMG_NAME = None
NAT_IMG_NAME = "NAT"
CLOUD_IMG_NAME = "smartville-cloud-bridge"
CONTROLLER_START_COMMAND=None


node_ids = []
template_ids = {}
server = None
gns3_server_connector = None
project = None





def setup_gns3_bridge(cfg):
    bridge_name = "gns3-bridge"
    bridge_ip = cfg.topology_creator.bridge_ip
    
    # Check if bridge already exists
    try:
        # Check if interface exists
        subprocess.run(["ip", "link", "show", bridge_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Interface exists, check if it has the correct IP
        ip_output = subprocess.run(["ip", "addr", "show", bridge_name], check=True, stdout=subprocess.PIPE, text=True).stdout
        if re.search(rf"inet {re.escape(bridge_ip)}", ip_output):
            print(f"{bridge_name} already exists with correct IP configuration")
            return True
        
        # Interface exists but with wrong config - reconfigure it
        print(f"{bridge_name} exists but needs reconfiguration")
        subprocess.run(["sudo", "ip", "addr", "flush", "dev", bridge_name], check=True)
        subprocess.run(["sudo", "ip", "addr", "add", bridge_ip, "dev", bridge_name], check=True)
        subprocess.run(["sudo", "ip", "link", "set", bridge_name, "up"], check=True)
        print(f"Reconfigured {bridge_name} with {bridge_ip}")
        return True
        
    except subprocess.CalledProcessError:
        # Interface doesn't exist, create it
        try:
            subprocess.run(["sudo", "ip", "link", "add", "name", bridge_name, "type", "bridge"], check=True)
            subprocess.run(["sudo", "ip", "addr", "add", bridge_ip, "dev", bridge_name], check=True)
            subprocess.run(["sudo", "ip", "link", "set", bridge_name, "up"], check=True)
            print(f"Successfully created {bridge_name} with {bridge_ip}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to create {bridge_name}: {e}")
            return False
        

def resetProject(PROJECT_NAME):
    global project
    print(f"The {PROJECT_NAME} GNS3 project will be deleted if existent")
    delete_project(server,PROJECT_NAME)
    create_project(server,PROJECT_NAME,1000,1000)
    print(f"New GNS3 project created with name {PROJECT_NAME}")
    project = get_project_by_name(server, PROJECT_NAME)
    open_project_if_closed(server, project)


def generateIPList(ip_nr,network,netmask, starting_from=3):
    ip_pool = []
    for i in range(starting_from, ip_nr+starting_from):
        net_ip = network[:-1]
        ip = net_ip+str(i)+netmask
        ip_pool.append(ip)
        print("IP ADDED TO LIST: ",ip)
    return ip_pool


def mountSwitch(templates, curr_switch_label,ip=None,gateway=None):
    template_id = get_template_id_from_name(templates, SWITCH_IMG_NAME)
    control_interface = 'eth0'
    if ip is not None:
        switch1_node_name = curr_switch_label + "("+ ip +")"
    else:
        switch1_node_name = curr_switch_label


    openvswitch=create_node(server, project, 0, 100, template_id, switch1_node_name)
    print(f"{curr_switch_label}: created")
    openvswitch_id = openvswitch['node_id']
    
    if ip is not None:
        set_node_network_interfaces(server, project, openvswitch_id, control_interface, ipaddress.IPv4Interface(ip), gateway)
        print(f"{curr_switch_label}: assigned ip: {ip}, gateway: {gateway} on {control_interface}")
    else:
        openvswitch_id = openvswitch['node_id']
        set_dhcp_node_network_interfaces(server, project, openvswitch_id, control_interface, None)
        print(f"{curr_switch_label}: DHCP on ",control_interface)
    
    print(f"{curr_switch_label}: started")
    node_ids.append(openvswitch_id)
    return switch1_node_name


def mount_edge_switch(templates):
    """
    We did not add Gateways to node configuration in GNS3. If you need to do so, refer to the GNS3utils API.
    """
    template_id = get_template_id_from_name(templates, 'edge-'+SWITCH_IMG_NAME)
    curr_switch_label = "openvswitch-edge-1"
    edge_openvswitch=create_node(server, project, 0, -200, template_id,curr_switch_label)
    print(f"{curr_switch_label}: created")
    edge_openvswitch_id = edge_openvswitch['node_id']

    interface = 'eth1'
    set_dhcp_node_network_interfaces(server, project, edge_openvswitch_id, interface, None)
    print(f"{curr_switch_label}: DHCP on ",interface)

    node_ids.append(edge_openvswitch_id)
    print(f"{curr_switch_label}: started")
    return curr_switch_label


def mountController(templates, switch_name, ip=None):
    """
    We did not add Gateways to node configuration in GNS3. If you need to do so, refer to the GNS3utils API.
    """
    template_id = get_template_id_from_name(templates, CONTROLLER_IMG_NAME)
    if ip is not None:
        controller_name = CONTROLLER_IMG_NAME+"("+ip+")"
    else:
        controller_name = CONTROLLER_IMG_NAME

    openvswitch_id = get_node_id_by_name(server,project,switch_name)
    controller_id = get_node_id_by_name(server,project,controller_name)
    print(f"controller id {controller_id}, switch id {openvswitch_id}")
    if(controller_id is not None):
        delete_node(server,project,controller_id)
        print("Old controller node deleted")

    controller = create_node(server, project, 0, 0, template_id, controller_name)
    controller_id = controller['node_id']
    print(f"new {CONTROLLER_IMG_NAME} controller created ")
    time.sleep(2)

    if ip is not None:
        set_node_network_interfaces(server, project, controller_id, "eth0", ipaddress.IPv4Interface(ip), None)
        print(f"{CONTROLLER_IMG_NAME}: assigned ip: {ip} on eth0")
    else:
        set_dhcp_node_network_interfaces(server, project, controller_id, "eth0", None)
        print(f"{CONTROLLER_IMG_NAME}: DHCP on eth0")

    create_link(server, project, controller_id,0,openvswitch_id,0)
    print(f"Created a link from {CONTROLLER_IMG_NAME} to {switch_name} on port eth0")

    set_dhcp_node_network_interfaces(server,project,controller_id,"eth1", None)
    print(f"{CONTROLLER_IMG_NAME}: DHCP on eth1")

    node_ids.append(controller_id)
    print(f"{CONTROLLER_IMG_NAME}: started")
    return controller_name


def mountNAT(templates):    
    NAT_template_id = get_template_id_from_name(templates, NAT_IMG_NAME)
    print("NAT TEMPLATE ID: ",NAT_template_id)

    # Create a new node
    nat_node = gfy.Node(
        project_id=project.id, 
        connector=gns3_server_connector, 
        name=NAT_IMG_NAME, 
        template_id= NAT_template_id,
        x=0,
        y=-350)

    # Add the node to the project
    nat_node.create()
    print("NAT created")


def mountCloud(templates):    
    cloud_template_id = get_template_id_from_name(templates, CLOUD_IMG_NAME)
    print("CLOUD TEMPLATE ID: ",cloud_template_id)

    # Create a new node
    cloud_node = gfy.Node(
        project_id=project.id, 
        connector=gns3_server_connector, 
        name=CLOUD_IMG_NAME, 
        template_id= cloud_template_id,
        x=0,
        y=+350)

    # Add the node to the project
    cloud_node.create()

    print("Cloud created")


def mount_single_Host(templates, curr_img_name, curr_node_name,switch1_node_name,switch_port,ip,gateway,x,y):
    template_id = get_template_id_from_name(templates, curr_img_name)

    openvswitch_id = get_node_id_by_name(server,project,switch1_node_name)

    host=create_node(server, project, x, y, template_id,curr_node_name)
    host_id=host['node_id']
    print(f"{curr_node_name}: created")

    if ip is not None:
        set_node_network_interfaces(server, project, host_id, "eth0", ipaddress.IPv4Interface(ip), gateway)
        print(f"{curr_node_name}: assigned ip: {ip}, gateway: {gateway} on eth0")
    else:
        set_dhcp_node_network_interfaces(server,project,host_id,"eth0", None)

    set_dhcp_node_network_interfaces(server,project,host_id,"eth1", None)

    create_link(server, project,host_id,0,openvswitch_id,switch_port)
    print(f"{curr_node_name}: link to {switch1_node_name} on port {switch_port} created")

    node_ids.append(host_id)
    print(f"{curr_node_name}: started")


def mount_all_hosts(cfg, templates, switch_node_name, curr_node_count=2, fixed_ips=True):
    node_names = []
    # mounts hosts and links each one to a port of the switch
    gateway = None  
    switch_port = 3

    if fixed_ips:
        #generate pool of ip addresses for specified network (es. 192.168.1.0)
        network = cfg.topology_creator.subnet
        netmask = cfg.topology_creator.netmask
        ip_pool = generateIPList(ATTACKER_NODE_COUNT + VICTIM_NODE_COUNT, network, netmask, starting_from=curr_node_count+1)
    else:
        # ip_pool will be a list of Nones:
        ip_pool = [None] * (ATTACKER_NODE_COUNT + VICTIM_NODE_COUNT)

    x = 300
    y = -200
    i = 1
    half = False

    node_proto_names = [list(honeypot.keys())[0] 
                        for honeypot in cfg.honeypots]+ \
                        [list(attacker.keys())[0] 
                            for attacker in cfg.attackers]
    
    for idx, (ip, nodename) in enumerate(zip(ip_pool, node_proto_names)):

        if (i > (len(ip_pool))/2) and not half:
            half = True
            x = -300
            y = -200

        if idx > VICTIM_NODE_COUNT-1:
            img_name = ATTACKER_IMG_NAME
        else:
            img_name = VICTIM_IMG_NAME
        
        if ip is not None:
            curr_node_name = f'{nodename}({ip})'
        else:
            curr_node_name = nodename

        mount_single_Host(
            templates,
            img_name,
            curr_node_name,
            switch_node_name,
            switch_port,
            ip,
            gateway,
            x,
            y)
        
        i = i+1
        y = y+100
        switch_port = switch_port+1

        node_names.append(curr_node_name)
    
    return node_names


def connect_all(cfg, main_switch_node_name, edge_switch_node_name,controller_node_name,host_names, fixed_ips=True):

    nat_id = get_node_id_by_name(server, project, NAT_IMG_NAME)
    edge_switch_id = get_node_id_by_name(server, project, edge_switch_node_name)
    create_link(server, project,str(nat_id),0,str(edge_switch_id),1)

    controller_id = get_node_id_by_name(server, project, controller_node_name)
    create_link(server, project,str(edge_switch_id),2,str(controller_id),1)

    for idx, host_name in enumerate(host_names):
        host_id = get_node_id_by_name(server, project, host_name)
        create_link(server, project,str(edge_switch_id),3+idx,str(host_id),1)

    cloud_id = get_node_id_by_name(server, project, CLOUD_IMG_NAME)
    main_switch_id = get_node_id_by_name(server, project, main_switch_node_name)

    if fixed_ips:
        # interrupt execution, asking the user to place the correct bridge in the GNS3 GUI
        print("---------------------------------------------------------------------------------------")
        print("-------------------------IMPORTANT:----------------------------------------------------")
        print("---------------------------------------------------------------------------------------")
        print(f"Setting the gns3 bridge in you host, we might need root permissions!!!!")
        setup_gns3_bridge(cfg)

        print(f"Please locate the \"{CLOUD_IMG_NAME}\" node in your topology using the STANDALONE GNS3 GUI")
        print("and make sure to put the \"gns3-bridge\" in the first (or only) place in the interface list.")
        print("Then press ENTER to continue...")
        print("If you are using the GNS3 Web GUI, you might not found the \"gns3-bridge\" in the list of available interfaces.")
        input()
        create_link(server, project, str(cloud_id),0,str(main_switch_id),1)

    else:
        cloud_node = gfy.Node(node_id=str(cloud_id), connector=gns3_server_connector, project_id=project.id)
        cloud_node.get()
        portnames = [port['name'] for port in cloud_node.ports]
        # ask the user to select the correct port
        print("Please select the correct port for the cloud node:")
        for i, portname in enumerate(portnames):
            print(f"{i}: {portname}")
        port_index = int(input("Enter the index of the port: "))
        # check if the index is valid
        if port_index < 0 or port_index >= len(portnames):
            print("Invalid index. Exiting.")
            exit(1)
        
        create_link(server, project, str(cloud_id),0,str(main_switch_id),1, port_number_1=port_index)
        print(f"Created a link from {CLOUD_IMG_NAME} port  to {main_switch_node_name} on port eth0")


def start_all():
    for id in node_ids:
        start_node(server, project, id)
        print("Node: ",id," started")


def starTopology(cfg, templates):
    main_switch_node_name = mountSwitch(templates, "openvswitch-1", ip=cfg.topology_creator.main_switch_ip)
    edge_switch_node_name = mount_edge_switch(templates)
    controller_node_name = mountController(templates, main_switch_node_name, ip=cfg.topology_creator.controller_ip)
    host_names = mount_all_hosts(cfg, templates, main_switch_node_name)
    mountNAT(templates)
    mountCloud(templates)
    connect_all(cfg, main_switch_node_name, edge_switch_node_name,controller_node_name,host_names)
    start_all()


def update_generic_template(templates, img_name, start_command):
    global project

    template_id = get_template_id_from_name(templates, img_name)
    if(template_id is not None):  
        delete_template(server,project,template_id)
        print((f"{template_id}: deleting old template"))
        
    print((f"{template_id}: creating a new template using local image"))
    create_docker_template(server, img_name, start_command, str(img_name+":latest"), environment=ENV_STR)


def update_edge_switch_template(templates):
    global project

    switch_template_id = get_template_id_from_name(templates, 'edge-'+SWITCH_IMG_NAME)
    if(switch_template_id is not None):
        delete_template(server,project,switch_template_id)
        print((f"{SWITCH_IMG_NAME}: old switch template deleted"))
    print((f"{SWITCH_IMG_NAME}: creating a new template using local image"))
    network_adapters_count = 6 + VICTIM_NODE_COUNT + ATTACKER_NODE_COUNT
    create_docker_template_switch(server, 'edge-'+SWITCH_IMG_NAME, str(SWITCH_IMG_NAME+":latest"), adapter_count=network_adapters_count)


def update_main_switch_template(templates):
    global project

    switch_template_id = get_template_id_from_name(templates, SWITCH_IMG_NAME)
    if(switch_template_id is not None):
        delete_template(server,project,switch_template_id)
        print((f"{SWITCH_IMG_NAME}: old switch template deleted"))
    print((f"{SWITCH_IMG_NAME}: creating a new template using local image"))
    network_adapters_count = 6 + VICTIM_NODE_COUNT + ATTACKER_NODE_COUNT
    create_docker_template_switch(
        server, SWITCH_IMG_NAME, str(SWITCH_IMG_NAME+":latest"), adapter_count=network_adapters_count, start_command='')

def update_controller_template(args, templates):
    global project, ENV_STR

    controller_template_id = get_template_id_from_name(templates, CONTROLLER_IMG_NAME)
    if(controller_template_id is not None):
        delete_template(server,project,controller_template_id)
        print(f"old controller template {CONTROLLER_IMG_NAME} deleted")

    for key, value in args.get('switch_args').items():
        ENV_STR += f"{key}={value}\n"

    create_docker_template(server, CONTROLLER_IMG_NAME, CONTROLLER_START_COMMAND, str(CONTROLLER_IMG_NAME+":latest"),environment=ENV_STR)


def update_cloud_template(templates):
    global project

    cloud_template_id = get_template_id_from_name(templates, CLOUD_IMG_NAME)
    if(cloud_template_id is not None):
        delete_template(server,project,cloud_template_id)
        print(f"old controller template {CLOUD_IMG_NAME} deleted")

    create_cloud_template(server, CLOUD_IMG_NAME)


def update_templates(args, templates):
    update_cloud_template(templates)
    update_edge_switch_template(templates)
    update_main_switch_template(templates)
    update_controller_template(args, templates)
    update_generic_template(templates, ATTACKER_IMG_NAME, ATTACKER_SERVER_COMMAND)
    update_generic_template(templates, VICTIM_IMG_NAME, HONEYPOT_SERVER_COMMAND)






@hydra.main(config_path="../config", config_name="default", version_base="1.2")
def main(cfg: DictConfig) -> None:
    global PROJECT_NAME, GNS3_HOST, GNS3_PORT, GNS3_AUTH, GNS3_USERNAME, GNS3_PASSWORD
    global CONTROLLER_IMG_NAME, SWITCH_IMG_NAME, VICTIM_IMG_NAME, ATTACKER_IMG_NAME
    global CONTROLLER_START_COMMAND, ENV_STR, ATTACKER_NODE_COUNT, VICTIM_NODE_COUNT
    global gns3_server_connector, logger, server, project, node_ids, template_ids
    global ENV_STR
    logger = logging.getLogger("Topology Creator")
    logger.info("\nIMPORTANT: Parameters are read from the default.yaml file at the config dir. \n")
    if cfg.override != "":
        try:
            # Load the variant specified from the command line
            config_overrides = OmegaConf.load(hydra.utils.get_original_cwd() + f'/config/overrides/{cfg.override}.yaml')
            """           
            def is_dict_of_dicts(d):
                return isinstance(d, DictConfig) and all(isinstance(v, DictConfig) for v in d.values())

            # Merge configurations, with the variant overriding the base config
            # Replace specific top-level fields completely if present in override
            for k in config_overrides:
                if k in cfg and is_dict_of_dicts(cfg[k]) and is_dict_of_dicts(config_overrides[k]):
                    # Fully replace dict-of-dicts
                    cfg[k] = config_overrides[k]
                else:
                    # Let OmegaConf.merge handle it
                    cfg = OmegaConf.merge(cfg, OmegaConf.create({k: config_overrides[k]}))
            """
            cfg = OmegaConf.merge(cfg, config_overrides)
        except:
            logger.error('Unsuccesfully tried to use the configuration override: ',cfg.override)
            assert 1 == 0
    else:
    
        logger.info("            - You can ovverride them by using the command line: \n" +\
            "                python3 utils/star_topology.py --override=your_override.yaml \n" +\
            "              Where your override file should be in the config/overrides folder. \n")
   
    args = cfg.topology_creator

    PROJECT_NAME = args.project
    
    USE_GNS3_FILE = args.use_gns3_config_file
    GNS3_CONFIG_PATH = args.gns3_config_path

    CONTROLLER_IMG_NAME = args.controller_docker
    SWITCH_IMG_NAME = args.switch_docker
    VICTIM_IMG_NAME = args.victim_docker
    ATTACKER_IMG_NAME = args.attacker_docker
    CONTROLLER_START_COMMAND = args.contr_start
    ENV_STR = args.env_vars
    
    ATTACKER_NODE_COUNT = len(cfg.honeypots)
    VICTIM_NODE_COUNT = len(cfg.attackers)
    
    if USE_GNS3_FILE:
        server = Server(*read_local_gns3_config(GNS3_CONFIG_PATH))
        GNS3_HOST = server.addr
        GNS3_PORT = server.port
        GNS3_AUTH = server.auth
        GNS3_USERNAME = server.user
        GNS3_PASSWORD = server.password
    else:
        
        GNS3_HOST = args.gns3_host
        GNS3_PORT = args.gns3_port
        GNS3_AUTH = args.gns3_auth
        GNS3_USERNAME = args.gns3_username
        GNS3_PASSWORD = args.gns3_password    
        server = Server(GNS3_HOST, GNS3_PORT, GNS3_AUTH, GNS3_USERNAME, GNS3_PASSWORD)


    gns3_server_connector = gfy.Gns3Connector(f"http://{GNS3_HOST}:{GNS3_PORT}", user=GNS3_USERNAME, cred=GNS3_PASSWORD)

    resetProject(PROJECT_NAME)
    
    templates = get_all_templates(server)
    update_templates(args, templates)
    templates = get_all_templates(server)

    

    starTopology(cfg, templates)


if __name__ == "__main__":
    
    main()