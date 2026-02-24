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
ATTACKER_START_COMMAND = None
VICTIM_START_COMMAND = None
MONITOR_START_COMMAND = None
CONTROLLER_IMG_NAME = None
SWITCH_IMG_NAME = None
VICTIM_IMG_NAME = None
ATTACKER_IMG_NAME = None
ZOOKEEPER_IMG_NAME = None
KAFKA_IMG_NAME = None
GRAFANA_IMG_NAME = None
PROMETHEUS_IMG_NAME = None
MONITOR_IMG_NAME = None
MONITOR_HOSTNAME = None
NAT_IMG_NAME = "NAT"
CLOUD_IMG_NAME = "smartville-cloud-bridge"
CONTROLLER_START_COMMAND=None
ZOOKEEPER_START_COMMAND=''
KAFKA_START_COMMAND=''
GRAFANA_START_COMMAND=None
PROMETHEUS_START_COMMAND=''

node_ids = []
template_ids = {}
server = None
gns3_server_connector = None
project = None





def setup_gns3_bridge(cfg):
    bridge_name = "gns3-bridge"
    bridge_ip = cfg.topology_creator.bridge_ip+cfg.topology_creator.netmask
    
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


def mount_switch(templates, curr_switch_label,ip=None,gateway=None):
    template_id = get_template_id_from_name(templates, SWITCH_IMG_NAME)
    control_interface = 'eth0'
    if ip is not None:
        switch1_node_name = curr_switch_label + "\n"+ ip.split("/")[0]
    else:
        switch1_node_name = curr_switch_label

    try:
        openvswitch=create_node(server, project, 0, 100, template_id, switch1_node_name)
    except Exception as e:
        print(f"Error creating {curr_switch_label}: {e} Make sure you have built docker the images using make !")
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


def mount_controller(templates, switch_name, ip=None):
    """
    We did not add Gateways to node configuration in GNS3. If you need to do so, refer to the GNS3utils API.
    """
    template_id = get_template_id_from_name(templates, CONTROLLER_IMG_NAME)
    if ip is not None:
        controller_name = CONTROLLER_IMG_NAME+"-"+ip.split("/")[0]
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


def mount_monitor(templates):
    template_id = get_template_id_from_name(templates, MONITOR_IMG_NAME)
    
    monitor_name = MONITOR_IMG_NAME

    monitor_id = get_node_id_by_name(server,project,monitor_name)
    if(monitor_id is not None):
        delete_node(server,project,monitor_id)
        print("Old monitor node deleted")

    monitor = create_node(server, project, 0, -480, template_id, monitor_name)
    monitor_id = monitor['node_id']
    print(f"new {MONITOR_IMG_NAME} monitor created ")
    time.sleep(2)

    set_dhcp_node_network_interfaces(server, project, monitor_id, "eth0", MONITOR_HOSTNAME)
    print(f"{MONITOR_IMG_NAME}: DHCP on eth0")

    node_ids.append(monitor_id)
    print(f"{MONITOR_IMG_NAME}: started")
    return monitor_name


def mount_zookeeper(templates, switch_name, ip=None):
    template_id = get_template_id_from_name(templates, ZOOKEEPER_IMG_NAME)
    if ip is not None:
        zookeeper_name = ZOOKEEPER_IMG_NAME+"("+ip+")"
    else:
        zookeeper_name = ZOOKEEPER_IMG_NAME

    openvswitch_id = get_node_id_by_name(server,project,switch_name)
    zookeeper_id = get_node_id_by_name(server,project,zookeeper_name)
    print(f"zookeeper id {zookeeper_id}, switch id {openvswitch_id}")
    if(zookeeper_id is not None):
        delete_node(server,project,zookeeper_id)
        print("Old zookeeper node deleted")

    zookeeper = create_node(server, project, -200, 220, template_id, zookeeper_name)
    zookeeper_id = zookeeper['node_id']
    print(f"new {ZOOKEEPER_IMG_NAME} zookeeper created ")
    time.sleep(2)

    if ip is not None:
        set_node_network_interfaces(server, project, zookeeper_id, "eth0", ipaddress.IPv4Interface(ip), None)
        print(f"{ZOOKEEPER_IMG_NAME}: assigned ip: {ip} on eth0")
    else:
        set_dhcp_node_network_interfaces(server, project, zookeeper_id, "eth0", None)
        print(f"{ZOOKEEPER_IMG_NAME}: DHCP on eth0")

    create_link(server, project, zookeeper_id,0,openvswitch_id, 3)
    print(f"Created a link from {ZOOKEEPER_IMG_NAME} to {switch_name} on port eth0")

    set_dhcp_node_network_interfaces(server,project,zookeeper_id,"eth1", None)
    print(f"{ZOOKEEPER_IMG_NAME}: DHCP on eth1")

    node_ids.append(zookeeper_id)
    print(f"{ZOOKEEPER_IMG_NAME}: started")
    return zookeeper_name
    

def mount_kafka(templates, switch_name, ip=None):
    template_id = get_template_id_from_name(templates, KAFKA_IMG_NAME)
    if ip is not None:
        kafka_name = KAFKA_IMG_NAME+"("+ip+")"
    else:
        kafka_name = KAFKA_IMG_NAME

    openvswitch_id = get_node_id_by_name(server,project,switch_name)
    kafka_id = get_node_id_by_name(server,project,kafka_name)
    print(f"kafka id {kafka_id}, switch id {openvswitch_id}")
    if(kafka_id is not None):
        delete_node(server,project,kafka_id)
        print("Old kafka node deleted")

    kafka = create_node(server, project, -100, 260, template_id, kafka_name)
    kafka_id = kafka['node_id']
    print(f"new {KAFKA_IMG_NAME} kafka created ")
    time.sleep(2)

    if ip is not None:
        set_node_network_interfaces(server, project, kafka_id, "eth0", ipaddress.IPv4Interface(ip), None)
        print(f"{KAFKA_IMG_NAME}: assigned ip: {ip} on eth0")
    else:
        set_dhcp_node_network_interfaces(server, project, kafka_id, "eth0", None)
        print(f"{KAFKA_IMG_NAME}: DHCP on eth0")

    create_link(server, project, kafka_id,0,openvswitch_id, 4)
    print(f"Created a link from {KAFKA_IMG_NAME} to {switch_name} on port eth0")

    set_dhcp_node_network_interfaces(server,project,kafka_id,"eth1", None)
    print(f"{KAFKA_IMG_NAME}: DHCP on eth1")

    node_ids.append(kafka_id)
    print(f"{KAFKA_IMG_NAME}: started")
    return kafka_name


def mount_prometheus(templates, switch_name, ip=None):
    template_id = get_template_id_from_name(templates, PROMETHEUS_IMG_NAME)
    if ip is not None:
        prometheus_name = PROMETHEUS_IMG_NAME+"("+ip+")"
    else:
        prometheus_name = PROMETHEUS_IMG_NAME

    openvswitch_id = get_node_id_by_name(server,project,switch_name)
    prometheus_id = get_node_id_by_name(server,project,prometheus_name)
    print(f"prometheus id {prometheus_id}, switch id {openvswitch_id}")
    if(prometheus_id is not None):
        delete_node(server,project,prometheus_id)
        print("Old prometheus node deleted")

    prometheus = create_node(server, project, 100, 260, template_id, prometheus_name)
    prometheus_id = prometheus['node_id']
    print(f"new {PROMETHEUS_IMG_NAME} prometheus created ")
    time.sleep(2)

    if ip is not None:
        set_node_network_interfaces(server, project, prometheus_id, "eth0", ipaddress.IPv4Interface(ip), None)
        print(f"{PROMETHEUS_IMG_NAME}: assigned ip: {ip} on eth0")
    else:    
        set_dhcp_node_network_interfaces(server, project, prometheus_id, "eth0", None)
        print(f"{PROMETHEUS_IMG_NAME}: DHCP on eth0")

    create_link(server, project, prometheus_id,0,openvswitch_id, 5)
    print(f"Created a link from {PROMETHEUS_IMG_NAME} to {switch_name} on port eth0")

    set_dhcp_node_network_interfaces(server,project,prometheus_id,"eth1", None)
    print(f"{PROMETHEUS_IMG_NAME}: DHCP on eth1")

    node_ids.append(prometheus_id)
    print(f"{PROMETHEUS_IMG_NAME}: started")
    return prometheus_name


def mount_grafana(templates, switch_name, ip=None):
    template_id = get_template_id_from_name(templates, GRAFANA_IMG_NAME)
    if ip is not None:
        grafana_name = GRAFANA_IMG_NAME+"("+ip+")"
    else:
        grafana_name = GRAFANA_IMG_NAME

    openvswitch_id = get_node_id_by_name(server,project,switch_name)
    grafana_id = get_node_id_by_name(server,project,grafana_name)
    print(f"grafana id {grafana_id}, switch id {openvswitch_id}")
    if(grafana_id is not None):
        delete_node(server,project,grafana_id)
        print("Old grafana node deleted")

    grafana = create_node(server, project, 200, 220, template_id, grafana_name)
    grafana_id = grafana['node_id']
    print(f"new {GRAFANA_IMG_NAME} grafana created ")
    time.sleep(2)

    if ip is not None:
        set_node_network_interfaces(server, project, grafana_id, "eth0", ipaddress.IPv4Interface(ip), None)
        print(f"{GRAFANA_IMG_NAME}: assigned ip: {ip} on eth0")
    else:    
        set_dhcp_node_network_interfaces(server, project, grafana_id, "eth0", None)
        print(f"{GRAFANA_IMG_NAME}: DHCP on eth0")

    create_link(server, project, grafana_id,0,openvswitch_id, 6)
    print(f"Created a link from {GRAFANA_IMG_NAME} to {switch_name} on port eth0")

    set_dhcp_node_network_interfaces(server,project,grafana_id,"eth1", None)
    print(f"{GRAFANA_IMG_NAME}: DHCP on eth1")

    node_ids.append(grafana_id)
    print(f"{GRAFANA_IMG_NAME}: started")
    return grafana_name

def mountNAT(templates):    
    NAT_template_id = get_template_id_from_name(templates, NAT_IMG_NAME)
    print("NAT TEMPLATE ID: ",NAT_template_id)

    # Create a new node
    nat_node = gfy.Node(
        project_id=project.id, 
        connector=gns3_server_connector, 
        name=NAT_IMG_NAME, 
        template_id= NAT_template_id,
        x=-100,
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
        x=+100,
        y=-350)

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
    switch_port = 7

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
            curr_node_name = f'{nodename}-{ip.split("/")[0]}'
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


def connect_all(
        cfg, 
        main_switch_node_name, 
        edge_switch_node_name,
        controller_node_name,
        monitor_node_name,
        host_names, 
        zookeeper_node_name,
        kafka_node_name,
        prometheus_node_name,
        grafana_node_name,
        fixed_ips=True):

    nat_id = get_node_id_by_name(server, project, NAT_IMG_NAME)
    edge_switch_id = get_node_id_by_name(server, project, edge_switch_node_name)
    create_link(server, project,str(nat_id),0,str(edge_switch_id),1)

    controller_id = get_node_id_by_name(server, project, controller_node_name)
    create_link(server, project,str(edge_switch_id),3,str(controller_id),1)

    montor_id = get_node_id_by_name(server, project, monitor_node_name)
    create_link(server, project,str(edge_switch_id),4,str(montor_id),0)

    if zookeeper_node_name is not None:
        zookeeper_id = get_node_id_by_name(server, project, zookeeper_node_name)
        create_link(server, project,str(edge_switch_id),4,str(zookeeper_id),1)

    if kafka_node_name is not None:
        kafka_id = get_node_id_by_name(server, project, kafka_node_name)
        create_link(server, project,str(edge_switch_id),5,str(kafka_id),1)

    if prometheus_node_name is not None:
        prometheus_id = get_node_id_by_name(server, project, prometheus_node_name)
        create_link(server, project,str(edge_switch_id),6,str(prometheus_id),1)

    if grafana_node_name is not None:
        grafana_id = get_node_id_by_name(server, project, grafana_node_name)
        create_link(server, project,str(edge_switch_id),7,str(grafana_id),1)

    for idx, host_name in enumerate(host_names):
        host_id = get_node_id_by_name(server, project, host_name)
        create_link(server, project,str(edge_switch_id),8+idx,str(host_id),1)

    cloud_id = get_node_id_by_name(server, project, CLOUD_IMG_NAME)

    """
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
    """
   
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
    
    create_link(server, project, str(cloud_id),0,str(edge_switch_id),2, port_number_1=port_index)
    print(f"Created a link from {CLOUD_IMG_NAME} port  to {main_switch_node_name} on port eth0")


def start_all():
    for id in node_ids:
        start_node(server, project, id)
        print("Node: ",id," started")


def starTopology(cfg, templates):
    main_switch_ip = cfg.topology_creator.main_switch_ip + cfg.topology_creator.netmask
    main_switch_node_name = mount_switch(templates, "openvswitch-1", ip=main_switch_ip)
    edge_switch_node_name = mount_edge_switch(templates)
    controller_ip = cfg.topology_creator.controller_ip + cfg.topology_creator.netmask
    controller_node_name = mount_controller(templates, main_switch_node_name, ip=controller_ip)
    monitor_node_name = mount_monitor(templates)
    """
    zookeeper_ip = cfg.topology_creator.zookeeper_ip + cfg.topology_creator.netmask
    zookeeper_node_name = mount_zookeeper(templates, main_switch_node_name, ip=zookeeper_ip)
    kafka_ip = cfg.topology_creator.kafka_ip + cfg.topology_creator.netmask
    kafka_node_name = mount_kafka(templates, main_switch_node_name, ip=kafka_ip)
    prometheus_ip = cfg.topology_creator.prometheus_ip + cfg.topology_creator.netmask
    prometheus_node_name = mount_prometheus(templates, main_switch_node_name, ip=prometheus_ip)
    grafana_ip = cfg.topology_creator.grafana_ip + cfg.topology_creator.netmask
    grafana_node_name = mount_grafana(templates, main_switch_node_name, ip=grafana_ip)
    """
    zookeeper_node_name = None
    kafka_node_name = None
    prometheus_node_name = None
    grafana_node_name = None
    host_names = mount_all_hosts(cfg, templates, main_switch_node_name)
    mountNAT(templates)
    mountCloud(templates)
    connect_all(
        cfg, 
        main_switch_node_name, 
        edge_switch_node_name,
        controller_node_name,
        monitor_node_name,
        host_names,
        zookeeper_node_name,
        kafka_node_name,
        prometheus_node_name,
        grafana_node_name)
    start_all()


def update_generic_template(templates, img_name, start_command, env_vars):
    global project

    template_id = get_template_id_from_name(templates, img_name)
    if(template_id is not None):  
        delete_template(server,project,template_id)
        print((f"{template_id}: deleting old template"))
        
    print((f"{template_id}: creating a new template using local image"))
    create_docker_template(server, img_name, start_command, str(img_name+":latest"), environment=env_vars)


def update_edge_switch_template(templates):
    global project

    switch_template_id = get_template_id_from_name(templates, 'edge-'+SWITCH_IMG_NAME)
    if(switch_template_id is not None):
        delete_template(server,project,switch_template_id)
        print((f"edge-{SWITCH_IMG_NAME}: old switch template deleted"))
    print((f"edge-{SWITCH_IMG_NAME}: creating a new template using local image"))
    network_adapters_count = 10 + VICTIM_NODE_COUNT + ATTACKER_NODE_COUNT
    create_docker_template_switch(server, 'edge-'+SWITCH_IMG_NAME, str(SWITCH_IMG_NAME+":latest"), adapter_count=network_adapters_count)


def update_main_switch_template(templates):
    global project

    switch_template_id = get_template_id_from_name(templates, SWITCH_IMG_NAME)
    if(switch_template_id is not None):
        delete_template(server,project,switch_template_id)
        print((f"{SWITCH_IMG_NAME}: old switch template deleted"))
    print((f"{SWITCH_IMG_NAME}: creating a new template using local image"))
    network_adapters_count = 10 + VICTIM_NODE_COUNT + ATTACKER_NODE_COUNT
    create_docker_template_switch(
        server, SWITCH_IMG_NAME, str(SWITCH_IMG_NAME+":latest"), adapter_count=network_adapters_count, start_command='')


def update_victim_template(args, templates):
    VICTIM_ENV_VARS = ""
    for key, value in OmegaConf.to_container(args.victim, resolve=True).items():
        VICTIM_ENV_VARS += f"{key}={value}\n"

    VICTIM_ENV_VARS += ENV_STR

    update_generic_template(templates, VICTIM_IMG_NAME, VICTIM_START_COMMAND, VICTIM_ENV_VARS)


def update_attacker_template(args, templates):
    ATTACKER_ENV_VARS = ""
    for key, value in OmegaConf.to_container(args.attacker, resolve=True).items():
        ATTACKER_ENV_VARS += f"{key}={value}\n"

    ATTACKER_ENV_VARS += ENV_STR

    update_generic_template(templates, ATTACKER_IMG_NAME, ATTACKER_START_COMMAND, ATTACKER_ENV_VARS)

def update_controller_template(args, templates):
    global project

    CONTROLLER_ENV_VARS = ""
    controller_template_id = get_template_id_from_name(templates, CONTROLLER_IMG_NAME)
    if(controller_template_id is not None):
        delete_template(server,project,controller_template_id)
        print(f"old controller template {CONTROLLER_IMG_NAME} deleted")

    for key, value in OmegaConf.to_container(args.controller, resolve=True).items():
        CONTROLLER_ENV_VARS += f"{key}={value}\n"

    CONTROLLER_ENV_VARS += ENV_STR

    create_docker_template(server, CONTROLLER_IMG_NAME, CONTROLLER_START_COMMAND, str(CONTROLLER_IMG_NAME+":latest"),environment=CONTROLLER_ENV_VARS)


def update_monitor_template(args, templates):
    global project

    MONITOR_ENV_STR = ""

    monitor_template_id = get_template_id_from_name(templates, MONITOR_IMG_NAME)
    if(monitor_template_id is not None):
        delete_template(server,project,monitor_template_id)
        print(f"old MONITOR template {MONITOR_IMG_NAME} deleted")

    for key, value in OmegaConf.to_container(args.monitor, resolve=True).items():
        MONITOR_ENV_STR += f"{key}={value}\n"

    MONITOR_ENV_STR += ENV_STR

    create_docker_template(server, MONITOR_IMG_NAME, MONITOR_START_COMMAND, str(MONITOR_IMG_NAME+":latest"),environment=MONITOR_ENV_STR)

def update_zookeeper_template(args, templates):
    global project

    ZOOKEEPER_ENV_STR = ""

    zookeeper_template_id = get_template_id_from_name(templates, ZOOKEEPER_IMG_NAME)
    if(zookeeper_template_id is not None):
        delete_template(server,project,zookeeper_template_id)
        print(f"old controller template {ZOOKEEPER_IMG_NAME} deleted")

    for key, value in OmegaConf.to_container(args.zookeeper, resolve=True).items():
        ZOOKEEPER_ENV_STR += f"{key}={value}\n"

    ZOOKEEPER_ENV_STR += ENV_STR

    create_docker_template(server, ZOOKEEPER_IMG_NAME, ZOOKEEPER_START_COMMAND, str(ZOOKEEPER_IMG_NAME+":latest"),environment=ZOOKEEPER_ENV_STR)


def update_kafka_template(args, templates):
    global project

    KAFKA_ENV_STR = ""
    kafka_template_id = get_template_id_from_name(templates, KAFKA_IMG_NAME)
    if(kafka_template_id is not None):
        delete_template(server,project,kafka_template_id)
        print(f"old controller template {KAFKA_IMG_NAME} deleted")

    for key, value in OmegaConf.to_container(args.kafka, resolve=True).items():
        KAFKA_ENV_STR += f"{key}={value}\n"

    KAFKA_ENV_STR += ENV_STR

    create_docker_template(server, KAFKA_IMG_NAME, KAFKA_START_COMMAND, str(KAFKA_IMG_NAME+":latest"),environment=KAFKA_ENV_STR)


def update_grafana_template(args, templates):
    global project

    GRAFANA_ENV_STR = ""

    grafana_template_id = get_template_id_from_name(templates, GRAFANA_IMG_NAME)
    if(grafana_template_id is not None):
        delete_template(server,project,grafana_template_id)
        print(f"old controller template {GRAFANA_IMG_NAME} deleted")

    for key, value in OmegaConf.to_container(args.grafana, resolve=True).items():
        GRAFANA_ENV_STR += f"{key}={value}\n"

    GRAFANA_ENV_STR += ENV_STR

    create_docker_template(server, GRAFANA_IMG_NAME, GRAFANA_START_COMMAND, str(GRAFANA_IMG_NAME+":latest"),environment=GRAFANA_ENV_STR)


def update_prometheus_template(args, templates):
    global project

    PROMETHEUS_ENV_STR = ""
    prometheus_template_id = get_template_id_from_name(templates, PROMETHEUS_IMG_NAME)
    if(prometheus_template_id is not None):
        delete_template(server,project,prometheus_template_id)
        print(f"old controller template {PROMETHEUS_IMG_NAME} deleted")

    for key, value in OmegaConf.to_container(args.prometheus, resolve=True).items():
        PROMETHEUS_ENV_STR += f"{key}={value}\n"

    PROMETHEUS_ENV_STR += ENV_STR

    create_docker_template(server, PROMETHEUS_IMG_NAME, PROMETHEUS_START_COMMAND, str(PROMETHEUS_IMG_NAME+":latest"),environment=PROMETHEUS_ENV_STR)



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
    update_monitor_template(args, templates)
    update_victim_template(args, templates)
    update_attacker_template(args, templates)
    """
    update_zookeeper_template(args, templates)
    update_kafka_template(args, templates)
    update_grafana_template(args, templates)
    update_prometheus_template(args, templates)
    """



@hydra.main(config_path="../config", config_name="default", version_base="1.2")
def main(cfg: DictConfig) -> None:
    global PROJECT_NAME, GNS3_HOST, GNS3_PORT, GNS3_AUTH, GNS3_USERNAME, GNS3_PASSWORD
    global CONTROLLER_IMG_NAME, SWITCH_IMG_NAME, VICTIM_IMG_NAME, ATTACKER_IMG_NAME, MONITOR_HOSTNAME, VICTIM_START_COMMAND
    global ZOOKEEPER_IMG_NAME, KAFKA_IMG_NAME, GRAFANA_IMG_NAME, PROMETHEUS_IMG_NAME, MONITOR_IMG_NAME, ATTACKER_START_COMMAND
    global CONTROLLER_START_COMMAND, ENV_STR, ATTACKER_NODE_COUNT, VICTIM_NODE_COUNT, MONITOR_START_COMMAND
    global GRAFANA_START_COMMAND, PROMETHEUS_START_COMMAND, ZOOKEEPER_START_COMMAND, KAFKA_START_COMMAND
    global gns3_server_connector, logger, server, project, node_ids, template_ids
    
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
            logging.info(f'Using configuration override: {cfg.override}')
        except:
            logger.error(f'Unsuccesfully tried to use the configuration override: {cfg.override}')
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
    MONITOR_IMG_NAME = args.monitor_docker
    MONITOR_HOSTNAME = args.monitor_hostname
    SWITCH_IMG_NAME = args.switch_docker
    VICTIM_IMG_NAME = args.victim_docker
    ATTACKER_IMG_NAME = args.attacker_docker
    ZOOKEEPER_IMG_NAME = args.zookeeper_docker
    KAFKA_IMG_NAME = args.kafka_docker
    PROMETHEUS_IMG_NAME = args.prometheus_docker
    GRAFANA_IMG_NAME = args.grafana_docker
    CONTROLLER_START_COMMAND = args.contr_start
    VICTIM_START_COMMAND = args.victim_start
    ATTACKER_START_COMMAND = args.attacker_start
    MONITOR_START_COMMAND = args.monitor_start
    GRAFANA_START_COMMAND = args.grafana_start
    PROMETHEUS_START_COMMAND = args.prometheus_start
    KAFKA_START_COMMAND = args.kafka_start
    ZOOKEEPER_START_COMMAND = args.zookeeper_start

    ENV_STR = args.get('ADDITIONAL_ENV_VARS')
    ATTACKER_NODE_COUNT = len(cfg.attackers)
    VICTIM_NODE_COUNT = len(cfg.honeypots)
    
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