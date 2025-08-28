# Makefile

# Load the .env file if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

.PHONY: all build-controller build-attacker build-victim build-openvswitch build-monitor

all: build-controller build-attacker build-victim build-openvswitch build-monitor

build-controller:
	docker build --build-arg WANDB_API_KEY=$(WANDB_API_KEY) -t pox-controller -f poxController/controller.Dockerfile poxController/.

build-attacker:
	docker build -t attacker -f AttackerNode/attacker.Dockerfile AttackerNode/.

build-victim:
	docker build -t victim -f VictimNode/victim.Dockerfile VictimNode/.

build-botmaster:
	docker build --build-arg GIT_USERNAME=$(GIT_USERNAME) --build-arg GIT_TOKEN=$(GIT_TOKEN) -t botmaster -f BotMasterNode/botmaster.Dockerfile BotMasterNode/.

build-openvswitch:
	docker build -t openvswitch -f openvswitch.Dockerfile openSwitch/.

build-monitor:
	docker build -t monitor -f smartville-monitor/monitor.Dockerfile smartville-monitor/.

# Zookeeper node (uses prebuilt Confluent image)
build-zookeeper:
	docker pull confluentinc/cp-zookeeper:latest

# Kafka node (uses prebuilt Confluent image)
build-kafka:
	docker pull confluentinc/cp-kafka:latest

# Prometheus node (official image)
build-prometheus:
	docker pull prom/prometheus:latest

# Grafana node (official image)
build-grafana:
	docker pull grafana/grafana:latest
