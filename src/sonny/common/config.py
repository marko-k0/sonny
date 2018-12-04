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

import configparser

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


def read_and_validate_config(config_file='config.ini'):
    config = configparser.ConfigParser()
    config.read(config_file)

    for section in ['SLACK', 'REDIS', 'MYSQL', 'OPENSTACK']:
        if section not in config.sections():
            raise Exception(f'missing section in config: {section}')

    return config


config = read_and_validate_config()

# DEFAULT
HEARTBEAT_PERIOD = int(config['DEFAULT'].get('heartbeat_period', 40))
COOLDOWN_PERIOD = int(config['DEFAULT'].get('cooldown_period', 86400))
MONITOR_PERIOD = int(config['DEFAULT'].get('monitor_period', 60))
SUSPICIOUS_BACKOFF = int(config['DEFAULT'].get('suspicious_backoff', 5))
DEAD_BACKOFF = int(config['DEFAULT'].get('dead_backoff', 1))

# OPENSTACK
CLOUD = config['OPENSTACK'].get('cloud')
EXT_NET_LIST = config['OPENSTACK'].get('provider_net', 'ext-net').split(',')

# MYSQL
MYSQL_HOST = config['MYSQL'].get('host', None)
MYSQL_USER = config['MYSQL'].get('user', None)
MYSQL_PASS = config['MYSQL'].get('pass', None)

# REDIS
REDIS_HOST = config['REDIS'].get('host')
REDIS_PASS = config['REDIS'].get('pass', None)

# SLACK
SLACK_TOKEN = config['SLACK'].get('token', '')
SLACK_CHANNEL = config['SLACK'].get('channel', '')
CLOUDS = config['SLACK'].get('clouds').split(',')

assert REDIS_HOST is not None
