# Makefile

# Load the .env file if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

# Generate a timestamp to use as cache-busting value
CACHE_BUST := $(shell date +%s)

.PHONY: all build-controller build-attacker build-victim build-openvswitch build-monitor \
        all-scache all-scache-nolib scache-nolib \
        build-controller-scache build-attacker-scache build-victim-scache build-monitor-scache build-mockserver-scache \
        build-controller-scache-nolib build-attacker-scache-nolib build-victim-scache-nolib build-monitor-scache-nolib build-mockserver-scache-nolib

all: build-controller build-attacker build-victim build-openvswitch build-monitor
all-nocache: build-victim-nocache build-attacker-nocache build-controller-nocache build-monitor-nocache
all-scache: build-controller-scache build-attacker-scache build-victim-scache build-monitor-scache build-openvswitch
all-scache-nolib: build-controller-scache-nolib build-attacker-scache-nolib build-victim-scache-nolib build-monitor-scache-nolib build-openvswitch
scache-nolib: all-scache-nolib

build-controller:
	docker build --build-arg WANDB_API_KEY=$(WANDB_API_KEY) -t pox-controller -f poxController/controller.Dockerfile poxController/.

build-controller-nocache:
	docker build --no-cache --build-arg WANDB_API_KEY=$(WANDB_API_KEY) -t pox-controller -f poxController/controller.Dockerfile poxController/.

build-attacker:
	docker build -t attacker -f AttackerNode/attacker.Dockerfile AttackerNode/.

build-attacker-nocache:
	docker build --no-cache -t attacker -f AttackerNode/attacker.Dockerfile AttackerNode/.

build-victim:
	docker build -t victim -f VictimNode/victim.Dockerfile VictimNode/.

build-victim-nocache:
	docker build --no-cache -t victim -f VictimNode/victim.Dockerfile VictimNode/.

build-botmaster:
	docker build --build-arg GIT_USERNAME=$(GIT_USERNAME) --build-arg GIT_TOKEN=$(GIT_TOKEN) -t botmaster -f BotMasterNode/botmaster.Dockerfile BotMasterNode/.

build-mockserver:
	docker build -t mockserver -f mockserver/mockserver.Dockerfile mockserver/.

build-openvswitch:
	docker build -t openvswitch -f openvswitch.Dockerfile openSwitch/.

build-monitor:
	docker build -t monitor -f smartville-monitor/monitor.Dockerfile smartville-monitor/.

build-monitor-nocache:
	docker build --no-cache -t monitor -f smartville-monitor/monitor.Dockerfile smartville-monitor/.

# scache builds (full rebuild of dependencies and code)
build-controller-scache:
	docker build --build-arg WANDB_API_KEY=$(WANDB_API_KEY) \
	             --build-arg CACHE_BUST=$(shell date +%s) \
	             -t pox-controller \
	             -f poxController/controller.Dockerfile poxController/.

build-monitor-scache:
	docker build --build-arg CACHE_BUST=$(shell date +%s) \
	             -t monitor \
	             -f smartville-monitor/monitor.Dockerfile smartville-monitor/.

build-attacker-scache:
	docker build --build-arg CACHE_BUST=$(shell date +%s) \
	             -t attacker \
	             -f AttackerNode/attacker.Dockerfile AttackerNode/.

build-victim-scache:
	docker build --build-arg CACHE_BUST=$(shell date +%s) \
	             -t victim \
	             -f VictimNode/victim.Dockerfile VictimNode/.

build-mockserver-scache:
	docker build --build-arg CACHE_BUST=$(shell date +%s) \
	             -t mockserver \
	             -f mockserver/mockserver.Dockerfile mockserver/.

# scache-nolib builds (reuse cached pip dependencies, rebuild code clone only)
build-controller-scache-nolib:
	docker build --build-arg WANDB_API_KEY=$(WANDB_API_KEY) \
	             --build-arg CODE_BUST=$(shell date +%s) \
	             -t pox-controller \
	             -f poxController/controller.Dockerfile poxController/.

build-monitor-scache-nolib:
	docker build --build-arg CODE_BUST=$(shell date +%s) \
	             -t monitor \
	             -f smartville-monitor/monitor.Dockerfile smartville-monitor/.

build-attacker-scache-nolib:
	docker build --build-arg CODE_BUST=$(shell date +%s) \
	             -t attacker \
	             -f AttackerNode/attacker.Dockerfile AttackerNode/.

build-victim-scache-nolib:
	docker build --build-arg CODE_BUST=$(shell date +%s) \
	             -t victim \
	             -f VictimNode/victim.Dockerfile VictimNode/.

build-mockserver-scache-nolib:
	docker build --build-arg CODE_BUST=$(shell date +%s) \
	             -t mockserver \
	             -f mockserver/mockserver.Dockerfile mockserver/.

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
