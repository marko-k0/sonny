# Sonny [![Build Status](https://travis-ci.org/marko-k0/sonny.png?branch=master)](https://travis-ci.org/marko-k0/sonny)


Sonny is a project providing automatic recovery for OpenStack instances from compute nodes that experience hardware failure. It takes care that your pet instances become available when inevitable hardware failure happens. _Sonny only works with CEPH being used as a beckend for emphemeral disks and Cinder volumes._


# Motivation

Modern applications in a cloud environment follow "cattle" model where application is build in a resilient way to tolerate the case where the instance dies for some reason. Maybe you haven't managed to get to the point where you have this kind of application and you are still treating virtual machines as a pets. That means that you want to have your pet resurrected when inevitable hardware failure kills it. Sonny brings you support for this scenario.

# Arhitecture

Project provides 3 separate processes that communicate with each other by *redis*, using [RQ](http://python-rq.org/). Process *ns4* serves as a worker process, *monitor* has the logic for detecting if hypervisor is dead by delegating jobs to *ns4*. It communicates important events to *sonny* which serves as middle "man" to carry this information to Slack. It is also able to respond to some basic information questions about virtual instances and hypervisors. 

## Processes

* *ns4* has jobs defined for updating OpenStack inventory (hosts, projects, neutron agents and instances) in *redis*, job for performing tcp scan on a list of hosts and last but not least, job for resurrecting dead instances from a dead hypervisor.

* *monitor* gives all the work to *ns4* but carries the core logic. It updates *redis* inventory, checks for hypervisors who's neutron agents haven't sent heartbeat in the last minute and performs tcp check on ports 22, 111 and 16509. If there is no reponse, it does tcp check on port 22 on all the instances that have IP from external network. In case there is no response, it concludes the hypervisor is dead and starts resurrecting all the instances.

* *sonny* subscribes to *redis* channels for messages from *monitors*. It post this messages on predefined Slack channel. It has very limited capabilities to responding to some questions.

## Constraints and limitiations

List of assumptions, constraints and limitations:

* all *monitors* are using the same *redis* host but each monitor has different database,
* *ns4* is able to reach all hypervisors on tcp 22, 111 and 16509,
* any hypervisor has at least one instance that *ns4* can rach on tcp port 22.

# Getting Started

## Prerequisites

Supported OpenStack enviornment is using *KVM* based hardware virtualization and *CEPH* storage backend for emphemeral disks and *Cinder* volumes.  

Install *nmap* and *redis* and use *python 3.7*.

## Installing

### Build and Install
```
virtualenv ~/.venv-sonny
source ~/.venv-sonny/bin/activate

git clone https://github.com/marko-k0/sonny
cd sonny
pip install .
```

### Configuration

Configure [Slack Bot User](https://api.slack.com/bot-users) and [OpenStack clouds.yaml](https://docs.openstack.org/python-openstackclient/pike/configuration/index.html). Create *~/.config.ini* and set configuration parameters for *REDIS*, *MYSQL*, *OPENSTACK* and *SLACK*.  

Configuration under *DEFAULT* section has the following meaning:
* *monitor_period* defines the period that the *monitor* does the check,
* *hearbeat_period* is the period by which all the neutron agents should be reporting to controller,
* *suspicious_backoff* defines how many hypervisors monitor can still inspect when heartbeats from neutron agents are missing,
* *cooldown_period* is the period that the monitor doesn't perform any action after resurrection happens,
* *dead_backoff* is the maximum number of dead hypervisors that *monitor* will be willing to handle.


### Run

```
cd ~
tmux new-session -s sonny
tmux new-window -n ns4 ns4 -v
tmux new-window -n sonny sonny
tmux new-window -n monitor monitor -v
```

# Comparison to Masakari

OpenStack project [Masakari](https://github.com/openstack/masakari) exists that provides similar service. *TODO*

# TODO

- [x] Beta version.
- [ ] Add Supervisord and Ansible deployment.
- [ ] Detect that access switch of HV is OK.
- [ ] Make Sonny be able to use Telegram.
- [ ] HA version.
- [ ] Make Sonny smarter for conversation.

# License

This project is currently licensed under GPLv3 - see [LICENSE.txt](LICENSE.txt) file.
