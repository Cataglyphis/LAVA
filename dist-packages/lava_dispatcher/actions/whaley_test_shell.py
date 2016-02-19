#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29

import logging
import stat
import os

from lava_dispatcher.actions import BaseAction

# 755 file permissions
XMOD = stat.S_IRWXU | stat.S_IXGRP | stat.S_IRGRP | stat.S_IXOTH | stat.S_IROTH


class cmd_whaley_test_shell(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'script': {'type': 'string', 'optional': False}
        },
        'additionalProperties': False,
    }

    def __init__(self, context):
        super(cmd_whaley_test_shell, self).__init__(context)

    def run(self, script=None):
        # bootloader
        target = self.client.target_device
        # script: dir of job, shell, deviceInfo
        # script = "/home/to/path/demo.sh"
        # script = "/home/to/path/demo.sh par1 par2"
        # path = "/home/to/path
        path = script.strip().rsplit('/', 1)
        script_name = script.strip().split(' ')[0]
        logging.info("Script path is: %s", path)
        if path != '' and os.path.isdir(path):
            target.whaley_file_system(path)
            if os.path.isfile(script_name):
                # add execute to script_name, and run script with parm
                os.chmod(script_name, XMOD)
                logging.info("Run command in file: %s", script_name)
                self.context.run_command(script)
        else:
            # script invalid, use '/tmp/' instead
            logging.warning("Invalid script parameter, use /tmp/ instead")
            target.whaley_file_system('/tmp/')

        # reconnect the serial connection
        target.whaley_file_system(script)
