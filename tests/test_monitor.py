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

from unittest.mock import MagicMock

import fakeredis
import pytest
import sonny.monitor as monitor

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


def setup_module():
    monitor.redis = fakeredis.FakeStrictRedis()


def teardown_module():
    pass


def test_refresh_redis_inventory():
    monitor.update_hypervisors_db = MagicMock()
    monitor.update_hypervisors_db.side_effect = Exception('OS API Issue')

    with pytest.raises(Exception):
        monitor.refresh_redis_inventory()

    assert monitor.redis.get('api_alive') == b'False'


def test_nmap_scan_up():
    input = '10.66.0.142'
    output = \
        {'nmap': {'command_line': 'nmap -oX - -p 22 -sV 10.66.0.142',
                  'scaninfo': {'tcp': {'method': 'connect', 'services': '22'}},
                  'scanstats': {'timestr': 'Wed Oct 03 14:26:08 2018',
                                'elapsed': '0.33',
                                'uphosts': '1',
                                'downhosts': '0',
                                'totalhosts': '1'}},
         'scan': {'10.66.0.142': {'hostnames': [{'name': '', 'type': ''}],
                                  'addresses': {'ipv4': '10.66.0.142'},
                                  'vendor': {},
                                  'status': {'state': 'up', 'reason': '...'},
                                  'tcp': {22: {'state': 'open',
                                               'reason': 'syn-ack',
                                               'name': 'ssh',
                                               'product': 'OpenSSH',
                                               'version': '7.4',
                                               'extrainfo': 'protocol 2.0',
                                               'conf': '10',
                                               'cpe': 'cpe:/a:openssh:7.4'}}}}}

    monitor.redis.set('hypervisors', {})
    monitor.nm.scan = MagicMock()
    monitor.nm.scan.return_value = output
    result = monitor.nmap_scan([input])

    assert result == []
    monitor.nm.scan.assert_called_once_with(input, '22')


def test_nmap_scan_down():
    input = '10.66.0.142'
    output = \
        {'nmap': {'command_line': 'nmap -oX - -p 22 -sV 10.66.0.142',
                  'scaninfo': {'tcp': {'method': 'connect', 'services': '22'}},
                  'scanstats': {'timestr': 'Wed Oct 03 14:25:33 2018',
                                'elapsed': '3.22',
                                'uphosts': '0',
                                'downhosts': '1',
                                'totalhosts': '1'}},
         'scan': {}}

    monitor.redis.set('hypervisors', {})
    monitor.nm.scan = MagicMock()
    monitor.nm.scan.return_value = output
    result = monitor.nmap_scan([input])

    assert result == [input]
    monitor.nm.scan.assert_called_once_with(input, '22')
