#!/usr/bin/python

import re
from datetime import datetime
from glob import glob
import ast
import base64
import logging
import os
import pexpect
import pkg_resources
import shutil
import stat
import StringIO
import subprocess
import tarfile
import tempfile
import time
import sys
from uuid import uuid4

import yaml

from linaro_dashboard_bundle.io import DocumentIO

from lava_dispatcher.bundle import PrettyPrinter
import lava_dispatcher.lava_test_shell as lava_test_shell
from lava_dispatcher.lava_test_shell import parse_testcase_result
from lava_dispatcher.signals import SignalDirector
from lava_dispatcher import utils

from lava_dispatcher.actions import BaseAction
from lava_dispatcher.downloader import download_image
from lava_dispatcher.errors import GeneralError, CriticalError

import signal
from lava_dispatcher.client.base import NetworkCommandRunner
from lava_dispatcher.errors import (
    CriticalError,
    OperationFailed,
    NetworkError,
)


class cmd_whaley_test_script(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'script': {'type': 'string', 'optional': True}
        },
        'additionalProperties': False,
    }

    @classmethod
    def validate_parameters(cls, parameters):
        super(cmd_whaley_test_script, cls).validate_parameters(parameters)
        if 'script' not in parameters:
            raise ValueError('must specify image in whaley test script')

    def __init__(self, context):
        super(cmd_whaley_test_script, self).__init__(context)

    def run(self, script=None):
        if script is not None:
            logging.info("whaley_test_script: %s", script)

        target = self.client.target_device

        with target.whaley_test() as runner:
            try:
                # get the target device ip
                ip = runner.get_target_ip()
            except NetworkError as e:
                error_detected = True
                raise CriticalError("Network error detected...aborting")

        logging.warning('Kill telnet command, release the serial port')
        proc_telnet = subprocess.Popen(['ps', 'a'], stdout=subprocess.PIPE)
        out, err = proc_telnet.communicate()
        for line in out.splitlines():
            if self.context.device_config.connection_command in line:
                pid = int(line.split()[0])
                logging.warning('kill process: %s', self.context.device_config.connection_command)
                os.kill(pid, signal.SIGKILL)  # SIGKILL for Linux

        logging.info("Execute the script in whaley_test_script")
        self.context.run_command(script)
