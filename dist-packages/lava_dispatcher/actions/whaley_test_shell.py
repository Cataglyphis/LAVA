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
from lava_dispatcher.errors import CriticalError


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
        cwd = os.getcwd()
        if git_repo:
            try:
                gitdir = self._get_git_repo(git_repo, branch, revision)
                with open(os.path.join(gitdir, 'git_info.json'), 'r') as fin:
                    git_info = json.load(fin)
                logging.info('git info: %s' % git_info)
            except Exception:
                os.chdir(cwd)
                logging.error('unable to get test definition from %s' % git_repo)
                raise RuntimeError('unable to get test definition from %s' % git_repo)
        else:
            os.chdir(cwd)
            raise CriticalError('must specify git_repo')

        # bootloader
        target = self.client.target_device
        # testdef = 'TAP/whaleyTAP.py'
        # script_path = '/tmp/xxx/android-automation/TAP/whaleyTAP.py'
        script_name = str(testdef).strip()
        script_path = os.path.join(gitdir, script_name)
        script_param = str(parameter).strip()
        script_param_path = os.path.join(gitdir, script_param)
        logging.info('script path is: %s' % script_path)

        if os.path.isfile(script_path):
            if os.path.isfile(script_param_path):
                logging.info('script param path is: %s' % script_param_path)
                case_json = target.whaley_file_system(script_param_path, git_info)
                os.chmod(script_path, XMOD)
                logging.info('run command in file: %s' % script_name)
                logging.info('command parameter: %s' % case_json)
                script = script_path + ' ' + case_json
                self.context.run_command(script)
            else:
                os.chmod(script_path, XMOD)
                logging.info('run command in file: %s' % script_name)
                logging.info('script parameter: %s' % script_param)
                script = script_path + ' ' + script_param
                self.context.run_command(script)
        else:
            logging.error('invalid script parameter')

        # reconnect the serial connection
        os.chdir(cwd)
        target.reconnect_serial()

    def _get_git_repo(self, git_repo, branch, revision):
        tmpdir = utils.mkdtemp()
        logging.info('clone git-repo and change workspace to %s' % tmpdir)
        os.chdir(tmpdir)
        current_user = os.environ.get('SUDO_USER', '')
        if not current_user:
            current_user = os.environ.get('HOME').split(os.sep)[-1]
        logging.info('current user is: %s' % current_user)
        cmd = ['sudo', '-u', current_user, 'git', 'clone']
        if branch:
            cmd.append('-b')
            cmd.append(branch)
        logging.info('git clone %s with branch %s' % (current_user, branch))
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        name = os.path.splitext(os.path.basename(git_repo))[0]
        logging.info('git_repo name is: %s' % name)
        gitdir = os.path.join(tmpdir, name)
        logging.info('git repo directory name is: %s' % git_repo)
        if revision:
            os.chdir(gitdir)
            subprocess.check_output(['sudo', '-u', current_user, 'git', 'checkout', revision],
                                    stderr=subprocess.STDOUT)
        branch_info = self._git_info(gitdir, name, current_user)
        with open(os.path.join(gitdir, 'git_info.json'), 'w') as fout:
            json.dump(branch_info, fout)
        return gitdir

    def _git_info(self, gitdir, name, current_user):
        cwd = os.getcwd()
        try:
            os.chdir('%s' % gitdir)
            commit_id = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%H']).strip()
            commit_subject = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%s']).strip()
            commit_author = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%ae']).strip()
            return {
                'project_name': name,
                'branch_revision': commit_id,
                'branch_subject': commit_subject,
                'branch_author': commit_author
            }
        finally:
            os.chdir(cwd)
