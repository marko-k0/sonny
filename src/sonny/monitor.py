#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Sonny
#
#    Copyright (C) 2018  Marko Kosmerl
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division, print_function, absolute_import

import argparse
import datetime
import json
import sys
import logging
import time

from rq import Queue

from sonny import __version__
from sonny.ns4 import (
    nmap_scan,
    refresh_redis_inventory,
    resurrect_instances)
from sonny.common.config import (
    COOLDOWN_PERIOD,
    DEAD_BACKOFF,
    HEARTBEAT_PERIOD,
    MONITOR_PERIOD,
    SUSPICIOUS_BACKOFF
)
from sonny.common.config import (
    CLOUD,
    SLACK_TOKEN,
    SLACK_CHANNEL
)
from sonny.common.redis import SonnyRedis

assert CLOUD is not None

strptime = datetime.datetime.strptime
utcnow = datetime.datetime.utcnow

_logger = logging.getLogger(__name__)

# REDIS
redis = SonnyRedis(CLOUD)
work_queue = Queue(connection=redis)


class SonnyHandler(logging.StreamHandler):

    def __init__(self, topic):
        logging.StreamHandler.__init__(self)
        self.topic = topic

    def emit(self, record):
        msg = self.format(record)
        redis.publish(self.topic, msg)


class Monitor:

    def __init__(self):
        work_queue.empty()
        for key in redis.keys('rq:job:*'):
            redis.delete(key)

        if SLACK_TOKEN and SLACK_CHANNEL:
            sonny_handler = SonnyHandler(CLOUD)
            _logger.addHandler(sonny_handler)
        else:
            _logger.info('slack config missing')

        _logger.info(f'monitor initialized on db {redis.db}')

    @property
    def api_alive(self):
        alive = redis.get('api_alive', str)
        alive_ts = redis.get('api_alive:timestamp', float)

        return alive == 'True' and (time.time() - alive_ts) < 60

    @api_alive.setter
    def api_alive(self, alive=True):
        redis.set('api_alive', alive)
        if alive:
            redis.set('api_alive:timestamp', time.time())

    def run(self):
        def period_sleep(check_time):
            time.sleep(max(MONITOR_PERIOD - (time.time() - check_time), 0))

        _logger.info('monitor running')
        self.api_alive = True

        while True:
            check_time = time.time()
            self.run_step()
            period_sleep(check_time)

    def run_step(self):
        """
        * update redis db,
        * get suspicious hypervisors
        * inspect suspicious hypervisors
        * inspect instances if hypervisor is unresponsive
        * handle dead hypervisor if instances unresponsive
        """
        _logger.debug('refreshing redis inventory')
        job = self.refresh_redis_inventory()
        job_finished = self.wait_for_job(job, 90)

        if job_finished and self.api_alive:
            _logger.debug('openstack api available')

            s_hvs = self.get_suspicious_hypervisors()
            if s_hvs:
                _logger.warning(f'suspicious hypervisors: {s_hvs}')
                if len(s_hvs) > SUSPICIOUS_BACKOFF:
                    _logger.warning(
                        'too many suspicious hypervisors, backing off')
                    return

                _logger.warning('scan check on on port 22, 111 and 16509')
                done, u_hvs = self.inspect_hypervisors(s_hvs)
                if done and u_hvs:
                    _logger.warning(f'no response from {u_hvs}')

                    d_hvs, a_hvs = self.inspect_instances(u_hvs)
                    if d_hvs:
                        _logger.warning(f'dead hypervisors detected: {d_hvs}')
                        s_cnt, f_cnt = self.handle_dead_hypervisors(d_hvs)
                        if s_cnt and not f_cnt:
                            _logger.info('affected instances resurrected')

                    if a_hvs:
                        _logger.warning(f'some or all instances reachable '
                                        f'but hypervisor is not: {a_hvs}')
                else:
                    _logger.info('tcp scan check shows hypervisors are ok')
            else:
                _logger.debug('no suspicious hypervisors')
        elif not self.api_alive:
            if job.result:
                _logger.warning(f'issues within the worker: {job.result}')
            else:
                _logger.warning(f'unknown issues within the worker')

    def handle_dead_hypervisors(self, dead_hvs):
        dead_count = len(dead_hvs)
        if dead_count > DEAD_BACKOFF:
            if DEAD_BACKOFF == 0:
                _logger.warning('running in dry mode')
            else:
                _logger.warning(f'dead limit ({dead_count} > {DEAD_BACKOFF})')
            _logger.warning('not performing any action')
            return None, None

        last_resurrection = redis.get('resurrection:timestamp', float)
        if last_resurrection and \
           time.time() - last_resurrection < COOLDOWN_PERIOD:
            _logger.warning('cooldown period still active')
            _logger.warning('not performing any action')
            return None, None

        running_job = {}
        selected_hv_set = set()
        for dead_hv in dead_hvs:
            spare_hv = self.get_spare_hypervisor(dead_hv, selected_hv_set)
            if spare_hv:
                selected_hv_set.add(spare_hv)
                _logger.info(f'resurrection started: {dead_hv} -> {spare_hv}')
                job = self.resurrect_instances(dead_hv, spare_hv)
                running_job[job.id] = job
            else:
                _logger.warning(f'no spare hypervisors!')
                return None, None

        redis.set('resurrection:timestamp', time.time())
        success_count = failure_count = 0
        while running_job:
            time.sleep(2)

            for job_id, job in dict(running_job).items():
                dead_hv, spare_hv = job.args
                if job.is_finished:
                    _logger.info(f'success: {dead_hv} -> {spare_hv}')
                    del running_job[job.id]
                    success_count += 1
                elif job.is_failed:
                    _logger.warning(f'failure: {dead_hv} -> {spare_hv}')
                    _logger.error(job.exc_info)
                    del running_job[job.id]
                    failure_count += 1

        return success_count, failure_count

    def inspect_hypervisors(self, suspicious_hvs):
        assert isinstance(suspicious_hvs, list)
        assert len(suspicious_hvs) > 0

        job = self.inspect_hosts(suspicious_hvs, port_list=[22, 111, 16509])
        if self.wait_for_job(job, 60):
            return True, job.result

        return False, []

    def inspect_instances(self, unreachable_hvs):
        assert isinstance(unreachable_hvs, list)
        assert len(unreachable_hvs) > 0

        job = self.refresh_redis_inventory(True)
        self.wait_for_job(job, 90)

        running_job = {}
        dead_hvs, alive_hvs = [], []

        for hv in unreachable_hvs:
            instances = self.get_instances(hv)
            instances_ip = [ip for _, ip in instances]
            if not instances_ip:
                _logger.info(f'no instances on {hv}')
                continue

            _logger.info(f'inspecting instances {instances_ip}')
            job = self.inspect_hosts(instances_ip, port_list=[22])
            job.hv = hv
            running_job[job.id] = job

        while running_job:
            time.sleep(1)

            for job_id, job in dict(running_job).items():
                if job.is_finished:
                    all_ips = job.args[0]
                    dead_ips = job.result
                    if len(dead_ips) == len(all_ips):
                        dead_hvs.append(job.hv)
                    else:
                        alive_hvs.append(job.hv)
                    del running_job[job.id]
                elif job.is_failed:
                    alive_hvs.append(job.hv)
                    del running_job[job.id]

        return dead_hvs, alive_hvs

    def wait_for_job(self, job, timeout=30):
        start_time = time.time()
        while not (job.is_finished or job.is_failed):
            time.sleep(1)
            if time.time() - start_time > timeout:
                return False

        return job.is_finished

    def get_suspicious_hypervisors(self):
        _logger.debug('checking for suspicious hypervisors')
        current_time = utcnow().timestamp()
        agents = redis.get('agents', json.loads)
        hvs = redis.get('hypervisors', json.loads)
        hypervisor_list = []

        for hv_name, agent_dict in agents.items():
            if hv_name not in hvs:
                continue

            hv = hvs[hv_name]
            if hv['state'] == 'down' and \
               hv['service_details']['disabled_reason'] and \
               'sonny' in hv['service_details']['disabled_reason']:
                _logger.debug(f'{hv_name} is down but alredy handled')
                continue
            elif hv['status'] == 'disabled' and hv['running_vms'] == 0:
                _logger.debug(
                    f'ignoring {hv_name} (disabled and 0 running vms)')
                continue
            elif hv['status'] == 'disabled' and hv['running_vms'] > 0:
                r_vms = hv['running_vms']
                _logger.warning(
                    f'{hv_name} is disabled and running {r_vms} instances!')
            elif hv['running_vms'] == 0:
                _logger.debug(f'ignoring {hv_name} (0 running vms)')
                continue

            ts_list = [
                strptime(t, "%Y-%m-%d %H:%M:%S").timestamp()
                for t in agent_dict.values()
            ]

            if all([(current_time - t) > HEARTBEAT_PERIOD for t in ts_list]):
                hypervisor_list.append(hv_name)
                _logger.info(f'hypervisor {hv_name} is suspicious')
                for a, t in agent_dict.items():
                    tt = strptime(t, "%Y-%m-%d %H:%M:%S").timestamp()
                    tt_d = int(current_time - tt)
                    _logger.debug(f'last heartbeat of {a} was {tt_d} sec ago')

        return hypervisor_list

    def get_instances(self, hypervisor):
        _logger.debug(f'checking for affected instances on {hypervisor}')
        servers = redis.get('servers', json.loads)
        instance_list = []

        for _, server in servers.items():
            if server['hypervisor_hostname'] == hypervisor:
                if 'ext-net' in server['addresses']:
                    instance_name = server['name']
                    instance_ip = server['addresses']['ext-net'][0]['addr']
                    instance_list.append((instance_name, instance_ip))

        return instance_list

    def get_spare_hypervisor(self, hv_down, ignore_set={}):
        _logger.info(f'getting spare hypervisor for {hv_down}')

        services = redis.get('services', json.loads)
        aggregates = redis.get('aggregates', json.loads)
        hypervisors = redis.get('hypervisors', json.loads)

        hv_down_az = services[hv_down]['zone']
        hv_down_vcpus = hypervisors[hv_down]['vcpus']
        hv_down_aggregate = aggregates[hv_down]

        _logger.info(f'az: {hv_down_az}, aggregate: {hv_down_aggregate}')

        spare_hv = None
        spare_hvs = []
        for hv in services:
            state = services[hv]['state']
            status = services[hv]['status']
            disables_reason = str(services[hv]['disables_reason'])
            zone = services[hv]['zone']

            if all([zone == hv_down_az, state == 'up',
                    status == 'disabled', 'spare' in disables_reason.lower()]):
                spare_hvs.append(hv)

        _logger.info(f'spare hypervisor candidates: {spare_hvs}')

        for hv_name in spare_hvs:
            hv = hypervisors[hv_name]
            if aggregates[hv_name] != hv_down_aggregate:
                continue
            if hv['vcpus_used'] > 0:
                continue
            if hv['vcpus'] < hv_down_vcpus:
                continue
            if hv_name in ignore_set:
                continue

            spare_hv = hv_name
            break

        return spare_hv

    def resurrect_instances(self, dead_hv, spare_hv):
        return work_queue.enqueue(resurrect_instances, dead_hv, spare_hv)

    def inspect_hosts(self, hv_name_list, port_list=[22]):
        return work_queue.enqueue(nmap_scan, hv_name_list, port_list)

    def refresh_redis_inventory(self, update_servers=False):
        last_servers_update = redis.get('servers:timestamp', float)
        if not last_servers_update or time.time() - last_servers_update > 600:
            update_servers = True

        return work_queue.enqueue(refresh_redis_inventory, update_servers)


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(
        description="OpenStack Monitor")
    parser.add_argument(
        '--version',
        action='version',
        version='sonny {ver}'.format(ver=__version__))
    parser.add_argument(
        '-v',
        '--verbose',
        dest="loglevel",
        help="set loglevel to INFO",
        action='store_const',
        const=logging.INFO)
    parser.add_argument(
        '-vv',
        '--very-verbose',
        dest="loglevel",
        help="set loglevel to DEBUG",
        action='store_const',
        const=logging.DEBUG)
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout,
                        format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    setup_logging(args.loglevel)
    _logger.debug("starting sonny")

    Monitor().run()


def run():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
