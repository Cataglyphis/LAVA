# Copyright (C) 2015 Linaro Limited
#
# Author: Stevan Radakovic <stevan.radakovic@linaro.org>
#
# This file is part of lava-scheduler-tool.
#
# lava-scheduler-tool is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# as published by the Free Software Foundation
#
# lava-scheduler-tool is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with lava-scheduler-tool.  If not, see <http://www.gnu.org/licenses/>.

import re


def devicedictionary_to_jinja2(data_dict, extends):
    """
    Formats a DeviceDictionary as a jinja2 string dictionary
    Arguments:
    data_dict: the DeviceDictionary.to_dict()
    extends: the name of the jinja2 device_type template file to extend.
    (including file name extension / suffix) which jinja2 will later
    assume to be in the jinja2 device_types folder
    """
    if type(data_dict) is not dict:
        return None
    data = u'{%% extends \'%s\' %%}\n' % extends
    for key, value in data_dict.items():
        if key == 'extends':
            continue
        data += u'{%% set %s = \'%s\' %%}\n' % (key, value)
    return data


def jinja2_to_devicedictionary(data_dict):
    """
    Do some string mangling to convert the template to a key value store
    The reverse of lava_scheduler_app.utils.devicedictionary_to_jinja2
    """
    if type(data_dict) is not str:
        return None
    data = {}
    for line in data_dict.replace('{% ', '').replace(' %}', '').split('\n'):
        if line == '':
            continue
        if line.startswith('extends'):
            base = line.replace('extends ', '')
            base = base.replace('"', "'").replace("'", '')
            data['extends'] = base
        if line.startswith('set '):
            key = line.replace('set ', '')
            key = re.sub(' = .*$', '', key)
            value = re.sub('^.* = ', '', line)
            value = value.replace('"', "'").replace("'", '')
            data[key] = value
    return data
