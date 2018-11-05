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

import fakeredis
import json
import pytest
import sonny.robot as robot
import time

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


def setup_module(module):
    robot.redis = fakeredis.FakeStrictRedis()


def teardown_module(robot):
    pass


@pytest.fixture
def sonny():
    with patch.object(robot.Sonny, '__init__', lambda _: None):
        sonny = robot.Sonny()

        sonny.redis = robot.redis
        sonny.redis.flushall()
        sonny.api_alive = True

        sonny.wait_for_job = MagicMock(return_value=True)

        sonny.refresh_redis_inventory = MagicMock()
        sonny.refresh_redis_inventory.return_value = MagicMock()
        sonny.refresh_redis_inventory.return_value.finished = True

        sonny.inspect_hosts = MagicMock()
        sonny.inspect_hosts.return_value = MagicMock()
        sonny.inspect_hosts.return_value.id = randint(1, 1000000)
        sonny.inspect_hosts.return_value.finished = True
        sonny.inspect_hosts.return_value.result = []

        sonny.recover_instances = MagicMock()
        sonny.recover_instances.return_value = MagicMock()
        sonny.recover_instances.return_value.id = randint(1, 1000000)
        sonny.recover_instances.return_value.finished = True

        return sonny


def test_db_value(sonny):
    sonny.redis.set('string', 'string')
    sonny.redis.set('dict', json.dumps({'test': 1}))
    sonny.redis.set('list', json.dumps(['test']))

    assert sonny.get_db_value('missing') is None
    assert sonny.get_db_value('string', str) == 'string'
    assert sonny.get_db_value('dict', json.loads) == {'test': 1}
    assert sonny.get_db_value('list', json.loads) == ['test']


def test_api_alive(sonny):
    sonny.api_alive = False
    assert sonny.api_alive is False
    sonny.api_alive = True
    assert sonny.api_alive is True


def test_get_instances(sonny):

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

    sonny.redis.set('servers', json.dumps(instance))
    assert sonny.get_instances('hv42') == [('instance1', '10.10.10.10')]
    assert sonny.get_instances('hv43') == []


def test_inspect_hypervisors(sonny):
    assert sonny.inspect_hypervisors(['hv1']) == (True, [])


def test_inspect_instances(sonny):
    u_hvs = ['hv42']
    instances = [(1, '192.168.1.1'), (2, '192.168.1.2'), (3, '192.168.1.3')]
    inspect_returns = [[], ['192.168.1.1'], [ip for _, ip in instances]]
    inspect_instances_returns = [
        ([], ['hv42']), ([], ['hv42']), (['hv42'], [])
    ]

    sonny.get_instances = MagicMock()
    sonny.get_instances.return_value = MagicMock()
    sonny.get_instances.return_value.result = instances
    sonny.inspect_hosts.return_value.args = [ip for _, ip in instances]
    for idx, ret in enumerate(inspect_returns):
        sonny.inspect_hosts.return_value.result = ret
        assert sonny.inspect_instances(u_hvs) == inspect_instances_returns[idx]


def test_suspicious_hypervisors(sonny):
    assert 0 == 1


def test_get_spare_hypervisor(sonny):
    assert 0 == 1


def test_handle_dead_hypervisors1(sonny):
    # successfully handle 2 dead hypervisors
    dead_hvs = ['hv10', 'hv11']

    def get_spare_hv_mock(dead_hv, _):
        return dead_hv + '9'

    def resurrect_instances_mock(*args):
        m = MagicMock()
        m.id = randint(1, 1000000)
        m.args = dead_hvs
        return m

    robot.DEAD_BACKOFF = 2
    sonny.get_db_value = MagicMock(return_value=None)
    sonny.get_spare_hypervisor = MagicMock(side_effect=get_spare_hv_mock)
    sonny.resurrect_instances = MagicMock(side_effect=resurrect_instances_mock)

    assert not sonny.redis.get('resurrection:timestamp')
    assert sonny.handle_dead_hypervisors(dead_hvs) == (2, 0)
    assert sonny.redis.get('resurrection:timestamp')


def test_handle_dead_hypervisors2(sonny):
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

    robot.DEAD_BACKOFF = 2
    sonny.get_db_value = MagicMock(return_value=None)
    sonny.get_spare_hypervisor = MagicMock(side_effect=get_spare_hv_mock)
    sonny.resurrect_instances = MagicMock(side_effect=resurrect_instances_mock)

    assert not sonny.redis.get('resurrection:timestamp')
    assert sonny.handle_dead_hypervisors(dead_spare_hv.keys()) == (1, 1)
    assert sonny.redis.get('resurrection:timestamp')


def test_handle_dead_hypervisors3(sonny):
    # dead backoff
    sonny.get_spare_hypervisor = MagicMock()

    robot.DEAD_BACKOFF = 1
    sonny.handle_dead_hypervisors(['hv10', 'hv11'])
    sonny.get_spare_hypervisor.assert_not_called()


def test_handle_dead_hypervisors4(sonny):
    # cooldown period active
    sonny.get_spare_hypervisor = MagicMock()

    period = 300
    robot.COOLDOWN_PERIOD = period
    last_recovery = int(time.time()) - period + 10
    sonny.get_db_value = MagicMock(return_value=last_recovery)

    sonny.handle_dead_hypervisors(['hv10'])
    sonny.get_spare_hypervisor.assert_not_called()


def test_run_step1(sonny):
    # get_suspicious_hypervisors(), inspect_hypervisors()

    sonny.get_suspicious_hypervisors = MagicMock()
    sonny.inspect_hypervisors = MagicMock()

    sonny.get_suspicious_hypervisors.return_value = []
    sonny.run_step()
    sonny.inspect_hypervisors.assert_not_called()

    sonny.get_suspicious_hypervisors.return_value = [str(i) for i in range(99)]
    sonny.run_step()
    sonny.inspect_hypervisors.assert_not_called()

    sonny.get_suspicious_hypervisors.return_value = ['hv42']
    sonny.inspect_hypervisors.return_value = (True, [])
    sonny.run_step()
    sonny.inspect_hypervisors.assert_called_once()


def test_run_step2(sonny):
    # inspect_hypervisors(), inspect_instances()

    sonny.get_suspicious_hypervisors = MagicMock()
    sonny.inspect_hypervisors = MagicMock()
    sonny.inspect_instances = MagicMock()

    sonny.get_suspicious_hypervisors.return_value = ['hv42']
    sonny.inspect_instances.return_value = ([], ['hv42'])

    sonny.inspect_hypervisors.return_value = (True, [])
    sonny.run_step()
    sonny.inspect_instances.assert_not_called()

    sonny.inspect_hypervisors.return_value = (True, ['hv42'])
    sonny.run_step()
    sonny.inspect_instances.assert_called_once()


def test_run_step3(sonny):
    # inspect_instances(), handle_dead_hypervisors()

    sonny.get_suspicious_hypervisors = MagicMock()
    sonny.inspect_hypervisors = MagicMock()
    sonny.inspect_instances = MagicMock()
    sonny.handle_dead_hypervisors = MagicMock()

    sonny.get_suspicious_hypervisors.return_value = ['hv42']
    sonny.inspect_hypervisors.return_value = (True, ['hv42'])
    sonny.handle_dead_hypervisors.return_value = 1, 0

    # alive
    sonny.inspect_instances.return_value = ([], ['hv42'])
    sonny.run_step()
    sonny.handle_dead_hypervisors.assert_not_called()

    # dead
    sonny.inspect_instances.return_value = (['hv42'], [])
    sonny.run_step()
    sonny.handle_dead_hypervisors.assert_called_once()
