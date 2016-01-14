# Copyright (C) 2010, 2011 Linaro Limited
#
# Author: Michael Hudson-Doyle <michael.hudson@linaro.org>
#
# This file is part of lava-scheduler-tool.
#
# lava-scheduler-tool is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# as published by the Free Software Foundation
#
# lava-scheduler-tool is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with lava-scheduler-tool.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import difflib
import jinja2
import os
import re
import subprocess
import sys
import time
import tempfile
import xmlrpclib
import yaml

from lava_tool.authtoken import AuthenticatingServerProxy, KeyringAuthBackend
from lava.tool.command import Command, CommandGroup
from lava.tool.errors import CommandError
from lava_dashboard_tool.commands import DataSetRenderer, _get_pretty_renderer
from lava_scheduler_tool.scheduler import (
    devicedictionary_to_jinja2,
    jinja2_to_devicedictionary
)


class scheduler(CommandGroup):
    """
    Interact with LAVA Scheduler
    """

    namespace = "lava.scheduler.commands"


class submit_job(Command):
    """
    Submit a job to lava-scheduler
    """

    @classmethod
    def register_arguments(cls, parser):
        super(submit_job, cls).register_arguments(parser)
        parser.add_argument("SERVER")
        parser.add_argument("JSON_FILE")
        parser.add_argument("--block",
                            action="store_true",
                            help="Blocks until the job gets executed")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        if not os.path.exists(self.args.JSON_FILE):
            raise CommandError("No such file: %s" % self.args.JSON_FILE)
        with open(self.args.JSON_FILE, 'rb') as stream:
            command_text = stream.read()
        try:
            job_ids = server.scheduler.submit_job(command_text)
        except xmlrpclib.Fault, e:
            raise CommandError(str(e))
        else:
            if isinstance(job_ids, list):
                print "submitted as job ids:"
                for job_id in job_ids:
                    print " -", job_id
            else:
                print "submitted as job id:", job_ids
                job_ids = [job_ids]

        if self.args.block:
            print('')
            print('Waiting for the job to run ')
            print('. = job waiting in the queue')
            print('# = job running')
            print('')
            for job_id in job_ids:
                print(job_id)
                job = {'job_status': 'Unknown'}
                progress = {'Submitted': '.', 'Running': '#'}
                while job['job_status'] in ['Unknown', 'Submitted', 'Running']:
                    job = server.scheduler.job_status(job_id)
                    sys.stdout.write(progress.get(job['job_status'], ''))
                    sys.stdout.flush()
                    time.sleep(10)  # seconds
                print('')
                print('')
                print('Job Status: %s' % job['job_status'])


class resubmit_job(Command):

    @classmethod
    def register_arguments(self, parser):
        parser.add_argument("SERVER")
        parser.add_argument("JOB_ID")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        try:
            job_id = server.scheduler.resubmit_job(self.args.JOB_ID)
        except xmlrpclib.Fault, e:
            raise CommandError(str(e))
        else:
            print "resubmitted as job id:", job_id


class cancel_job(Command):

    @classmethod
    def register_arguments(self, parser):
        parser.add_argument("SERVER")
        parser.add_argument("JOB_ID")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        server.scheduler.cancel_job(self.args.JOB_ID)


class job_output(Command):
    """
    Get job output from the scheduler.
    """

    @classmethod
    def register_arguments(cls, parser):
        super(job_output, cls).register_arguments(parser)
        parser.add_argument("SERVER")
        parser.add_argument("JOB_ID",
                            help="Job ID to download output file")
        parser.add_argument("--overwrite",
                            action="store_true",
                            help="Overwrite files on the local disk")
        parser.add_argument("--output", "-o",
                            type=argparse.FileType("wb"),
                            default=None,
                            help="Alternate name of the output file")

    def invoke(self):
        if self.args.output is None:
            filename = str(self.args.JOB_ID) + '_output.txt'
            if os.path.exists(filename) and not self.args.overwrite:
                print >> sys.stderr, "File {filename!r} already exists".format(
                    filename=filename)
                print >> sys.stderr, "You may pass --overwrite to write over it"
                return -1
            stream = open(filename, "wb")
        else:
            stream = self.args.output
            filename = self.args.output.name

        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        try:
            stream.write(server.scheduler.job_output(self.args.JOB_ID).data)
            print "Downloaded job output of {0} to file {1!r}".format(
                self.args.JOB_ID, filename)
        except xmlrpclib.Fault as exc:
            print >> sys.stderr, exc
            return -1


class job_status(Command):
    """
    Get job status and bundle sha1, if it existed, from the scheduler.
    """

    @classmethod
    def register_arguments(cls, parser):
        super(job_status, cls).register_arguments(parser)
        parser.add_argument("SERVER")
        parser.add_argument("JOB_ID",
                            help="Job ID to check the status")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        job_status = server.scheduler.job_status(self.args.JOB_ID)

        print "Job ID: %s\nJob Status: %s\nBundle SHA1: %s" % \
            (str(self.args.JOB_ID), job_status['job_status'],
             job_status['bundle_sha1'])


class job_details(Command):
    """
    Get job details, if it existed, from the scheduler.
    """

    @classmethod
    def register_arguments(cls, parser):
        super(job_details, cls).register_arguments(parser)
        parser.add_argument("SERVER")
        parser.add_argument("JOB_ID",
                            help="Job ID to find the details")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        job_details = server.scheduler.job_details(self.args.JOB_ID)

        print "Details of job {0}: \n".format(str(self.args.JOB_ID))
        for detail in job_details:
            print "%s: %s" % (detail, job_details[detail])


class jobs_list(Command):
    """
    Get list of running and submitted jobs from the scheduler.
    """

    renderer = _get_pretty_renderer(
        order=('id', 'description', 'status', 'actual_device', 'requested_device'),
        column_map={
            'id': 'Job ID',
            'description': 'Job description',
            'status': 'Job status',
            'actual_device': 'Device',
            'requested_device': 'Requested device or device type'},
        row_formatter={
            'actual_device': lambda x: x or "",
            'requested_device': lambda x: x or ""},
        empty="There are no running or submitted jobs",
        caption="Jobs list")

    @classmethod
    def register_arguments(cls, parser):
        super(jobs_list, cls).register_arguments(parser)
        parser.add_argument("SERVER")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        jobs_list = server.scheduler.all_jobs()

        data_for_renderer = []
        for row in jobs_list:
            if row[6]:
                job_id = row[6]
            else:
                job_id = row[0]
            if row[4]:
                req_d = row[4]["hostname"]
            else:
                req_d = row[5]["name"]
            if row[3]:
                req_d = ""
                act_d = row[3]["hostname"]
            else:
                act_d = ""
            data_for_renderer.append(dict(zip(['id', 'description', 'status', 'actual_device', 'requested_device'],
                                     [job_id, row[1], row[2], act_d, req_d])))

        self.renderer.render(data_for_renderer)


class devices_list(Command):
    """
    Get list of devices from the scheduler.
    """

    renderer = _get_pretty_renderer(
        order=('hostname', 'device_type_name', 'status', 'job'),
        column_map={
            'hostname': 'Hostname',
            'device_type_name': 'Device type',
            'status': 'Status',
            'job': 'Job ID'},
        row_formatter={
            'job': lambda x: x or ""},
        empty="There are no devices",
        caption="Devices list")

    @classmethod
    def register_arguments(cls, parser):
        super(devices_list, cls).register_arguments(parser)
        parser.add_argument("SERVER")

    def invoke(self):
        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        all_devices = server.scheduler.all_devices()

        data_for_renderer = []
        for row in all_devices:
            if row[3]:
                job_id = row[3]
            else:
                job_id = ""
            data_for_renderer.append(dict(zip(['hostname', 'device_type_name', 'status', 'job'],
                                     [row[0], row[1], row[2], job_id])))

        self.renderer.render(data_for_renderer)


class get_pipeline_device_config(Command):
    """
    Get the pipeline device configuration from scheduler to a local file
    or stdout.
    """

    @classmethod
    def register_arguments(cls, parser):
        super(get_pipeline_device_config, cls).register_arguments(parser)
        parser.add_argument("SERVER",
                            help="Host to download pipeline device config from")
        parser.add_argument("DEVICE_HOSTNAME",
                            help="DEVICE_HOSTNAME to download config file")
        parser.add_argument("--overwrite",
                            action="store_true",
                            help="Overwrite files on the local disk")
        parser.add_argument("--output", "-o",
                            type=argparse.FileType("wb"),
                            default=None,
                            help="Alternate name of the config file")
        parser.add_argument("--stdout",
                            action="store_true",
                            help="Write output to stdout")

    def invoke(self):
        if self.args.output is None and not self.args.stdout:
            filename = str(self.args.DEVICE_HOSTNAME) + '_config.yaml'
            if os.path.exists(filename) and not self.args.overwrite:
                print >> sys.stderr, "File {filename!r} already exists".format(
                    filename=filename)
                print >> sys.stderr, "You may pass --overwrite to write over it"
                return -1
            stream = open(filename, "wb")
        elif self.args.stdout:
            stream = sys.stdout
            filename = "stdout"
        else:
            stream = self.args.output
            filename = self.args.output.name

        server = AuthenticatingServerProxy(
            self.args.SERVER, auth_backend=KeyringAuthBackend())
        try:
            stream.write(server.scheduler.get_pipeline_device_config(
                self.args.DEVICE_HOSTNAME).data)
            print "Downloaded device config of {0} to file {1!r}".format(
                self.args.DEVICE_HOSTNAME, filename)
        except xmlrpclib.Fault as exc:
            print >> sys.stderr, exc
            return -1


class compare_device_conf(Command):
    """
    Compare device config YAML files.
    """

    @classmethod
    def register_arguments(cls, parser):
        super(compare_device_conf, cls).register_arguments(parser)
        parser.add_argument("--wdiff", "-w",
                            action='store_true',
                            help="Use wdiff for parsing output")

        parser.add_argument("--use-stored", "-u",
                            default=None,
                            help="Use stored device config with specified device")
        parser.add_argument("--dispatcher-config-dir",
                            default="/etc/lava-server/dispatcher-config/",
                            help="Where to find the device_type templates.")
        parser.add_argument("CONFIGS",
                            nargs='*',
                            help="List of device config paths, at least one, max two.")

    def invoke(self):

        configs = self.args.CONFIGS

        # Validate number of arguments depending on the options.
        if self.args.use_stored is None:
            if len(self.args.CONFIGS) != 2:
                print >> sys.stderr, "Please input two arguments with config file paths"
                print >> sys.stderr, "You may use --use-stored with one config file path"
                return -1

            for path in self.args.CONFIGS:
                if not os.path.exists(path):
                    print >> sys.stderr, "File {path!r} does not exist".format(
                        path=path)
                    return -1

        else:
            if len(self.args.CONFIGS) != 1:
                print >> sys.stderr, "Please input one argument with config file path"
                print >> sys.stderr, "You may omit --use-stored and use two config file paths"
                return -1

            path = self.args.CONFIGS[0]
            if not os.path.exists(path):
                print >> sys.stderr, "File {path!r} does not exist".format(
                    path=path)
                return -1

            # Run device-dictionary --preview and load it into tmp file.
            args = [
                "lava-server",
                "manage",
                "device-dictionary",
                "--hostname=%s" % self.args.use_stored,
                "--export"
            ]

            config_handle, config_path = tempfile.mkstemp()

            return_code = subprocess.call(
                args,
                stdout=open(config_path, "w")
            )

            if return_code != 0:
                print >> sys.stderr, "Device config for {device!r} doesn't exists".format(device=self.args.use_stored)
                return -1

            configs.append(config_path)

        # Load templates and compare. Current output is classic unified diff.
        device_confs = []
        for path in configs:
            with open(path) as read_file:
                line = read_file.readline()

            if re.search(r'\{%\sextends\s.*%\}', line):
                # First line matches 'extends' regex. Treat it as a template.
                data = self._parse_template(path)
                config = devicedictionary_to_jinja2(
                    data,
                    data['extends']
                )
                string_loader = jinja2.DictLoader({'%s' % path: config})
                type_loader = jinja2.FileSystemLoader([
                    os.path.join(self.args.dispatcher_config_dir,
                                 'device-types')])
                env = jinja2.Environment(
                    loader=jinja2.ChoiceLoader([string_loader, type_loader]),
                    trim_blocks=True)
                template = env.get_template("%s" % path)
                device_configuration = template.render()
                device_confs.append(
                    device_configuration.strip("\n").split("\n"))
            else:
                # 'Extends' not matched. Treat this as a regular config file.
                try:
                    yaml.safe_load(file(path, 'r'))
                except yaml.YAMLError:
                    print "Please provide a valid YAML configuration file."
                    sys.exit(2)

                device_configuration = []
                with open(path) as read_file:
                    device_configuration = [line.strip('\n') for line in read_file.readlines()]

                device_confs.append(device_configuration)

        diff = difflib.unified_diff(device_confs[0], device_confs[1],
                                    fromfile=configs[0],
                                    tofile=configs[1])
        input = [line for line in diff]

        if self.args.wdiff:
            # Pass diff to wdiff for word diff output.
            diff_handle, diff_path = tempfile.mkstemp()

            args = ["wdiff", "-d"]

            proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE
            )
            out, err = proc.communicate("\n".join(input))

            if out:
                print out

        if not self.args.wdiff:
            for line in input:
                print line

        if not input:
            print "Success. The configuration files are identical."

        return 0

    def _parse_template(self, device_file):

        if not os.path.exists(os.path.realpath(device_file)):
            print "Unable to find file '%s'\n" % device_file
            sys.exit(2)
        with open(device_file, 'r') as fileh:
            content = fileh.read()
        return jinja2_to_devicedictionary(content)
