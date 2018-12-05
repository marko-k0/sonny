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
import json
import re
import sys
import logging
import time

from nmap import PortScanner
from openstack.connection import Connection as OpenStack
from pymysql import connect as mysql_connect, escape_string
from rq import Worker

from sonny import __version__
from sonny.common.config import (
    CLOUD,
    MYSQL_HOST,
    MYSQL_USER,
    MYSQL_PASS
)
from sonny.common.redis import SonnyRedis

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"

_logger = logging.getLogger(__name__)

nm = PortScanner()
os = OpenStack(CLOUD)
redis = SonnyRedis(CLOUD)

assert CLOUD is not None
assert MYSQL_HOST is not None
assert MYSQL_USER is not None
assert MYSQL_PASS is not None


def nmap_scan(host_list, port_list=[22]):
    assert isinstance(host_list, list)
    assert len(host_list) > 0

    ip_to_hostname = {}
    host_ip_list = []
    hvs_db = redis.get('hypervisors', json.loads)

    for host in host_list:
        if re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', host):
            host_ip_list.append(host)
        else:
            hv_ip = hvs_db[host]['host_ip']
            ip_to_hostname[hv_ip] = host
            host_ip_list.append(hv_ip)

    results = nm.scan(
        ' '.join(host_ip_list),
        ','.join(str(p) for p in port_list)
    )
    up_hosts = results['scan'].keys()
    down_hosts = set(host_ip_list).difference(set(up_hosts))

    down_host_list = []
    for h in down_hosts:
        down_host = h if h not in ip_to_hostname else ip_to_hostname[h]
        down_host_list.append(down_host)

    return down_host_list


def refresh_redis_inventory(update_servers=False):
    try:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

        if update_servers:
            update_servers_db(os_conn)
        update_hypervisors_db(os_conn)
        update_projects_db(os_conn)
        update_agents_db(os_conn)
        update_services_db(os_conn)
        update_aggregates_db(os_conn)
    except Exception as e:
        redis.set('api_alive', False)
        _logger.error(str(e))
        raise e

    redis.set('api_alive', True)
    redis.set('api_alive:timestamp', time.time())


def update_aggregates_db(os_conn=None):
    if not os_conn:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

    aggregates_os = os_conn.list_aggregates()
    aggregates = {}
    for aggregate in aggregates_os:
        for host in aggregate.hosts:
            aggregates[host] = aggregate.name

    redis.set('aggregates', json.dumps(aggregates))
    redis.set('aggregates:timestamp', time.time())


def update_services_db(os_conn=None):
    if not os_conn:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

    services_os = os_conn.compute.services()
    services = {
        s.host: s.to_dict() for s in services_os
        if s.binary == 'nova-compute'
    }

    redis.set('services', json.dumps(services))
    redis.set('services:timestamp', time.time())


def update_projects_db(os_conn=None):
    if not os_conn:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

    projects_os = os_conn.identity.projects()
    projects = {t.id: t.to_dict() for t in projects_os}

    redis.set('projects', json.dumps(projects))
    redis.set('projects:timestamp', time.time())


def update_hypervisors_db(os_conn=None):
    if not os_conn:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

    hypervisors_os = os_conn.compute.hypervisors(True)
    hypervisors = {hv.name: hv.to_dict() for hv in hypervisors_os}

    redis.set('hypervisors', json.dumps(hypervisors))
    redis.set('hypervisors:timestamp', time.time())


def update_agents_db(os_conn=None):
    if not os_conn:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

    agents_os = [
        (a.host, a.binary, a.last_heartbeat_at)
        for a in os_conn.network.agents()
    ]
    agents = {}
    for host, binary, heartbeat in agents_os:
        agents.setdefault(host, {})[binary] = heartbeat

    redis.set('agents', json.dumps(agents))
    redis.set('agents:timestamp', time.time())


def update_servers_db(os_conn=None):
    if not os_conn:
        os_conn = OpenStack(
            session=os.session, cloud=CLOUD, region_name=os.get_region())

    servers_os = os_conn.compute.servers(all_tenants=True)
    servers = {}

    for server in servers_os:
        servers[server.id] = server.to_dict()

    redis.set('servers', json.dumps(servers))
    redis.set('servers:timestamp', time.time())


def reset_cooldown():
    redis.delete('resurrection:timestamp')


# XXX: use nova api (evacuate --on-shared-storage) & refactor
def resurrect_instances(dead_hv, spare_hv, update_db=True):
    assert dead_hv != spare_hv

    os_conn = OpenStack(
        session=os.session, cloud=CLOUD, region_name=os.get_region())

    if update_db:
        _logger.info('updating redis database')
        refresh_redis_inventory(True)

    spare_hv_r = redis.get('hypervisors', json.loads)[spare_hv]
    assert spare_hv_r['running_vms'] == 0
    dead_service = spare_service = None
    for svc in os_conn.compute.services():
        if svc.host == dead_hv:
            dead_service = svc
        elif svc.host == spare_hv:
            spare_service = svc
            assert svc.status == 'disabled'

    assert dead_service is not None
    assert spare_service is not None
    assert spare_service.state == 'up'
    assert spare_service.zone == dead_service.zone
    assert 'spare' in spare_service.disables_reason.lower()

    _logger.info(f'verifying that {dead_hv} is dead')
    if not nmap_scan([dead_hv], [22, 111, 16509]):
        raise Exception(f'hypervisor {dead_hv} does not seem to be dead!')

    instance_list = []
    servers = json.loads(redis.get('servers'))
    for _, server in servers.items():
        if server['hypervisor_hostname'] == spare_hv:
            raise Exception(f'spare hypervisor {spare_hv} has vms assigned!')
        if server['hypervisor_hostname'] == dead_hv:
            instance_list.append(server['id'])
            server['hypervisor_hostname'] = spare_hv

    if not instance_list:
        _logger.warning(f'{dead_hv} does not run any instances')
        return

    _logger.info('updating database records in nova')
    db_conn = mysql_connect(
        host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASS, db='nova')
    try:
        spare_hv = escape_string(spare_hv)
        with db_conn.cursor() as cursor:
            for uuid in instance_list:
                uuid = escape_string(uuid)
                query = \
                    f'''update instances set
                    host = "{spare_hv}", node = "{spare_hv}"
                    where uuid="{uuid}"'''
                _logger.debug(query)
                cursor.execute(query)
        db_conn.commit()
    finally:
        db_conn.close()

    _logger.info('updating servers inventory db')
    redis.set('servers', json.dumps(servers))

    exceptions = []
    for uuid in instance_list:
        try:
            if servers[uuid]['vm_state'] == 'stopped':
                _logger.info(f'instance {uuid} is stoppped, not rebooting')
                continue

            _logger.info(f'hard rebooting instance {uuid}')
            os_conn.compute.reboot_server(uuid, 'HARD')
            for ifce in os_conn.compute.server_interfaces(uuid):
                _logger.info(f'updating port binding on {ifce.port_id}')
                port = os_conn.get_port(ifce.port_id)
                if port:
                    os_conn.network.update_port(
                        port, **{'binding:host_id': spare_hv})
        except Exception as e:
            exceptions.append(str(e))

    if exceptions:
        raise Exception('\n'.join(exceptions))

    _logger.info(f'disabling nova on {dead_hv}, enabling nova on {spare_hv}')
    os_conn.compute.disable_service(dead_service, dead_hv, 'nova-compute',
                                    f'sonny resurrection on {spare_hv}')
    os_conn.compute.enable_service(spare_service, spare_hv, 'nova-compute')


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(
        description="NS-4 Robot")
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

    recover_group = parser.add_argument_group(title='Resurrect Instances')
    recover_group.add_argument(
        '-d',
        '--dead-hypervisor')
    recover_group.add_argument(
        '-s',
        '--spare-hypervisor')
    recover_group.add_argument(
        '-r',
        '--reset-cooldown',
        action='store_true',
        help='reset cooldown period')

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

    if args.dead_hypervisor:
        if not args.spare_hypervisor:
            print('Spare hypervisor required!')
            sys.exit(1)

        resurrect_instances(
            args.dead_hypervisor,
            args.spare_hypervisor)

        return

    if args.reset_cooldown:
        reset_cooldown()
        return

    _logger.debug("started monitor")
    Worker(['default'], connection=redis).work()


def run():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
