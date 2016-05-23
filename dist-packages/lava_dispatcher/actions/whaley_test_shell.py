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
            'script': {'type': 'string', 'optional': False},
            'debug': {'type': 'boolean', 'optional': True, 'default': False},
            'case_debug': {'type': 'string', 'optional': True},
        },
        'additionalProperties': False,
    }

    def __init__(self, context):
        super(cmd_whaley_test_shell, self).__init__(context)

    def run(self, script=None, debug=False, case_debug=None):
        # bootloader
        target = self.client.target_device
        # script = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py /home/.../LAVA.json"
        # script_name = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py"
        # script_path = "/home/dqa/workspace/LAVA/android-automation/TAP"
        script = str(script).strip()
        script_name = script.split(' ')[0]
        script_path = os.path.split(script_name)[0]
        logging.info("Script name is: %s", script_name)
        logging.info("Script path is: %s", script_path)
        if os.path.isfile(script_name) and os.path.isdir(script_path):
            current_dir = os.getcwd()
            target_dir = script_path
            logging.info("change dir to %s", target_dir)
            os.chdir(target_dir)
            current_user = os.listdir("/home")[0]
            logging.info("pull the latest code with cmd: sudo -u %s git pull", current_user)
            os.system("sudo -u %s git pull" % current_user)
            os.chdir(current_dir)
            case_json = target.whaley_file_system(script_path, debug, case_debug)
            os.chmod(script_name, XMOD)
            logging.info("run command in file: %s", script_name)
            logging.info("command parameter: %s", case_json)
            script_name = script_name + " " + case_json
            self.context.run_command(script_name)
        else:
            # script invalid, use '/tmp/' instead
            logging.warning("invalid script parameter, use /tmp/ instead")
            target.whaley_file_system('/tmp/', debug, case_debug)

        # reconnect the serial connection
        target.whaley_file_system(script_path, debug, case_debug)
