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

import fakeredis

__author__ = "Marko Kosmerl"
__copyright__ = "Marko Kosmerl"
__license__ = "gpl3"


class FakeSonnyRedis(fakeredis.FakeStrictRedis):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
