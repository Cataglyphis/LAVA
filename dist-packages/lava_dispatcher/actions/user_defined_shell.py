#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29

import logging
import subprocess
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
        cwd = os.getcwd()
        # script = "/home/dqa/workspace/android-automation/TAP/whaleyTAP.py"
        # script_path = "/home/dqa/workspace/android-automation/TAP"
        script_name = str(script).strip()
        script_path = os.path.split(script_name)[0]
        script_param = str(parameter).strip()
        logging.info("script name is: %s" % script_name)
        logging.info("script path is: %s" % script_path)
        logging.info("script param is: %s" % script_param)

        # bootloader
        target = self.client.target_device

        if os.path.isfile(script_name):
            os.chdir(script_path)
            self._git_pull()
            git_info = self._git_info(script_path, os.path.basename(script_name))
            logging.info('git info: %s' % git_info)

            if os.path.isfile(script_param):
                case_json = target.whaley_file_system(script_param, git_info)
                os.chmod(script_name, XMOD)
                logging.info('run command in file: %s' % script_name)
                logging.info('command parameter: %s' % case_json)
                script = script_name + ' ' + case_json
                self.context.run_command(script)
            else:
                os.chmod(script_name, XMOD)
                logging.info('run command in file: %s' % script_name)
                logging.info('script parameter: %s' % script_param)
                script = script_name + ' ' + script_param
                self.context.run_command(script)
        else:
            os.chdir(cwd)
            logging.error('invalid script %s' % script)
            raise

        # reconnect the serial connection
        os.chdir(cwd)
        target.reconnect_serial()

    def _git_pull(self):
        current_user = os.listdir('/home')[0]
        logging.info('current user is: %s' % current_user)
        cmd = ['sudo', '-u', current_user, 'git', 'pull']
        logging.info('get the latest code with command %s' % cmd)
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)

    def _git_info(self, gitdir, name):
        cwd = os.getcwd()
        try:
            current_user = os.listdir('/home')[0]
            logging.info('current user is: %s' % current_user)
            os.chdir(gitdir)
            commit_id = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%h']).strip()
            commit_subject = subprocess.check_output(
                ['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%s']).strip()
            commit_author = subprocess.check_output(
                ['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%ae']).strip()
            return {
                'git_name': name,
                'git_revision': commit_id,
                'git_subject': commit_subject,
                'git_author': commit_author
            }
        finally:
            os.chdir(cwd)
