#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29

import logging
import stat
import os

from lava_dispatcher.actions import BaseAction
from lava_dispatcher.utils import finalize_process, connect_to_serial

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
        target = self.client.target_device
        proc = target.proc
        logging.warning("Disconnect the serial connection, try to run the script")
        if proc:
            finalize_process(proc)
            target.proc = None
        # add 755 file permissions
        os.chmod(script, XMOD)
        logging.info("Run command in file: %s", script)
        self.context.run_command(script)
        logging.warning("Reconnect the serial connection")
        target.proc = connect_to_serial(self.context)
