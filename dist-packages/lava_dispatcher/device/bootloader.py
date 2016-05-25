# Copyright (C) 2013 Linaro Limited
#
# Author: Tyler Baker <tyler.baker@linaro.org>
#
# This file is part of LAVA Dispatcher.
#
# LAVA Dispatcher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# LAVA Dispatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.


############################################################
# modified by Wang Bo (wang.bo@whaley.cn), 2016.01.15
# add function deploy_whaley_image in class BootloaderTarget
############################################################

import logging
import contextlib
import subprocess
import os
import json

from lava_dispatcher.device.master import (
    MasterImageTarget
)
from lava_dispatcher.client.base import (
    NetworkCommandRunner,
)
from lava_dispatcher.utils import (
    finalize_process,
    connect_to_serial,
    extract_overlay,
    extract_ramdisk,
    create_ramdisk,
    ensure_directory,
    append_dtb,
    create_uimage,
    is_uimage,
)
from lava_dispatcher.errors import (
    CriticalError,
    NetworkError
)

from lava_dispatcher.downloader import (
    download_image,
)
from lava_dispatcher import deployment_data


class BootloaderTarget(MasterImageTarget):

    def __init__(self, context, config):
        super(BootloaderTarget, self).__init__(context, config)
        self._booted = False
        self._reset_boot = False
        self._in_test_shell = False
        self._default_boot_cmds = 'boot_cmds_ramdisk'
        self._lava_nfsrootfs = None
        self._uboot_boot = False
        self._ipxe_boot = False
        self._uefi_boot = False
        self._boot_tags = {}
        self._base_tmpdir, self._tmpdir = self._setup_tmpdir()

    def _get_http_url(self, path):
        prefix = self.context.config.lava_image_url
        return prefix + '/' + self._get_rel_path(path, self._base_tmpdir)

    def _set_load_addresses(self, bootz):
        meta = {}
        if not bootz and self.config.u_load_addrs and len(self.config.u_load_addrs) == 3:
            logging.info("Attempting to set uImage Load Addresses")
            self._boot_tags['{KERNEL_ADDR}'] = self.config.u_load_addrs[0]
            self._boot_tags['{RAMDISK_ADDR}'] = self.config.u_load_addrs[1]
            self._boot_tags['{DTB_ADDR}'] = self.config.u_load_addrs[2]
            # Set boot metadata
            meta['kernel-image'] = 'uImage'
            meta['kernel-addr'] = self.config.u_load_addrs[0]
            meta['initrd-addr'] = self.config.u_load_addrs[1]
            meta['dtb-addr'] = self.config.u_load_addrs[2]
            self.context.test_data.add_metadata(meta)
        elif bootz and self.config.z_load_addrs and len(self.config.z_load_addrs) == 3:
            logging.info("Attempting to set zImage Load Addresses")
            self._boot_tags['{KERNEL_ADDR}'] = self.config.z_load_addrs[0]
            self._boot_tags['{RAMDISK_ADDR}'] = self.config.z_load_addrs[1]
            self._boot_tags['{DTB_ADDR}'] = self.config.z_load_addrs[2]
            # Set boot metadata
            meta['kernel-image'] = 'zImage'
            meta['kernel-addr'] = self.config.z_load_addrs[0]
            meta['initrd-addr'] = self.config.z_load_addrs[1]
            meta['dtb-addr'] = self.config.z_load_addrs[2]
            self.context.test_data.add_metadata(meta)
        else:
            logging.debug("Undefined u_load_addrs or z_load_addrs. Three values required!")

    def _get_uboot_boot_command(self, kernel, ramdisk, dtb):
        bootz = False
        bootx = []

        if is_uimage(kernel, self.context):
            logging.info('Attempting to set boot command as bootm')
            bootx.append('bootm')
        else:
            logging.info('Attempting to set boot command as bootz')
            bootx.append('bootz')
            bootz = True

        # At minimal we have a kernel
        bootx.append('${kernel_addr_r}')

        if ramdisk is not None:
            bootx.append('${initrd_addr_r}')
        elif ramdisk is None and dtb is not None:
            bootx.append('-')

        if dtb is not None:
            bootx.append('${fdt_addr_r}')

        self._set_load_addresses(bootz)

        return ' '.join(bootx)

    def _is_uboot(self):
        if self._uboot_boot:
            return True
        else:
            return False

    def _is_ipxe(self):
        if self._ipxe_boot:
            return True
        else:
            return False

    def _is_uefi(self):
        if self._uefi_boot:
            return True
        else:
            return False

    def _is_bootloader(self):
        if self._is_uboot() or self._is_ipxe() or self._is_uefi():
            return True
        else:
            return False

    def _set_boot_type(self, bootloadertype):
        if bootloadertype == "u_boot":
            self._uboot_boot = True
        elif bootloadertype == 'ipxe':
            self._ipxe_boot = True
        elif bootloadertype == 'uefi':
            self._uefi_boot = True
        else:
            raise CriticalError("Unknown bootloader type")

    ############################################################
    # modified by Wang Bo (wang.bo@whaley.cn), 2016.01.21
    # add function deploy_whaley_image in class BootloaderTarget
    ############################################################

    def deploy_whaley_image(self, image, image_server_ip, rootfstype, bootloadertype):
        if self.__deployment_data__ is None:
            # Get deployment data
            logging.debug("Attempting to set deployment data")
            if self.config.device_type == 'mstar':
                logging.info("Set deployment data to whaley mstar platform")
                self.deployment_data = deployment_data.whaley_mstar
            elif self.config.device_type == 'hisi':
                logging.info("Set deployment data to whaley hisi platform")
                self.deployment_data = deployment_data.whaley_hisi
            else:
                logging.warning("No deployment data, please have a check")
        logging.debug("Set bootloader type to u_boot in whaley platform")
        self._set_boot_type(bootloadertype)
        self._default_boot_cmds = 'boot_cmds'
        if self._is_uboot():
            self._boot_tags['{IMAGE}'] = image
            self._boot_tags['{IMAGE_SERVER_IP}'] = image_server_ip
            logging.info("Set {IMAGE} to %s, and {IMAGE_SERVER_IP} to %s" % (image, image_server_ip))

    def deploy_linaro_kernel(self, kernel, ramdisk, dtb, overlays, rootfs, nfsrootfs, image, bootloader, firmware,
                             bl0, bl1, bl2, bl31, rootfstype, bootloadertype, target_type, qemu_pflash=None):
        if self.__deployment_data__ is None:
            # Get deployment data
            logging.debug("Attempting to set deployment data")
            self.deployment_data = deployment_data.get(target_type)
        else:
            # Reset deployment data
            logging.debug("Attempting to reset deployment data")
            self.power_off(self.proc)
            self.__init__(self.context, self.config)
            # Get deployment data
            self.deployment_data = deployment_data.get(target_type)
        # We set the boot type
        self._set_boot_type(bootloadertype)
        # At a minimum we must have a kernel
        if kernel is None:
            raise CriticalError("No kernel image to boot")
        if self._is_uboot() or self._is_uefi() or self._is_ipxe():
            # Set the server IP (Dispatcher)
            self._boot_tags['{SERVER_IP}'] = self.context.config.lava_server_ip
            # We have been passed kernel image
            kernel = download_image(kernel, self.context,
                                    self._tmpdir, decompress=False)
            if self._is_uboot() or self._is_uefi():
                if self.config.uimage_only and not is_uimage(kernel, self.context):
                    if len(self.config.u_load_addrs) == 3:
                        if self.config.text_offset:
                            load_addr = self.config.text_offset
                        else:
                            load_addr = self.config.u_load_addrs[0]
                        kernel = create_uimage(kernel, load_addr,
                                               self._tmpdir, self.config.uimage_xip)
                        logging.info('uImage created successfully')
                    else:
                        logging.error('Undefined u_load_addrs, aborting uImage creation')
            self._boot_tags['{KERNEL}'] = self._get_rel_path(kernel, self._base_tmpdir)

            if ramdisk is not None:
                # We have been passed a ramdisk
                ramdisk = download_image(ramdisk, self.context,
                                         self._tmpdir,
                                         decompress=False)
                if overlays is not None:
                    ramdisk_dir = extract_ramdisk(ramdisk, self._tmpdir,
                                                  is_uboot=self._is_uboot_ramdisk(ramdisk))
                    for overlay in overlays:
                        overlay = download_image(overlay, self.context,
                                                 self._tmpdir,
                                                 decompress=False)
                        extract_overlay(overlay, ramdisk_dir)
                    ramdisk = create_ramdisk(ramdisk_dir, self._tmpdir)
                if self._is_uboot():
                    # Ensure ramdisk has u-boot header
                    if not self._is_uboot_ramdisk(ramdisk):
                        ramdisk_uboot = ramdisk + ".uboot"
                        logging.info("RAMdisk needs u-boot header.  Adding.")
                        cmd = "mkimage -A arm -T ramdisk -C none -d %s %s > /dev/null" \
                            % (ramdisk, ramdisk_uboot)
                        r = subprocess.call(cmd, shell=True)
                        if r == 0:
                            ramdisk = ramdisk_uboot
                        else:
                            logging.warning("Unable to add u-boot header to ramdisk.  Tried %s", cmd)
                self._boot_tags['{RAMDISK}'] = self._get_rel_path(ramdisk, self._base_tmpdir)
            if dtb is not None:
                # We have been passed a device tree blob
                dtb = download_image(dtb, self.context,
                                     self._tmpdir, decompress=False)
                if self.config.append_dtb:
                    kernel = append_dtb(kernel, dtb, self._tmpdir)
                    logging.info('Appended dtb to kernel image successfully')
                    self._boot_tags['{KERNEL}'] = self._get_rel_path(kernel, self._base_tmpdir)
                else:
                    self._boot_tags['{DTB}'] = self._get_rel_path(dtb, self._base_tmpdir)
            if rootfs is not None:
                # We have been passed a rootfs
                rootfs = download_image(rootfs, self.context,
                                        self._tmpdir, decompress=False)
                self._boot_tags['{ROOTFS}'] = self._get_rel_path(rootfs, self._base_tmpdir)
            if nfsrootfs is not None:
                # Extract rootfs into nfsrootfs directory
                nfsrootfs = download_image(nfsrootfs, self.context,
                                           self._tmpdir,
                                           decompress=False)
                self._lava_nfsrootfs = self._setup_nfs(nfsrootfs, self._tmpdir)
                self._default_boot_cmds = 'boot_cmds_nfs'
                self._boot_tags['{NFSROOTFS}'] = self._lava_nfsrootfs
                if overlays is not None and ramdisk is None:
                    for overlay in overlays:
                        overlay = download_image(overlay, self.context,
                                                 self._tmpdir,
                                                 decompress=False)
                        extract_overlay(overlay, self._lava_nfsrootfs)
            if bootloader is not None:
                # We have been passed a bootloader
                bootloader = download_image(bootloader, self.context,
                                            self._tmpdir,
                                            decompress=False)
                self._boot_tags['{BOOTLOADER}'] = self._get_rel_path(bootloader, self._base_tmpdir)
            if firmware is not None:
                # We have been passed firmware
                firmware = download_image(firmware, self.context,
                                          self._tmpdir,
                                          decompress=False)

                self._boot_tags['{FIRMWARE}'] = self._get_rel_path(firmware, self._base_tmpdir)
            if self._is_uboot():
                self._boot_tags['{BOOTX}'] = self._get_uboot_boot_command(kernel,
                                                                          ramdisk,
                                                                          dtb)

    def deploy_linaro(self, hwpack, rfs, dtb, rootfstype, bootfstype,
                      bootloadertype, qemu_pflash=None):
        self._uboot_boot = False
        super(BootloaderTarget, self).deploy_linaro(hwpack, rfs, dtb,
                                                    rootfstype, bootfstype,
                                                    bootloadertype, qemu_pflash=qemu_pflash)

    def deploy_linaro_prebuilt(self, image, dtb, rootfstype, bootfstype, bootloadertype, qemu_pflash=None):
        self._uboot_boot = False
        if self._is_ipxe():
            if image is not None:
                self._ipxe_boot = True
                # We are not booted yet
                self._booted = False
                # We specify OE deployment data, vanilla as possible
                self.deployment_data = deployment_data.oe
                # We have been passed a image
                image = download_image(image, self.context,
                                       self._tmpdir,
                                       decompress=False)
                image_url = self._get_http_url(image)
                # We are booting an image, can be iso or whole disk
                self._boot_tags['{IMAGE}'] = image_url
            else:
                raise CriticalError("No image to boot")
        else:
            super(BootloaderTarget, self).deploy_linaro_prebuilt(image,
                                                                 dtb,
                                                                 rootfstype,
                                                                 bootfstype,
                                                                 bootloadertype,
                                                                 qemu_pflash=qemu_pflash)

    def _run_boot(self):
        self._load_test_firmware()
        # enter bootloader, 2016.01.21
        self._enter_bootloader(self.proc)
        # add set mac address in bootloader, 2016.04.19
        self._set_macaddr_whaley(self.proc)
        boot_cmds = self._load_boot_cmds(default=self._default_boot_cmds,
                                         boot_tags=self._boot_tags)
        # Sometimes a command must be run to clear u-boot console buffer
        logging.info("boot cmds: %s", boot_cmds)
        if self.config.pre_boot_cmd:
            self.proc.sendline(self.config.pre_boot_cmd,
                               send_char=self.config.send_char)
        self._customize_bootloader(self.proc, boot_cmds)
        self._monitor_boot(self.proc, self.tester_ps1, self.tester_ps1_pattern)

    def _boot_linaro_image(self, skip):
        if self.proc:
            if self.config.connection_command_terminate:
                self.proc.sendline(self.config.connection_command_terminate)
            finalize_process(self.proc)
            self.proc = None
        self.proc = connect_to_serial(self.context)
        # add below part
        # skip=True, only connect to the device, don't reboot & deploy the image
        # skip=False, connect to the device, then reboot to bootloader & deploy the image
        if skip is True:
            self._booted = True
        # bootloader and not booted, 2016.01.21
        if self._is_bootloader() and not self._booted:
            if self.config.hard_reset_command or self.config.hard_reset_command == "":
                self._hard_reboot(self.proc)
                self._run_boot()
            else:
                self._soft_reboot(self.proc)
                self._run_boot()
            self._booted = True
        # bootloader and booted, 2016.01.21
        elif self._is_bootloader() and self._booted:
            self.proc.sendline('export PS1="%s"'
                               % self.tester_ps1,
                               send_char=self.config.send_char)
        else:
            super(BootloaderTarget, self)._boot_linaro_image()

    def is_booted(self):
        return self._booted

    def reset_boot(self, in_test_shell=True):
        self._reset_boot = True
        self._booted = False
        self._in_test_shell = in_test_shell

    # comment at 2015.01.22
    @contextlib.contextmanager
    def file_system(self, partition, directory):
        # whaley
        # partition = 5
        # directory = None
        if self._is_bootloader() and self._reset_boot:
            self._reset_boot = False
            if self._in_test_shell:
                self._in_test_shell = False
                raise Exception("Operation timed out, resetting platform!")
        # bootloader and not booted
        if self._is_bootloader() and not self._booted:
            # self.context.client.boot_linaro_image()
            # reboot the system to the test image
            # if we don't use boot_whaley_image in job, use lava_test_shell directly, then boot the image
            self.context.client.boot_whaley_image()
        # for deploy linaro kernel, pass here
        if self._is_bootloader() and self._lava_nfsrootfs:
            path = '%s/%s' % (self._lava_nfsrootfs, directory)
            ensure_directory(path)
            yield path
        # bootloader
        elif self._is_bootloader():
            # pat = 'TESTER_PS1': "shell@helios:/ # "
            # incrc = 'TESTER_PS1_INCLUDES_RC': False
            pat = self.tester_ps1_pattern
            incrc = self.tester_ps1_includes_rc
            runner = NetworkCommandRunner(self, pat, incrc)
            with self._busybox_file_system(runner, directory) as path:
                yield path
        else:
            with super(BootloaderTarget, self).file_system(
                    partition, directory) as path:
                yield path

    # modify at 2016.02.17
    def whaley_file_system(self, path):
        logging.info("get the target device serial number, ip address and pdu port")
        ##############################################
        # get device telnet port & serial number
        # telnet localhost 2000, etc
        ##############################################
        connection_command = self.config.connection_command
        # port = ['telnet', 'localhost', '2000']
        # port = '2000:', should add ':' here
        port = connection_command.strip().split(" ")[-1] + ":"
        with open("/etc/ser2net.conf", "r") as fin:
            for line in fin.readlines():
                if port in line and not line.startswith("#"):
                    # 2000:telnet:600:/dev/ttyUSB0:115200 8DATABITS NONE 1STOPBIT banner
                    # serial = /dev/ttyUSB0
                    serial = line.split(":")[3]
                    tty = serial.split("/")[-1]
                    break
        port = connection_command.strip().split(" ")[-1]
        logging.info("serial number is: %s" % tty)
        logging.info("telnet number is: %s" % port)

        ##############################################
        # get device ip address info
        ##############################################
        pat = self.tester_ps1_pattern
        incrc = self.tester_ps1_includes_rc
        runner = NetworkCommandRunner(self, pat, incrc)
        try:
            # get the target device ip
            ip = runner.get_target_ip()
        except NetworkError as e:
            raise CriticalError("Network error detected..aborting")

        ##############################################
        # get the pdu port info
        ##############################################
        hard_reset_command = self.config.hard_reset_command
        command = hard_reset_command.strip().split(' ')
        pdu = ''
        if '--port' in command:
            index = command.index('--port')
            pdu = command[index+1]
        logging.info("PDU port number is: %s" % pdu)

        ##############################################
        # get current job id
        ##############################################
        output_dir = self.context.output.output_dir
        if output_dir:
            logging.info("current job output directory: %s" % output_dir)
            job_id = output_dir.strip().split('/')[-1]
            job_id = job_id.split('-')[-1]
        else:
            job_id = "0"

        ##############################################
        # judge whether current device has signal
        ##############################################
        ota = self._get_ota_whaley()
        if ota:
            LAVA_json = os.path.join(path, "plan", "LAVA_OTA.json")
            logging.info("load ota test case: %s", LAVA_json)
        else:
            signal = self._get_signal_whaley()
            if signal:
                LAVA_json = os.path.join(path, "plan", "LAVA_Signal.json")
                logging.info("target device has signal connected: %s", LAVA_json)
            else:
                LAVA_json = os.path.join(path, "plan", "LAVA.json")
                logging.info("target device no signal connected: %s", LAVA_json)

        ##############################################
        # dump info to LAVA.json/LAVA_Signal.json
        ##############################################
        if os.path.isfile(LAVA_json):
            with open(LAVA_json, "r") as fin:
                LAVA_data = json.load(fin)
        else:
            logging.error("no json file found")
            raise

        LAVA_data["device"]["target"] = str(ip) + ":5555"
        LAVA_data["device"]["telnet"] = int(port)
        LAVA_data["device"]["tty"] = str(tty)
        LAVA_data["device"]["pdu"] = str(pdu)
        LAVA_data["device"]["image"] = self.context.job_data.get("job_name")
        if "tags" in self.context.job_data:  # use tags
            LAVA_data["device"]["platform"] = self.context.job_data.get("tags")[0]
        else:  # use target to specify one device
            LAVA_data["device"]["platform"] = self.context.job_data.get("target")
        LAVA_data["device"]["job_id"] = int(job_id)
        LAVA_data["mail"]["subject"] = LAVA_data["mail"]["subject"] + " " + self.context.job_data.get("job_name")

        # LAVA_H01P55D-01.13.00-1616508-65_1255
        result_dir = "LAVA" + "_" + self.context.job_data.get("job_name") + "_" + job_id
        LAVA_dir = os.path.join(path, "testResult", result_dir)
        os.makedirs(LAVA_dir)
        if os.path.isdir(LAVA_dir):
            logging.info("makedirs %s successfully", LAVA_dir)
        else:
            logging.warning("can't makedirs %s, try again", LAVA_dir)
            os.makedirs(LAVA_dir)

        # ../testResult/result_dir/LAVA.json
        case_json = os.path.join(LAVA_dir, "LAVA.json")

        with open(case_json, "w") as fout:
            logging.info("write lava data to json file")
            json.dump(LAVA_data, fout, indent=4)

        logging.warning("disconnect the serial connection, try to run the script")
        if self.config.connection_command_terminate:
            self.proc.sendline(self.config.connection_command_terminate)
        finalize_process(self.proc)
        self.proc = None
        self.context.client.proc = self.proc
        return case_json

    def modify_json(self, script_path, script_param):
        logging.info("get the target device serial number, ip address and pdu port")
        ##############################################
        # get device telnet port & serial number
        # telnet localhost 2000, etc
        ##############################################
        connection_command = self.config.connection_command
        # port = ['telnet', 'localhost', '2000']
        # port = '2000:', should add ':' here
        port = connection_command.strip().split(" ")[-1] + ":"
        with open("/etc/ser2net.conf", "r") as fin:
            for line in fin.readlines():
                if port in line and not line.startswith("#"):
                    # 2000:telnet:600:/dev/ttyUSB0:115200 8DATABITS NONE 1STOPBIT banner
                    # serial = /dev/ttyUSB0
                    serial = line.split(":")[3]
                    tty = serial.split("/")[-1]
                    break
        port = connection_command.strip().split(" ")[-1]
        logging.info("serial number is: %s" % tty)
        logging.info("telnet number is: %s" % port)

        ##############################################
        # get device ip address info
        ##############################################
        pat = self.tester_ps1_pattern
        incrc = self.tester_ps1_includes_rc
        runner = NetworkCommandRunner(self, pat, incrc)
        try:
            # get the target device ip
            ip = runner.get_target_ip()
        except NetworkError as e:
            raise CriticalError("Network error detected..aborting")

        ##############################################
        # get the pdu port info
        ##############################################
        hard_reset_command = self.config.hard_reset_command
        command = hard_reset_command.strip().split(' ')
        pdu = ''
        if '--port' in command:
            index = command.index('--port')
            pdu = command[index + 1]
        logging.info("PDU port number is: %s" % pdu)

        ##############################################
        # get current job id
        ##############################################
        output_dir = self.context.output.output_dir
        if output_dir:
            logging.info("current job output directory: %s" % output_dir)
            job_id = output_dir.strip().split('/')[-1]
            job_id = job_id.split('-')[-1]
        else:
            job_id = "0"

        ##############################################
        # dump info to plan.json
        ##############################################
        if os.path.isfile(script_param):
            with open(script_param, "r") as fin:
                data = json.load(fin)
        else:
            logging.error("no json file found")
            raise

        data["device"]["target"] = str(ip) + ":5555"
        data["device"]["telnet"] = int(port)
        data["device"]["tty"] = str(tty)
        data["device"]["pdu"] = str(pdu)
        data["device"]["image"] = self.context.job_data.get("job_name")
        if "tags" in self.context.job_data:  # use tags
            data["device"]["platform"] = self.context.job_data.get("tags")[0]
        else:  # use target to specify one device
            data["device"]["platform"] = self.context.job_data.get("target")
        data["device"]["job_id"] = int(job_id)
        data["mail"]["subject"] = data["mail"]["subject"] + " " + self.context.job_data.get("job_name")

        # LAVA_H01P55D-01.13.00-1616508-65_1255
        result_dir = "LAVA" + "_" + self.context.job_data.get("job_name") + "_" + job_id
        LAVA_dir = os.path.join(script_path, "testResult", result_dir)
        os.makedirs(LAVA_dir)
        if os.path.isdir(LAVA_dir):
            logging.info("makedirs %s successfully", LAVA_dir)
        else:
            logging.warning("can't makedirs %s, try again", LAVA_dir)
            os.makedirs(LAVA_dir)

        # ../testResult/result_dir/plan.json
        case_json = os.path.join(LAVA_dir, "plan.json")

        with open(case_json, "w") as fout:
            logging.info("write data to json file")
            json.dump(data, fout, indent=4)

        logging.warning("disconnect the serial connection, try to run the script")
        if self.config.connection_command_terminate:
            self.proc.sendline(self.config.connection_command_terminate)
        finalize_process(self.proc)
        self.proc = None
        self.context.client.proc = self.proc
        return case_json

    # modify at 2016.05.25
    def reconnect_serial(self):
        if not self.proc:
            logging.info("reconnect the serial connection")
            self.proc = connect_to_serial(self.context)
            self.context.client.proc = self.proc
            # install busybox, close shutdown again
            self._install_busybox_whaley(self.proc)
            self._close_shutdown_whaley(self.proc)
        else:
            logging.info("no need to reconnect the serial connection")

    # add in 2016.02.17
    # override
    def get_device_version(self):
        logging.info("get device version, ro.build.version.rom")
        self.proc.sendcontrol('c')
        self.proc.sendline('')
        # self.proc.expect('shell', timeout=5)
        self.proc.expect('@', timeout=5)
        # empty the buffer
        self.proc.empty_buffer()
        # self.proc.sendline('getprop ro.helios.version')
        self.proc.sendline('getprop ro.build.version.rom')
        self.proc.expect('@', timeout=2)
        # 'getprop ro.helios.version\r\r\n01.07.01\r\n'
        # 01.07.01
        try:
            device_version = self.proc.before.strip().split('\n')[1].strip()
        except:
            device_version = '0.0.0'
        return device_version

target_class = BootloaderTarget
