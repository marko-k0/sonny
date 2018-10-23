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

from unittest.mock import patch

import fakeredis
import json
import sonny.robot as robot

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


def setup_module(module):
    robot.redis = fakeredis.FakeStrictRedis()


def teardown_module(robot):
    pass


def test_db_value():
    with patch.object(robot.Sonny, '__init__', lambda _: None):
        sonny = robot.Sonny()
        sonny.redis = robot.redis

        sonny.redis.set('string', 'string')
        sonny.redis.set('dict', json.dumps({'test': 1}))
        sonny.redis.set('list', json.dumps(['test']))

        assert sonny.get_db_value('missing') is None
        assert sonny.get_db_value('string', str) == 'string'
        assert sonny.get_db_value('dict', json.loads) == {'test': 1}
        assert sonny.get_db_value('list', json.loads) == ['test']


def test_api_alive():
    with patch.object(robot.Sonny, '__init__', lambda _: None):
        sonny = robot.Sonny()
        sonny.redis = robot.redis

        sonny.api_alive = False
        assert sonny.api_alive is False
        sonny.api_alive = True
        assert sonny.api_alive is True
