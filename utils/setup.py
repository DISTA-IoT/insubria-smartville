import subprocess
import re
from gns3util import *


def setup_gns3_bridge():
    bridge_name = "gns3-bridge"
    bridge_ip = "192.168.1.100/24"
    
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
        

if __name__ == "__main__":
    setup_gns3_bridge()