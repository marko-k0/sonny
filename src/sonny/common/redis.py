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

import hashlib
import json
import yaml

from redis import StrictRedis

from sonny.common.config import (
    CLOUD,
    CLOUDS,
    REDIS_HOST,
)

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"
__all__ = ['Redis', 'redis_db', 'redis_value']

_redis = {}


def Redis(cloud=CLOUD):
    db = 0 if not cloud else redis_db(cloud)
    return _redis.setdefault(db, StrictRedis(host=REDIS_HOST, db=db))


def redis_db(cloud=CLOUD):
    return int(hashlib.sha256(cloud.encode('utf-8')).hexdigest(), 16) % 15 + 1


def redis_value(key, value_type=None, cloud=CLOUD):
    value = Redis(CLOUD).get(key)

    if value and value_type is str:
        return value.decode('utf-8')
    elif value and value_type:
        return value_type(value)
    elif value:
        return value
    else:
        return None


def redis_value_show(command, cloud=None):
    cmds = command.split(' ')
    if len(cmds) != 3:
        return 'usage: show {hv name|vm {uuid|name}}'

    clouds = [cloud] if cloud else CLOUDS

    if cmds[1] == 'hv':
        hv = cmds[2]
        if hv.startswith('<'):
            hv = hv.strip('<>').split('|')[1]

        for cloud in clouds:
            hvs = redis_value('hypervisors', json.loads, cloud)
            if hv in hvs:
                return yaml.dump(hvs[hv])
        return 'unknown hypervisor'

    elif cmds[1] == 'vm':
        vm = cmds[2]
        for cloud in clouds:
            vms = redis_value('servers', json.loads, cloud)
            for uuid, v in vms.items():
                if uuid == vm or v['name'] == vm:
                    return yaml.dump(v)
        return 'unknown vm'
