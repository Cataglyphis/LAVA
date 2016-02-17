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
        if script != '' and os.path.isdir(script):
            target.whaley_file_system(script)
            start = os.path.join(script, 'start.sh')
            if os.path.isfile(start):
                os.chmod(start, XMOD)
                logging.info("Run command in file: %s", start)
                self.context.run_command(start)
        else:
            # script invalid, use '/tmp/' instead
            logging.warning("Invalid script parameter, use /tmp/ instead")
            target.whaley_file_system('/tmp/')

        target.whaley_file_system(script)
