#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29

import logging
import json
import stat
import os
import re

from lava_dispatcher.actions import BaseAction

# 755 file permissions
XMOD = stat.S_IRWXU | stat.S_IXGRP | stat.S_IRGRP | stat.S_IXOTH | stat.S_IROTH


class cmd_user_defined_shell(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'script': {'type': 'string', 'optional': False},
            'parameter': {'type': 'string', 'optional': False, 'default': ''}
        },
        'additionalProperties': False,
    }

    def __init__(self, context):
        super(cmd_user_defined_shell, self).__init__(context)

    def run(self, script=None, parameter=None):
        script = str(script).strip()
        # script = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py /home/.../plan.json"
        # script_name = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py"
        # script_path = "/home/dqa/workspace/LAVA/android-automation/TAP"
        script_name = str(script).strip()
        script_path = os.path.split(script_name)[0]
        script_param = str(parameter).strip()
        logging.info("script name is: %s", script_name)
        logging.info("script path is: %s", script_path)

        if os.path.isfile(script_name):

            # 1. script_name whaleyTAP.py, and has parameter
            if script_name.endswith("whaleyTAP.py") and script_param:
                self.git_pull(script_path)
                case_json = self.modify_json(script_path, script_param)
                os.chmod(script_name, XMOD)
                logging.info("run command in file: %s", script_name)
                logging.info("command parameter: %s", case_json)
                script = script_name + " " + case_json
                self.context.run_command(script)

            # 2. script_name other values
            else:
                os.chmod(script_name, XMOD)
                logging.info("run command in file: %s", script_name)
                script = script_name + " " + script_param
                self.context.run_command(script)
        else:
            logging.error("invalid script parameter")

    def modify_json(self, script_path, script_param):
        ##############################################
        # get current job id
        ##############################################
        job_id = ""
        output_dir = self.context.output.output_dir
        if output_dir:
            logging.info("current job output directory: %s" % output_dir)
            job_id = output_dir.strip().split('/')[-1]
            job_id = job_id.split('-')[-1]
        else:
            job_id = "0"

        if os.path.isfile(script_param):
            with open(script_param, "r") as fin:
                data = json.load(fin)
        else:
            logging.error("no json file found")
            raise

        data["device"]["job_id"] = int(job_id)
        data["mail"]["subject"] = data["mail"]["subject"] + " " + self.context.job_data.get("job_name")

        # LAVA_job_name_1255
        result_name = "LAVA" + "_" + self.context.job_data.get("job_name") + "_" + job_id
        result_path = os.path.join(script_path, "testResult", result_name)
        os.makedirs(result_path)
        if os.path.isdir(result_path):
            logging.info("makedirs %s successfully", result_path)
        else:
            logging.warning("can't makedirs %s, try again", result_path)
            os.makedirs(result_path)

        # json file for whaleyTAP.py
        case_json = os.path.join(result_path, "plan.json")  # ../testResult/result_dir/plan.json

        with open(case_json, "w") as fout:
            logging.info("write plan data to json file")
            json.dump(data, fout, indent=4)
        return case_json

    def git_pull(self, script_path):
        current_dir = os.getcwd()
        target_dir = script_path
        logging.info("change workspace to %s", target_dir)
        os.chdir(target_dir)
        current_user = os.listdir("/home")[0]
        logging.info("pull the latest code with cmd: sudo -u %s git pull", current_user)
        os.system("sudo -u %s git pull" % current_user)
        os.chdir(current_dir)