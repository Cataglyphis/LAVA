#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29

import os
import stat
import logging
import subprocess

import urllib2
import urlparse

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
            'parameter': {'type': 'array', 'optional': True, 'items': {'type': 'string'}},
            'job_url': {'type': 'string', 'optional': True, 'default': ''},
            'job_cycle': {'type': 'string', 'optional': True, 'default': '1'}
        },
        'additionalProperties': False,
    }

    def __init__(self, context):
        super(cmd_whaley_test_shell, self).__init__(context)

    def run(self, git_repo=None, branch=None, revision=None, testdef=None, parameter=None, job_url=None, job_cycle='1'):
        # clone git with branch, revision
        cwd = os.getcwd()
        if git_repo:
            try:
                gitdir, git_info = self._get_git_repo(git_repo, branch, revision)
            except Exception as e:
                os.chdir(cwd)
                logging.info(e)
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
        if job_url:
            logging.info('try to download file from %s' % job_url)
            u = urllib2.urlopen(job_url)
            schema, netloc, path, query, fragment = urlparse.urlsplit(job_url)
            filename = os.path.join(gitdir, os.path.basename(path))
            logging.info('save %s to %s' % (job_url, filename))
            with open(filename, 'wb') as fout:
                meta = u.info()
                meta_func = meta.getheaders if hasattr(meta, 'getheaders') else meta.get_all
                meta_length = meta_func('Content-Length')
                logging.info('file size: %s' % meta_length)
                file_size = None
                if meta_length:
                    file_size = int(meta_length[0])
                file_size_dl = 0
                block_sz = 8192
                while True:
                    buf = u.read(block_sz)
                    if not buf:
                        break
                    file_size_dl += len(buf)
                    fout.write(buf)
                    status = "{0:16}".format(file_size_dl)
                    if file_size:
                        status += "   [{0:6.2f}%]".format(file_size_dl * 100 / file_size)
                    status += chr(13)
                    logging.info('current status: %s' % status)
            if os.path.isfile(filename):
                case_json = target.whaley_file_system(filename, git_info)
            else:
                raise CriticalError('fail to download %s' % filename)
            os.chmod(script_path, XMOD)
            logging.info('run command in file: %s' % script_name)
            logging.info('command parameter: %s' % case_json)
            script = script_path + ' ' + case_json + ' ' + job_cycle
            self.context.run_command(script)
        else:
            script_param = parameter[0].strip()
            script_param_path = os.path.join(gitdir, script_param)
            logging.info('script path is: %s' % script_path)

            if os.path.isfile(script_path):
                if os.path.isfile(script_param_path):
                    logging.info('script param path is: %s' % script_param_path)
                    case_json = target.whaley_file_system(script_param_path, git_info)
                    os.chmod(script_path, XMOD)
                    logging.info('run command in file: %s' % script_name)
                    logging.info('command parameter: %s' % case_json)
                    if len(parameter) == 1:
                        script = script_path + ' ' + case_json
                    else:
                        script = script_path + ' ' + case_json + ' ' + ' '.join(parameter[1:])
                    self.context.run_command(script)
                else:
                    os.chmod(script_path, XMOD)
                    logging.info('run command in file: %s' % script_name)
                    logging.info('script parameter: %s' % script_param)
                    script = script_path + ' ' + ' '.join(parameter[:])
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
        current_user = os.listdir('/home')[0]
        logging.info('current user is: %s' % current_user)
        cmd = ['sudo', '-u', current_user, 'git', 'clone']
        if branch:
            cmd.append('-b')
            cmd.append(branch)
        cmd.append(git_repo)
        logging.info('cmd is: %s' % cmd)
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        name = os.path.splitext(os.path.basename(git_repo))[0]
        logging.info('git_repo name is: %s' % name)
        gitdir = os.path.join(tmpdir, name)
        logging.info('git repo directory name is: %s' % git_repo)
        if revision:
            os.chdir(gitdir)
            subprocess.check_output(['sudo', '-u', current_user, 'git', 'checkout', revision],
                                    stderr=subprocess.STDOUT)
        git_info = self._git_info(gitdir, name, current_user)
        logging.info('git info: %s' % git_info)
        return gitdir, git_info

    def _git_info(self, gitdir, name, current_user):
        cwd = os.getcwd()
        try:
            os.chdir('%s' % gitdir)
            commit_id = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%h']).strip()
            commit_subject = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%s']).strip()
            commit_author = subprocess.check_output(['sudo', '-u', current_user, 'git', 'log', '-1', '--pretty=%ae']).strip()
            return {
                'git_name': name,
                'git_revision': commit_id,
                'git_subject': commit_subject,
                'git_author': commit_author
            }
        finally:
            os.chdir(cwd)
