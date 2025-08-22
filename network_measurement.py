# start a wand monitoring
import wandb
import time
wandb.init(project="network_monitoring", config={"system_monitor": {"cpu": True, "memory": True, "disk": True, "gpu": True, "network": True}})
# a loop waiting for the user to end with ctrl c

seconds = 0 
while True:
    wandb.log({"seconds_counter": seconds })
    time.sleep(1)
    seconds += 1