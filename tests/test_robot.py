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


def test_inspect_instances():
    assert 0 == 1


def test_suspicious_hypervisors():
    assert 0 == 1


def test_get_spare_hypervisor():
    assert 0 == 1


def test_handle_dead_hypervisor():
    assert 0 == 1


def test_run_step1():
    assert 0 == 1


def test_run_step2():
    assert 0 == 1


def test_run_step3():
    assert 0 == 1
