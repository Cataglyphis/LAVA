# Copyright (C) 2013 Linaro Limited
#
# Author: Milo Casagrande <milo.casagrande@linaro.org>
#
# This file is part of lava-tool.
#
# lava-tool is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# as published by the Free Software Foundation
#
# lava-tool is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with lava-tool.  If not, see <http://www.gnu.org/licenses/>.

"""
Tests for lava.commands.
"""

import os
import tempfile
import sys
import unittest
from cStringIO import StringIO
from mock import (
    MagicMock,
    patch
)

from lava.commands import (
    init,
    submit,
)
from lava_scheduler_tool.commands import compare_device_conf
from lava.config import Config
from lava.helper.tests.helper_test import HelperTest
from lava.tool.errors import CommandError


class InitCommandTests(HelperTest):

    def setUp(self):
        super(InitCommandTests, self).setUp()
        self.config_file = self.tmp("init_command_tests")
        self.config = Config()
        self.config.config_file = self.config_file

    def tearDown(self):
        super(InitCommandTests, self).tearDown()
        if os.path.isfile(self.config_file):
            os.unlink(self.config_file)

    def test_register_arguments(self):
        self.args.DIR = os.path.join(tempfile.gettempdir(), "a_fake_dir")
        init_command = init(self.parser, self.args)
        init_command.register_arguments(self.parser)

        # Make sure we do not forget about this test.
        self.assertEqual(2, len(self.parser.method_calls))

        _, args, _ = self.parser.method_calls[0]
        self.assertIn("--non-interactive", args)

        _, args, _ = self.parser.method_calls[1]
        self.assertIn("DIR", args)

    @patch("lava.commands.edit_file", create=True)
    def test_command_invoke_0(self, mocked_edit_file):
        # Invoke the init command passing a path to a file. Should raise an
        # exception.
        self.args.DIR = self.temp_file.name
        init_command = init(self.parser, self.args)
        self.assertRaises(CommandError, init_command.invoke)

    def test_command_invoke_2(self):
        # Invoke the init command passing a path where the user cannot write.
        try:
            self.args.DIR = "/root/a_temp_dir"
            init_command = init(self.parser, self.args)
            self.assertRaises(CommandError, init_command.invoke)
        finally:
            if os.path.exists(self.args.DIR):
                os.removedirs(self.args.DIR)

    def test_update_data(self):
        # Make sure the template is updated accordingly with the provided data.
        self.args.DIR = self.temp_file.name

        init_command = init(self.parser, self.args)
        init_command.config.get = MagicMock()
        init_command.config.save = MagicMock()
        init_command.config.get.side_effect = ["a_job.json"]

        expected = {
            "jobfile": "a_job.json",
        }

        obtained = init_command._update_data()
        self.assertEqual(expected, obtained)


class SubmitCommandTests(HelperTest):

    def setUp(self):
        super(SubmitCommandTests, self).setUp()
        self.config_file = self.tmp("submit_command_tests")
        self.config = Config()
        self.config.config_file = self.config_file
        self.config.save = MagicMock()

    def tearDown(self):
        super(SubmitCommandTests, self).tearDown()
        if os.path.isfile(self.config_file):
            os.unlink(self.config_file)

    def test_register_arguments(self):
        self.args.JOB = os.path.join(tempfile.gettempdir(), "a_fake_file")
        submit_command = submit(self.parser, self.args)
        submit_command.register_arguments(self.parser)

        # Make sure we do not forget about this test.
        self.assertEqual(2, len(self.parser.method_calls))

        _, args, _ = self.parser.method_calls[0]
        self.assertIn("--non-interactive", args)

        _, args, _ = self.parser.method_calls[1]
        self.assertIn("JOB", args)


class CompareDeviceConfCommandTests(HelperTest):

    def setUp(self):
        super(CompareDeviceConfCommandTests, self).setUp()
        self.config_file = self.tmp("compare_device_conf_command_tests")
        self.config = Config()
        self.config.config_file = self.config_file
        self.args.use_stored = None
        self.args.dispatcher_config_dir = "/etc/lava-server/dispatcher-config/"
        self.temp_yaml = tempfile.NamedTemporaryFile(suffix=".yaml",
                                                     delete=False)

    def tearDown(self):
        super(CompareDeviceConfCommandTests, self).tearDown()
        if os.path.isfile(self.config_file):
            os.unlink(self.config_file)
        os.unlink(self.temp_yaml.name)

    def test_register_arguments(self):
        compare_command = compare_device_conf(self.parser, self.args)
        compare_command.register_arguments(self.parser)

        # Make sure we do not forget about this test.
        self.assertEqual(4, len(self.parser.method_calls))

        _, args, _ = self.parser.method_calls[0]
        self.assertIn("--wdiff", args)

        _, args, _ = self.parser.method_calls[1]
        self.assertIn("--use-stored", args)

        _, args, _ = self.parser.method_calls[2]
        self.assertIn("--dispatcher-config-dir", args)

        _, args, _ = self.parser.method_calls[3]
        self.assertIn("CONFIGS", args)

    def test_command_invoke_0(self):
        # Test that when passing less arguments then expected.
        self.args.CONFIGS = ["non.existing.yaml"]
        compare_command = compare_device_conf(self.parser, self.args)
        result = compare_command.invoke()
        self.assertEqual(result, -1)

    def test_command_invoke_1(self):
        # Test that when passing unexisting file(s).
        self.args.CONFIGS = ["non.existing.yaml", "non.existing2.yaml"]
        compare_command = compare_device_conf(self.parser, self.args)
        result = compare_command.invoke()
        self.assertEqual(result, -1)

    @unittest.skipIf(not os.path.exists('/usr/bin/wdiff'), 'wdiff not installed')
    def test_command_invoke_2(self):
        # Test that when configuration files are identical.
        sys.stdout = output = StringIO()
        self.args.CONFIGS = ["lava/tests/bbb01.example.yaml",
                             "lava/tests/bbb02.example.yaml"]
        compare_command = compare_device_conf(self.parser, self.args)

        result = compare_command.invoke()
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(),
                         "Success. The configuration files are identical.\n")
        sys.stdout = sys.__stdout__

    @unittest.skipIf(not os.path.exists('/etc/lava-server/dispatcher-config/device-types/qemu.yaml'), 'lava-server not configured')
    def test_command_invoke_3(self):
        # Test when configuration files are different.
        sys.stdout = output = StringIO()
        self.args.CONFIGS = ["lava/tests/qemu01.example.yaml",
                             "lava/tests/qemu02.example.yaml"]
        compare_command = compare_device_conf(self.parser, self.args)

        result = compare_command.invoke()
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(),
                         "[--- lava/tests/qemu01.example.yaml-]\n" +
                         "{+++ lava/tests/qemu02.example.yaml+}\n\n" +
                         "@@ -18,8 +18,8 @@\n\n          " +
                         "- -nographic\n          " +
                         "- -enable-kvm\n          " +
                         "- -cpu host\n          " +
                         "- -net [-nic,model=virtio,macaddr=52:54:00:12:34:58-] {+nic,model=virtio,macaddr=15:54:00:12:34:43+} " +
                         "-net user\n          " +
                         "- -m [-512-] {+1024+}\n\ntest_image_prompts:\n  " +
                         "- '(initramfs)'\n")
        sys.stdout = sys.__stdout__
