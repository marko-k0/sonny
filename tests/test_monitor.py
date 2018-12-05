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

from random import randint
from unittest.mock import MagicMock, patch

import json
import pytest
import time
import sys

sys.modules['openstack.connection'] = MagicMock()
import sonny.monitor # noqa
from .fakesonnyredis import FakeSonnyRedis # noqa

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


def setup_module(module):
    sonny.monitor.redis = FakeSonnyRedis()


@pytest.fixture
def monitor():
    with patch.object(sonny.monitor.Monitor, '__init__', lambda _: None):
        monitor = sonny.monitor.Monitor()

        monitor.redis = sonny.monitor.redis
        monitor.redis.flushall()
        monitor.api_alive = True

        monitor.wait_for_job = MagicMock(return_value=True)

        monitor.refresh_redis_inventory = MagicMock()
        monitor.refresh_redis_inventory.return_value = MagicMock()
        monitor.refresh_redis_inventory.return_value.finished = True

        monitor.inspect_hosts = MagicMock()
        monitor.inspect_hosts.return_value = MagicMock()
        monitor.inspect_hosts.return_value.id = randint(1, 1000000)
        monitor.inspect_hosts.return_value.finished = True
        monitor.inspect_hosts.return_value.result = []

        monitor.recover_instances = MagicMock()
        monitor.recover_instances.return_value = MagicMock()
        monitor.recover_instances.return_value.id = randint(1, 1000000)
        monitor.recover_instances.return_value.finished = True

        return monitor


def test_db_value(monitor):
    monitor.redis.set('string', 'string')
    monitor.redis.set('dict', json.dumps({'test': 1}))
    monitor.redis.set('list', json.dumps(['test']))

    assert monitor.redis.get('missing') is None
    assert monitor.redis.get('string', str) == 'string'
    assert monitor.redis.get('dict', json.loads) == {'test': 1}
    assert monitor.redis.get('list', json.loads) == ['test']


def test_api_alive(monitor):
    monitor.api_alive = False
    assert monitor.api_alive is False
    monitor.api_alive = True
    assert monitor.api_alive is True


def test_get_instances(monitor):

    instance = {
        '9de51dbe-22b5-4737-9d4e-656ed66e9b9f':
        {'addresses': {'ext-net': [
            {'version': 4, 'addr': '10.10.10.10',
             'OS-EXT-IPS:type': 'fixed'}]},
         'name': 'instance1',
         'hypervisor_hostname': 'hv42'},
        '12345678-22b5-4737-9d4e-656ed66e9b9f':
        {'addresses': {'test-net': [
            {'version': 4, 'addr': '10.10.10.11',
             'OS-EXT-IPS:type': 'fixed'}]},
         'name': 'instance2',
         'hypervisor_hostname': 'hv42'}
    }

    monitor.redis.set('servers', json.dumps(instance))
    assert monitor.get_instances('hv42') == [('instance1', '10.10.10.10')]
    assert monitor.get_instances('hv43') == []


def test_inspect_hypervisors(monitor):
    assert monitor.inspect_hypervisors(['hv1']) == (True, [])


def test_inspect_instances(monitor):
    u_hvs = ['hv42']
    instances = [(1, '192.168.1.1'), (2, '192.168.1.2'), (3, '192.168.1.3')]
    inspect_returns = [[], ['192.168.1.1'], [ip for _, ip in instances]]
    inspect_instances_rets = [
        ([], ['hv42']), ([], ['hv42']), (['hv42'], [])
    ]

    monitor.get_instances = MagicMock()
    monitor.get_instances.return_value = instances
    monitor.inspect_hosts.return_value.args = ([ip for _, ip in instances], 22)
    for idx, ret in enumerate(inspect_returns):
        monitor.inspect_hosts.return_value.result = ret

        expected = inspect_instances_rets[idx]
        returned = monitor.inspect_instances(u_hvs)
        assert expected == returned


def test_handle_dead_hypervisors1(monitor):
    # successfully handle 2 dead hypervisors
    dead_hvs = ['hv10', 'hv11']

    def get_spare_hv_mock(dead_hv, _):
        return dead_hv + '9'

    def resurrect_instances_mock(*args):
        m = MagicMock()
        m.id = randint(1, 1000000)
        m.args = dead_hvs
        return m

    sonny.monitor.DEAD_BACKOFF = 2
    monitor.get_db_value = MagicMock(return_value=None)
    monitor.get_spare_hypervisor = MagicMock(
        side_effect=get_spare_hv_mock)
    monitor.resurrect_instances = MagicMock(
        side_effect=resurrect_instances_mock)

    assert not monitor.redis.get('resurrection:timestamp')
    assert monitor.handle_dead_hypervisors(dead_hvs) == (2, 0)
    assert monitor.redis.get('resurrection:timestamp')


def test_handle_dead_hypervisors2(monitor):
    # 1 successfully handled and 1 unsuccessfully handled
    dead_spare_hv = {'hv10': 'hv109', 'hv11': 'hv119'}

    def get_spare_hv_mock(dead_hv, _):
        return dead_spare_hv[dead_hv]

    def resurrect_instances_mock(dead_hv, spare_hv):
        m = MagicMock()
        m.id = randint(1, 1000000)
        m.args = [dead_hv, spare_hv]
        if dead_hv == 'hv10':
            m.is_finished = True
            m.is_failed = False
        else:
            m.is_finished = False
            m.is_failed = True
        return m

    sonny.monitor.DEAD_BACKOFF = 2
    monitor.get_db_value = MagicMock(return_value=None)
    monitor.get_spare_hypervisor = MagicMock(side_effect=get_spare_hv_mock)
    monitor.resurrect_instances = MagicMock(
        side_effect=resurrect_instances_mock)

    assert not monitor.redis.get('resurrection:timestamp')
    assert monitor.handle_dead_hypervisors(dead_spare_hv.keys()) == (1, 1)
    assert monitor.redis.get('resurrection:timestamp')


def test_handle_dead_hypervisors3(monitor):
    # dead backoff
    monitor.get_spare_hypervisor = MagicMock()

    sonny.monitor.DEAD_BACKOFF = 1
    monitor.handle_dead_hypervisors(['hv10', 'hv11'])
    monitor.get_spare_hypervisor.assert_not_called()


def test_handle_dead_hypervisors4(monitor):
    # cooldown period active
    monitor.get_spare_hypervisor = MagicMock()

    period = 300
    sonny.monitor.COOLDOWN_PERIOD = period
    last_resurrection = int(time.time()) - period + 10
    monitor.redis.set('resurrection:timestamp', last_resurrection)

    monitor.handle_dead_hypervisors(['hv10'])
    monitor.get_spare_hypervisor.assert_not_called()


def test_run_step1(monitor):
    # get_suspicious_hypervisors(), inspect_hypervisors()

    monitor.get_suspicious_hypervisors = MagicMock()
    monitor.inspect_hypervisors = MagicMock()

    monitor.get_suspicious_hypervisors.return_value = []
    monitor.run_step()
    monitor.inspect_hypervisors.assert_not_called()

    monitor.get_suspicious_hypervisors.return_value = \
        [str(i) for i in range(99)]
    monitor.run_step()
    monitor.inspect_hypervisors.assert_not_called()

    monitor.get_suspicious_hypervisors.return_value = ['hv42']
    monitor.inspect_hypervisors.return_value = (True, [])
    monitor.run_step()
    monitor.inspect_hypervisors.assert_called_once()


def test_run_step2(monitor):
    # inspect_hypervisors(), inspect_instances()

    monitor.get_suspicious_hypervisors = MagicMock()
    monitor.inspect_hypervisors = MagicMock()
    monitor.inspect_instances = MagicMock()

    monitor.get_suspicious_hypervisors.return_value = ['hv42']
    monitor.inspect_instances.return_value = ([], ['hv42'])

    monitor.inspect_hypervisors.return_value = (True, [])
    monitor.run_step()
    monitor.inspect_instances.assert_not_called()

    monitor.inspect_hypervisors.return_value = (True, ['hv42'])
    monitor.run_step()
    monitor.inspect_instances.assert_called_once()


def test_run_step3(monitor):
    # inspect_instances(), handle_dead_hypervisors()

    monitor.get_suspicious_hypervisors = MagicMock()
    monitor.inspect_hypervisors = MagicMock()
    monitor.inspect_instances = MagicMock()
    monitor.handle_dead_hypervisors = MagicMock()

    monitor.get_suspicious_hypervisors.return_value = ['hv42']
    monitor.inspect_hypervisors.return_value = (True, ['hv42'])
    monitor.handle_dead_hypervisors.return_value = 1, 0

    # alive
    monitor.inspect_instances.return_value = ([], ['hv42'])
    monitor.run_step()
    monitor.handle_dead_hypervisors.assert_not_called()

    # dead
    monitor.inspect_instances.return_value = (['hv42'], [])
    monitor.run_step()
    monitor.handle_dead_hypervisors.assert_called_once()
