#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29

import logging
import subprocess
import json
import stat
import os

from lava_dispatcher.actions import BaseAction
from lava_dispatcher import utils

# 755 file permissions
XMOD = stat.S_IRWXU | stat.S_IXGRP | stat.S_IRGRP | stat.S_IXOTH | stat.S_IROTH


class cmd_whaley_test_shell(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'git_repo': {'type': 'string', 'optional': False},
            'branch': {'type': 'string', 'optional': True, 'default': 'master'},
            'revision': {'type': 'string', 'optional': True, 'default': ''},
            'testdef': {'type': 'string', 'optional': False},
            'parameter': {'type': 'string', 'optional': False, 'default': ''}
        },
        'additionalProperties': False,
    }

    def __init__(self, context):
        super(cmd_whaley_test_shell, self).__init__(context)

    def run(self, git_repo=None, branch=None, revision=None, testdef=None, parameter=None):
        # clone git with branch, revision
        if git_repo:
            tmpdir = utils.mkdtemp()
            logging.info('clone git-repo and change workspace to %s' % tmpdir)
            os.chdir(tmpdir)
            if isinstance(git_repo, str):
                current_user = os.environ.get('SUDO_USER', '')
                if not current_user:
                    current_user = 'dqa'
                logging.info("sudo -u %s git clone %s" % (current_user, git_repo))
                subprocess.check_output(['sudo', '-u', current_user, 'git', 'clone', git_repo], stderr=subprocess.STDOUT)
                name = gitdir = os.path.splitext(os.path.basename(git_repo))[0]
                self._git_info(gitdir, name)
        else:
            logging.error("must specify git_repo")





        # bootloader
        target = self.client.target_device
        # script = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py"
        # script_path = "/home/dqa/workspace/LAVA/android-automation/TAP"
        # script_param = "/home/dqa/workspace/LAVA/android-automation/TAP/plan/plan.json"
        script_name = str(script).strip()
        script_path = os.path.split(script_name)[0]
        script_param = str(parameter).strip()
        logging.info("script name is: %s", script_name)
        logging.info("script path is: %s", script_path)
        logging.info("script param is: %s", script_param)

        if os.path.isfile(script_name):

            # 1. script_name whaleyTAP.py, and no parameter
            # use LAVA.json or LAVA_Signal.json
            if script_name.endswith("whaleyTAP.py") and not script_param:
                self.git_pull(script_path)
                case_json = target.whaley_file_system(script_path)
                os.chmod(script_name, XMOD)
                logging.info("run command in file: %s", script_name)
                logging.info("command parameter: %s", case_json)
                script = script_name + " " + case_json
                self.context.run_command(script)

            # 2. script_name whaleyTAP.py, and has parameter
            elif script_name.endswith("whaleyTAP.py") and script_param:
                self.git_pull(script_path)
                case_json = target.modify_json(script_path, script_param)
                os.chmod(script_name, XMOD)
                logging.info("run command in file: %s", script_name)
                logging.info("command parameter: %s", case_json)
                script = script_name + " " + case_json
                self.context.run_command(script)

            # 3. script_name other values
            else:
                os.chmod(script_name, XMOD)
                logging.info("run command in file: %s", script_name)
                script = script_name + " " + script_param
                self.context.run_command(script)
        else:
            logging.error("invalid script parameter")

        # reconnect the serial connection
        target.reconnect_serial()

    def git_pull(self, script_path):
        current_dir = os.getcwd()
        target_dir = script_path
        logging.info("change workspace to %s", target_dir)
        os.chdir(target_dir)
        current_user = os.listdir("/home")[0]
        logging.info("pull the latest code with cmd: sudo -u %s git pull", current_user)
        os.system("sudo -u %s git pull" % current_user)
        os.chdir(current_dir)

    def _git_info(self, gitdir, name):
        cwd = os.getcwd()
        try:
            os.chdir('%s' % gitdir)
            commit_id = subprocess.check_output(['git', 'log', '-1', '--pretty=%H']).strip()
            commit_subject = subprocess.check_output(['git', 'log', '-1', '--pretty=%s']).strip()
            return {
                'project_name': name,
                'branch_vcs': 'git',
                'branch_revision': commit_id,
                'branch_subject': commit_subject,
            }
        finally:
            os.chdir(cwd)
