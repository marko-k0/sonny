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
    REDIS_HOST,
)

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


class SonnyRedis(StrictRedis):

    def __init__(self, cloud=None):
        self.__set_db(cloud)
        super().__init__(host=REDIS_HOST, db=self.db)

    @property
    def db(self):
        return self.__db

    def __set_db(self, cloud=None):
        if cloud:
            self.__db = int(hashlib.sha256(
                cloud.encode('utf-8')).hexdigest(), 16) % 15 + 1
        else:
            self.__db = 0

    def get(self, name, value_type=None):
        value = super().get(name)

        if value and value_type is str:
            return value.decode('utf-8')
        elif value and value_type:
            return value_type(value)
        elif value:
            return value
        else:
            return None

    def show(self, command):
        cmds = command.split(' ')

        if cmds[1] == 'hv':
            hv = cmds[2]
            if hv.startswith('<') and hv.endswith('>') and '|' in hv:
                hv = hv.strip('<>').split('|')[1]

            hvs = self.get('hypervisors', json.loads)
            if hv in hvs:
                return yaml.dump(hvs[hv])

        elif cmds[1] == 'vm':
            vm = cmds[2]
            vms = self.get('servers', json.loads)

            for uuid, v in vms.items():
                if uuid == vm or v['name'] == vm:
                    return yaml.dump(v)

        return None
