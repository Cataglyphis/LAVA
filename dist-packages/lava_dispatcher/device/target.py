# -*- coding: utf-8 -*-
# Copyright (C) 2012 Linaro Limited
#
# Author: Andy Doan <andy.doan@linaro.org>
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import contextlib
import os
import shutil
import re
import logging
import time
import pexpect
import subprocess
import json
import lava_dispatcher.utils as utils

from lava_dispatcher.device import boot_options
from lava_dispatcher import deployment_data
from lava_dispatcher.utils import (
    wait_for_prompt
)
from lava_dispatcher.client.lmc_utils import (
    image_partition_mounted
)
from lava_dispatcher.downloader import (
    download_image,
)
from lava_dispatcher.errors import (
    CriticalError,
    OperationFailed,
    NetworkError,
)


class ImagePathHandle(object):

    def __init__(self, image, image_path, config, mount_info):
        if image_path[:5] == "boot:":
            self.part = config.boot_part
            self.part_mntdir = mount_info['boot']
            self.path = image_path[5:]
        elif image_path[:7] == "rootfs:":
            self.part = config.root_part
            self.part_mntdir = mount_info['rootfs']
            self.path = image_path[7:]
        else:
            # FIXME: we can support more patitions here!
            logging.error('The partition we have supported : boot, rootfs. \n\
            And the right image path format is \"<partition>:<path>\".')
            raise CriticalError('Do not support this partition or path format %s yet!' % image_path)

        self.dir_full = os.path.dirname(self.path)
        self.dir_name = os.path.basename(self.dir_full)
        self.file_name = os.path.basename(self.path)
        self.image = image

    def copy_to(self, context, local_path=None):
        # copy file from image to local path
        des_path = None

        # make default local path in the lava
        if local_path is None:
            local_path = utils.mkdtemp(basedir=context.config.lava_image_tmpdir)

        src_path = '%s/%s' % (self.part_mntdir, self.path)
        if not os.path.exists(src_path):
            raise CriticalError('Can not find source in image (%s at part %s)!' % (self.path, self.part))
        if os.path.isdir(src_path):
            if not os.path.exists(local_path):
                des_path = local_path
            else:
                if self.file_name == '':
                    des_name = self.dir_name
                else:
                    des_name = self.file_name
                des_path = os.path.join(local_path, des_name)
            logging.debug("Copying dir from #%s:%s(%s) to %s!", self.part, self.path, src_path, des_path)
            shutil.copytree(src_path, des_path)
        elif os.path.isfile(src_path):
            if not os.path.exists(local_path):
                if os.path.basename(local_path) == '':
                    des_name = os.path.basename(src_path)
                    des_path = os.path.join(local_path, des_name)
                    os.makedirs(local_path)
                else:
                    if not os.path.exists(os.path.dirname(local_path)):
                        os.makedirs(os.path.dirname(local_path))
                    des_path = local_path
            else:
                if os.path.isdir(local_path):
                    des_name = os.path.basename(src_path)
                    des_path = os.path.join(local_path, des_name)
                else:
                    des_path = local_path
            logging.debug("Copying file from #%s:%s(%s) to %s!", self.part, self.path, src_path, des_path)
            shutil.copyfile(src_path, des_path)
        else:
            raise CriticalError('Please check the source file type, we only support file and dir!')

        return des_path

    def copy_from(self, local_path):
        # copy file from local path into image
        src_path = local_path
        if not os.path.exists(src_path):
            raise CriticalError('Can not find source in local server (%s)!' % src_path)

        if os.path.isdir(src_path):
            des_path = '%s/%s' % (self.part_mntdir, self.path)
            if os.path.exists(des_path):
                if os.path.basename(src_path) == '':
                    des_name = os.path.basename(os.path.dirname(src_path))
                else:
                    des_name = os.path.basename(src_path)
                des_path = os.path.join(des_path, des_name)
            logging.debug("Copying dir from %s to #%s:%s(%s)!", des_path, self.part, self.path, src_path)
            shutil.copytree(src_path, des_path)
        elif os.path.isfile(src_path):
            des_path = '%s/%s' % (self.part_mntdir, self.path)
            if not os.path.exists(des_path):
                if os.path.basename(des_path) == '':
                    os.makedirs(des_path)
                    des_name = os.path.basename(src_path)
                    des_path = os.path.join(des_path, des_name)
                else:
                    if not os.path.exists(os.path.dirname(des_path)):
                        os.makedirs(os.path.dirname(des_path))
            else:
                if os.path.isdir(des_path):
                    des_name = os.path.basename(src_path)
                    des_path = os.path.join(des_path, des_name)
            logging.debug("Copying file from %s to #%s:%s(%s)!", des_path, self.part, self.path, src_path)
            shutil.copyfile(src_path, des_path)
        else:
            raise CriticalError('Please check the source file type, we only support file and dir!')

        return des_path

    def remove(self):
        # delete the file/dir from Image
        des_path = '%s/%s' % (self.part_mntdir, self.path)
        if os.path.isdir(des_path):
            logging.debug("Removing dir(%s) %s from #%s partition of image!", des_path, self.path, self.part)
            shutil.rmtree(des_path)
        elif os.path.isfile(des_path):
            logging.debug("Removing file(%s) %s from #%s partition of image!", des_path, self.path, self.part)
            os.remove(des_path)
        else:
            logging.warning('Unrecognized file type or file/dir doesn\'t exist(%s)! Skipped', des_path)


def get_target(context, device_config):
    ipath = 'lava_dispatcher.device.%s' % device_config.client_type
    m = __import__(ipath, fromlist=[ipath])
    return m.target_class(context, device_config)


class Target(object):
    """ Defines the contract needed by the dispatcher for dealing with a
    target device
    """

    def __init__(self, context, device_config):
        self.context = context
        self.config = device_config
        self.boot_options = []
        self._scratch_dir = None
        self.__deployment_data__ = None
        self.mount_info = {'boot': None, 'rootfs': None}
        self._bridge_configured = False
        # add by Bo, at 2016.06.29
        self._image_params = None
        self._boot_params = None

    @property
    def deployment_data(self):
        if self.__deployment_data__:
            return self.__deployment_data__
        else:
            raise RuntimeError("No operating system deployed. "
                               "Did you forget to run a deploy action?")

    @deployment_data.setter
    def deployment_data(self, data):
        self.__deployment_data__ = data

    @property
    def scratch_dir(self):
        if self._scratch_dir is None:
            self._scratch_dir = utils.mkdtemp(
                self.context.config.lava_image_tmpdir)
        return self._scratch_dir

    # deploy_whaley_image parameters
    @property
    def image_params(self):
        job_data = self.context.job_data
        if self._image_params is None:
            for cmd in job_data['actions']:
                if cmd.get('command') == 'deploy_whaley_image':
                    self._image_params = cmd.get('parameters', {})
        return self._image_params

    # boot_whaley_image parameters
    @property
    def boot_params(self):
        job_data = self.context.job_data
        if self._boot_params is None:
            for cmd in job_data['actions']:
                if cmd.get('command') == 'boot_whaley_image':
                    self._boot_params = cmd.get('parameters', {})
        return self._boot_params

    def power_on(self):
        """ responsible for powering on the target device and returning an
        instance of a pexpect session
        """
        raise NotImplementedError('power_on')

    def deploy_linaro(self, hwpack, rfs, dtb, rootfstype, bootfstype,
                      bootloadertype, qemu_pflash=None):
        raise NotImplementedError('deploy_image')

    def deploy_android(self, images, rootfstype,
                       bootloadertype, target_type):
        raise NotImplementedError('deploy_android_image')

    def deploy_linaro_prebuilt(self, image, dtb, rootfstype, bootfstype,
                               bootloadertype, qemu_pflash=None):
        raise NotImplementedError('deploy_linaro_prebuilt')

    def deploy_linaro_kernel(self, kernel, ramdisk, dtb, overlays, rootfs, nfsrootfs, image, bootloader, firmware, bl0, bl1,
                             bl2, bl31, rootfstype, bootloadertype, target_type, qemu_pflash=None):
        raise NotImplementedError('deploy_linaro_kernel')

    def dummy_deploy(self, target_type):
        pass

    def power_off(self, proc):
        if proc is not None:
            proc.close()
        if self.config.bridged_networking and self._bridge_configured:
            self._teardown_network_bridge(self.config.bridge_interface, self._interface_name)

    def is_booted(self):
        # By default we pass
        pass

    def reset_boot(self, in_test_shell=True):
        # By default we pass
        pass

    @contextlib.contextmanager
    def file_system(self, partition, directory):
        """ Allows the caller to interact directly with a directory on
        the target. This method yields a directory where the caller can
        interact from. Upon the exit of this context, the changes will be
        applied to the target.

        The partition parameter refers to partition number the directory
        would reside in as created by linaro-media-create. ie - the boot
        partition would be 1. In the case of something like the master
        image, the target implementation must map this number to the actual
        partition its using.

        NOTE: due to difference in target implementations, the caller should
        try and interact with the smallest directory locations possible.
        """
        raise NotImplementedError('file_system')

    def extract_tarball(self, tarball_url, partition, directory='/'):
        """ This is similar to the file_system API but is optimized for the
        scenario when you just need explode a potentially large tarball on
        the target device. The file_system API isn't really suitable for this
        when thinking about an implementation like master.py
        """
        raise NotImplementedError('extract_tarball')

    def get_test_data_attachments(self):
        return []

    def get_device_version(self):
        """ Returns the device version associated with the device, i.e. version
        of emulation software, or version of master image. Must be overriden in
        subclasses.
        """
        return 'unknown'

    def _copy_first_find_from_list(self, subdir, odir, file_list, rename=None):
        f_path = None
        for fname in file_list:
            f_path = self._find_and_copy(subdir, odir, fname, rename)
            if f_path:
                break

        return f_path

    def _find_and_copy(self, rootdir, odir, pattern, name=None):
        dest = None
        for root, dirs, files in os.walk(rootdir, topdown=False):
            for file_name in files:
                if re.match(pattern, file_name):
                    src = os.path.join(root, file_name)
                    logging.info('Loading file: %s', src)
                    if name is not None:
                        dest = os.path.join(odir, name)
                        new_src = os.path.join(root, name)
                    else:
                        dest = os.path.join(odir, file_name)
                    if src != dest:
                        if name is not None:
                            shutil.copyfile(src, dest)
                            shutil.move(src, new_src)
                        else:
                            shutil.copyfile(src, dest)
                        return dest
                    else:
                        if name is not None:
                            shutil.move(src, new_src)
                        return dest
        return dest

    def _find_file(self, rootdir, pattern):
        dest = None
        for root, dirs, files in os.walk(rootdir, topdown=False):
            for file_name in files:
                if re.match(pattern, file_name):
                    logging.debug("Found a match: %s" % file_name)
                    dest = os.path.join(root, file_name)
                    return dest
        return dest

    def _find_dir(self, rootdir, pattern):
        dest = None
        for root, dirs, files in os.walk(str(rootdir), topdown=False):
            for dir_name in dirs:
                dir_name = str(dir_name)
                root = str(root)
                if re.match(pattern, dir_name):
                    dest = os.path.join(root, dir_name)
                    return dest
        return dest

    def _wait_for_prompt(self, connection, prompt_pattern, timeout):
        wait_for_prompt(connection, prompt_pattern, timeout)

    def _is_job_defined_boot_cmds(self, boot_cmds):
        if isinstance(self.config.boot_cmds, basestring):
            return False
        else:
            return True

    def _image_has_selinux_support(self, runner, timeout):
        # rc = runner.run("LANG=C tar --help 2>&1 | grep selinux", failok=True)
        # add below 2 lines, 2016.01.22
        rc = runner.run("LANG=C busybox tar --help 2>&1 | grep selinux", failok=True, timeout=timeout)
        logging.info("image_has_selinux_support: %s" % rc)
        if rc >= 1:
            logging.info("SELinux support disabled in test image. The current image has no selinux support in 'tar'.")
            return False
        elif rc is None:
            logging.info("No SELinux support in test image. The Current image has no selinux support in 'tar'.")
            return False
        else:
            logging.debug("Retaining SELinux support in the current image.")
            return True

    # judge current state, and skip guide
    def _skip_guide_whaley(self, connection):
        pattern = ["Can't find service", "com.helios.guide", "com.helios.launcher", "com.whaley.tv.tvplayer.ui", pexpect.TIMEOUT]
        for i in range(10):
            logging.info('try to skip the guide. attempt: %s' % str(i+1))
            connection.empty_buffer()
            connection.sendcontrol('c')
            connection.expect(['shell@', 'root@', pexpect.TIMEOUT], timeout=20)
            connection.sendline('dumpsys window | grep mFocusedApp', send_char=self.config.send_char)
            pos1 = connection.expect(pattern, timeout=10)
            if pos1 == 0:
                logging.warning("can't find service: window")
                time.sleep(100)
                continue
            elif pos1 == 1:
                logging.info('now in com.helios.guide activity')
                time.sleep(80)
                connection.sendcontrol('c')
                connection.expect(['shell@', 'root@', pexpect.TIMEOUT], timeout=5)
                connection.sendline('su', send_char=self.config.send_char)
                connection.sendline('am start -n com.helios.launcher/.LauncherActivity', send_char=self.config.send_char)
                time.sleep(20)
                connection.sendline('dumpsys window | grep mFocusedApp', send_char=self.config.send_char)
                pos2 = connection.expect(pattern, timeout=10)
                if pos2 == 2:
                    logging.info('now in com.helios.launcher activity, skip the guide successfully')
                    break
                else:
                    logging.info("can't skip the guide, try it again")
            elif pos1 == 2:
                logging.info('already in com.helios.launch activity')
                break
            elif pos1 == 3:
                logging.info('already in com.whaley.tv.tvplayer.ui activity')
                break
            else:
                time.sleep(100)
                continue
        else:
            logging.error("can't skip the guide, please have a check")
            self.context.test_data.add_result('skip_guide_whaley', 'fail')

    # install busybox in /system/xbin
    def _install_busybox_whaley(self, connection):
        logging.info('install busybox in /system/xbin')
        connection.sendline('su', send_char=self.config.send_char)
        connection.sendline('mount -o remount,rw /system', send_char=self.config.send_char)
        connection.sendline('cd /system/xbin', send_char=self.config.send_char)
        connection.sendline('busybox --install .', send_char=self.config.send_char)
        image = self.image_params.get('image', '')
        if 'R' in image:
            logging.info('download sqlite3 to /system/xbin')
            if self.config.device_type == 'mstar':
                connection.sendline('busybox wget -O sqlite3 http://172.16.117.1:8000/resource/sqlite3', send_char=self.config.send_char)
            elif self.config.device_type == 'hisi':
                connection.sendline('busybox wget -O sqlite3 http://172.16.117.1:8000/resource/sqlite3_hisi', send_char=self.config.send_char)
            time.sleep(5)
            connection.sendline('busybox chmod 755 sqlite3', send_char=self.config.send_char)
        # go back to /, otherwise block the next step in whaley_test_shell
        connection.sendline('cd /', send_char=self.config.send_char)
        connection.empty_buffer()
        logging.info('end installation of busybox')

    # set vip account
    def _set_vip_whaley(self, connection):
        logging.info('set vip info')
        connection.sendline('cd /data/local/tmp', send_char=self.config.send_char)
        connection.sendline('su', send_char=self.config.send_char)
        connection.sendline('busybox wget -O TvUiTools.jar http://172.16.117.1:8000/resource/media/TvUiTools.jar', send_char=self.config.send_char)
        time.sleep(5)
        connection.sendline('input keyevent 21', send_char=self.config.send_char)
        time.sleep(5)
        connection.empty_buffer()
        connection.sendline('uiautomator runtest TvUiTools.jar -c com.whaley.viplogin.testcases.AutoLoginTestCase#testAutoLogin', send_char=self.config.send_char)
        connection.expect(['shell@', 'root@', pexpect.TIMEOUT])
        logging.info('back to home page')
        connection.sendline('input keyevent 3', send_char=self.config.send_char)
        connection.sendline('cd /', send_char=self.config.send_char)
        connection.empty_buffer()
        logging.info('end setting vip info')

    # set logctl
    def _set_logctl_whlay(self, connection):
        logging.info('set logctl file to /data/local/tmp/log')
        connection.sendline('cd /data/local/tmp', send_char=self.config.send_char)
        connection.sendline('su')
        connection.sendline('mkdir log')
        connection.sendline('chmod 777 log')
        connection.sendline('setprop persist.svc.logctl.file /data/local/tmp/log/logcat.log')
        connection.sendline('setprop persist.svc.logctl.size 10000')
        connection.sendline('setprop persist.service.logcat.enable true')
        connection.sendline('stop logctl')
        connection.sendline('getprop | grep logctl')
        connection.sendline('start logctl')
        connection.sendline('cd /', send_char=self.config.send_char)
        connection.empty_buffer()
        logging.info('end set logctl file')

    # display /mnt/usb/sda1/多媒体
    def _display_usb_whaley(self, connection):
        logging.info('display /mnt/usb/sdx/多媒体 info')
        connection.sendline('su')
        connection.expect(['shell@', 'root@', pexpect.TIMEOUT])
        connection.sendline('for usb in `ls /mnt/usb`; do busybox du -sh /mnt/usb/$usb/多媒体; busybox ls -lh /mnt/usb/$usb/多媒体; done')
        connection.expect(['shell@', 'root@', pexpect.TIMEOUT])
        connection.empty_buffer()
        logging.info('end display /mnt/usb/sdx/多媒体 info')

    # remove helios guide, so after reboot no guide appear
    def _remove_helios_guide(self, connection):
        logging.info('remove helios guide')
        connection.sendline('su', send_char=self.config.send_char)
        connection.sendline('rm -rf /data/dalvik-cache/arm/system@priv-app@HeliosGuide@HeliosGuide.apk@classes.dex', send_char=self.config.send_char)
        connection.sendline('mount -o remount,rw /system', send_char=self.config.send_char)
        connection.sendline('rm -rf /system/priv-app/HeliosGuide', send_char=self.config.send_char)
        if self.config.device_type == 'mstar-938':
            connection.sendline("busybox sed -i 's/name=\"user_setup_complete\" value=\"0\"/name=\"user_setup_complete\" value=\"1\"/g' /data/system/users/0/settings_secure.xml",
                                send_char=self.config.send_char)
        connection.empty_buffer()
        logging.info('end remove helios guide')

    # close shutdown
    def _close_shutdown_whaley(self, connection):
        logging.info('modify hardwareprotect.db, set shutdown time to -1')
        connection.sendline("sqlite3 /data/system/hardwareprotect.db \"update hwprotect set timeout=-1 where name='shutdown'\"", send_char=self.config.send_char)
        logging.info('end modify hardwareprotect.db')

    # burn su image to tvinfo
    def _burn_su_image(self, connection):
        connection.expect(self.config.interrupt_boot_prompt, timeout=self.config.image_boot_msg_timeout)
        logging.info('current deploy image is Release version, should enable console and su')
        if 'mstar' in self.config.device_type:  # mstar/mstar-938
            for i in range(10):
                connection.sendline('')
            # << MStar >>#
            connection.expect(self.config.bootloader_prompt)
            # clear connection buffer
            connection.empty_buffer()
            # burn su image
            logging.info('use 172.16.10.41 for su image, and burun su.img to tvinfo')
            connection.sendline('setenv serverip 172.16.10.41', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('estart')
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('dhcp')
            connection.expect(self.config.bootloader_prompt, timeout=100)
            if self.config.device_type == 'mstar':
                connection.sendline('mstar su/mstar', send_char=self.config.send_char)
            elif self.config.device_type == 'mstar-938':
                connection.sendline('mstar su/mstar_938', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt, timeout=600)
        elif self.config.device_type == 'hisi':
            try:
                if self.config.hard_reset_command != '':
                    self.context.run_command(self.config.power_off_cmd)
                    time.sleep(20)
                    self.context.run_command(self.config.power_on_cmd)
                    connection.expect(self.config.interrupt_boot_prompt, timeout=20)
                    for i in range(50):
                        connection.sendline('')
                        time.sleep(0.1)
                else:
                    for i in range(50):
                        connection.sendline('')
                        time.sleep(0.1)
                connection.expect(self.config.bootloader_prompt)
            except pexpect.TIMEOUT:
                msg = 'Infrastructure Error: failed to enter the bootloader.'
                logging.error(msg)
                raise
            # clear connection buffer
            connection.empty_buffer()
            # burn su.ext4.gz image
            logging.info("use 172.16.10.41 for su image, and buru su.ext4.gz to tvinfo")
            connection.sendline('setenv serverip 172.16.10.41', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('exec su/hisi', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt, timeout=600)
        else:
            logging.warning('no device type mstar or hisi found')
        logging.info('end of burn su image to tvinfo')

    # enter recovery mode
    def _enter_recovery_whaley(self, connection):
        logging.info('enter recovery mode')
        # clear connection buffer
        connection.empty_buffer()
        if self.config.device_type == 'mstar' or self.config.device_type == 'mstar-938':
            connection.sendline('ac androidboot.debuggable 1', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('recovery', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('reset', send_char=self.config.send_char)
            connection.expect('/ #', timeout=150)
            time.sleep(15)
        elif self.config.device_type == 'hisi':
            connection.sendline('ufts set fts.fac.factory_mode 0', send_char=self.config.send_char)
            connection.sendline('ufts set fts.boot.command boot-recovery', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('ufts set fts.boot.status', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('ufts set fts.boot.recovery', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.sendline('reset', send_char=self.config.send_char)
            connection.expect('StartGUI', timeout=150)
            time.sleep(15)
        else:
            logging.warning('no device type mstar or hisi found')
        connection.empty_buffer()
        logging.info('end of enter recovery mode')

    # su device in recovery mode
    def _su_device_whaley(self, connection):
        logging.info('su device in recovery mode')
        connection.sendcontrol('c')
        connection.expect('/ #')
        connection.sendline('busybox --install /sbin', send_char=self.config.send_char)
        connection.sendline('busybox mkdir /tmp/disk', send_char=self.config.send_char)
        if self.config.device_type == 'mstar' or self.config.device_type == 'mstar-938':
            tvinfo = '/dev/block/platform/mstar_mci.0/by-name/tvinfo'
            connection.sendline('busybox mount %s /tmp/disk' % tvinfo, send_char=self.config.send_char)
        elif self.config.device_type == 'hisi':
            tvinfo = '/dev/block/platform/hi_mci.1/by-name/tvinfo'
            connection.sendline('busybox mount %s /tmp/disk' % tvinfo, send_char=self.config.send_char)
        else:
            logging.warning('no device type mstar or hisi found')
        connection.sendline('busybox ls /tmp/disk', send_char=self.config.send_char)
        connection.sendline('cd /tmp/disk/su', send_char=self.config.send_char)
        connection.sendline('busybox ls /tmp/disk/su', send_char=self.config.send_char)
        connection.sendline('busybox chmod 755 su_install.sh', send_char=self.config.send_char)
        connection.sendline('busybox sh su_install.sh', send_char=self.config.send_char)
        time.sleep(5)
        connection.sendline('busybox reboot -f')
        connection.empty_buffer()
        logging.info('end su device in recovery mode')

    # get current device mac address
    def _get_macaddr_whaley(self):
        mac_addr = self.config.macaddr
        logging.info('mac address: %s' % mac_addr)
        return mac_addr

    # get current device sn
    def _get_sn_whaley(self):
        sn = self.config.sn
        logging.info('sn: %s' % sn)
        return sn

    # set mac address in bootloader
    def _set_macaddr_whaley(self, connection):
        logging.info('set mac address and bootdelay in bootloader')
        mac_addr = self._get_macaddr_whaley()
        # device_type = self.context.job_data['device_type']
        # if we define target parameter in job json, no job_data['device_type'] found
        # use self.config.device_type to replace job_data['device_type']
        device_type = self.config.device_type
        if device_type == 'mstar' or device_type == 'mstar-938':
            connection.sendline('setenv ethaddr %s' % mac_addr, send_char=self.config.send_char)
            connection.sendline('setenv macaddr %s' % mac_addr, send_char=self.config.send_char)
            connection.sendline('setenv bootdelay 10', send_char=self.config.send_char)
            connection.sendline('saveenv', send_char=self.config.send_char)
            connection.expect('done')
            connection.empty_buffer()
        elif device_type == 'hisi':
            connection.sendline('setenv ethaddr %s' % mac_addr, send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
            connection.empty_buffer()
        else:
            logging.warning('no device type mstar or hisi found')
        logging.info('end set mac address and bootdelay in bootloader')

    # set factory info, e.g. mac address, sn
    # then reboot the device
    def _set_factory_whaley(self, connection):
        logging.info('set factory mode info')
        mac_addr = self._get_macaddr_whaley()
        sn = self._get_sn_whaley()
        connection.sendline('su', send_char=self.config.send_char)
        connection.sendline('mount -o remount,rw /factory', send_char=self.config.send_char)
        if mac_addr:
            connection.sendline('echo ro.hardware.lan_mac=%s >> /factory/factory.prop' % mac_addr, send_char=self.config.send_char)
        if sn:
            # connection.sendline('echo ro.helios.sn=%s >> /factory/factory.prop' % sn, send_char=self.config.send_char)
            connection.sendline('echo ro.device.serialno=%s >> /factory/factory.prop' % sn, send_char=self.config.send_char)
        connection.sendline('chmod 644 /factory/factory.prop', send_char=self.config.send_char)
        logging.info('end set factory mode info')

    def _auto_login(self, connection, is_master=False):
        if is_master:
            if self.config.master_login_prompt is not None:
                self._wait_for_prompt(connection,
                                      self.config.master_login_prompt,
                                      timeout=self.config.boot_linaro_timeout)
                connection.sendline(self.config.master_username)
            if self.config.master_password_prompt is not None:
                self._wait_for_prompt(connection,
                                      self.config.master_password_prompt, timeout=10)
                connection.sendline(self.config.master_password)
            if self.config.master_login_commands is not None:
                for command in self.config.master_login_commands:
                    connection.sendline(command)
        else:
            if self.config.login_prompt is not None:
                self._wait_for_prompt(connection,
                                      self.config.login_prompt,
                                      timeout=self.config.boot_linaro_timeout)
                connection.sendline(self.config.username)
            if self.config.password_prompt is not None:
                self._wait_for_prompt(connection,
                                      self.config.password_prompt, timeout=10)
                connection.sendline(self.config.password)
            if self.config.login_commands is not None:
                for command in self.config.login_commands:
                    connection.sendline(command)

    def _is_uboot_ramdisk(self, ramdisk):
        try:
            out = subprocess.check_output('mkimage -l %s' % ramdisk, shell=True).splitlines()
        except subprocess.CalledProcessError:
            return False

        for line in out:
            if not line.startswith('Image Type:'):
                continue
            key, val = line.split(':')
            if val.find('RAMDisk') > 0:
                return True

        return False

    def _get_rel_path(self, path, base):
        return os.path.relpath(path, base)

    def _setup_nfs(self, nfsrootfs, tmpdir):
        lava_nfsrootfs = utils.mkdtemp(basedir=tmpdir)
        utils.extract_rootfs(nfsrootfs, lava_nfsrootfs)
        return lava_nfsrootfs

    def _setup_tmpdir(self):
        if not self.config.use_lava_tmpdir:
            if self.config.alternative_dir is None:
                logging.error("You have specified not to use the LAVA temporary \
                              directory. However, you have not defined an \
                              alternate temporary directory. Falling back to \
                              use the LAVA temporary directory.")
                return self.context.config.lava_image_tmpdir, self.scratch_dir
            else:
                if self.config.alternative_create_tmpdir:
                    return self.config.alternative_dir, utils.mkdtemp(self.config.alternative_dir)
                else:
                    return self.config.alternative_dir, self.config.alternative_dir
        else:
            return self.context.config.lava_image_tmpdir, self.scratch_dir

    def _load_boot_cmds(self, default=None, boot_cmds_dynamic=None,
                        boot_tags=None):
        # Set flags
        boot_cmds_job_file = False
        boot_cmds_boot_options = False
        master_boot = False

        # Set the default boot commands
        if default is None:
            boot_cmds = self.deployment_data['boot_cmds']
        else:
            boot_cmds = default

        # Check for job defined boot commands
        if boot_cmds != 'boot_cmds_master':
            boot_cmds_job_file = self._is_job_defined_boot_cmds(self.config.boot_cmds)
        else:
            master_boot = True

        # Check if a user has entered boot_options
        options, user_option = boot_options.as_dict(self, defaults={'boot_cmds': boot_cmds})
        if 'boot_cmds' in options and user_option and not master_boot:
            boot_cmds_boot_options = True

        # Interactive boot_cmds from the job file are a list.
        # We check for them first, if they are present, we use
        # them and ignore the other cases.
        if boot_cmds_job_file:
            logging.info('Overriding boot_cmds from job file')
            boot_cmds = self.config.boot_cmds
        # If there were no interactive boot_cmds, next we check
        # for boot_option overrides. If one exists, we use them
        # and ignore all other cases.
        elif boot_cmds_boot_options:
            logging.info('Overriding boot_cmds from boot_options')
            boot_cmds = options['boot_cmds'].value
            logging.info('boot_option=%s', boot_cmds)
            boot_cmds = self.config.cp.get('__main__', boot_cmds)
            boot_cmds = utils.string_to_list(boot_cmds.encode('ascii'))
        # No interactive or boot_option overrides are present,
        # we prefer to get the boot_cmds for the image if they are
        # present.
        elif boot_cmds_dynamic is not None:
            logging.info('Loading boot_cmds from image')
            boot_cmds = boot_cmds_dynamic
        # This is the catch all case. Where we get the default boot_cmds
        # from the deployment data.
        else:
            logging.info('Loading boot_cmds from device configuration')
            boot_cmds = self.config.cp.get('__main__', boot_cmds)
            boot_cmds = utils.string_to_list(boot_cmds.encode('ascii'))

        if boot_tags is not None:
            boot_cmds = self._tag_boot_cmds(boot_cmds, boot_tags)

        return boot_cmds

    ############################################################
    # modified by Wang Bo (wang.bo@whaley.cn), 2016.01.15
    # modify 'Restarting system.' to 'Restarting system'
    # to match the whaley platform
    ############################################################
    def _soft_reboot(self, connection):
        logging.info('perform soft reboot the system')
        # Try to C-c the running process, if any.
        connection.empty_buffer()
        connection.sendcontrol('c')
        connection.expect(['shell@', 'root@'])
        connection.sendline(self.config.soft_boot_cmd)
        if self.config.device_type == 'hisi':  # hisi platform
            connection.expect(self.config.interrupt_boot_prompt, timeout=20)
        else:  # mstar platform, mstar/mstar-938
            connection.expect('U-Boot', timeout=20)
        for i in range(100):
            connection.sendline('')
            time.sleep(0.06)

    def _hard_reboot(self, connection):
        logging.info('perform hard reset on the system')
        connection.empty_buffer()
        connection.sendline('')
        index = connection.expect(['shell@', 'root@', pexpect.TIMEOUT], timeout=5)
        if index == 0 or index == 1:
            logging.info('in normal shell console, try to display usb info')
            self._display_usb_whaley(connection)
        else:
            logging.info('not in normal shell console, skip display usb info')

        if self.config.hard_reset_command != '':
            # use power_off and power_on to instead of hard_reset_command
            # self.context.run_command(self.config.hard_reset_command)
            self.context.run_command(self.config.power_off_cmd)
            time.sleep(20)
            self.context.run_command(self.config.power_on_cmd)
            if self.config.device_type == 'hisi':  # hisi platform
                connection.expect(self.config.interrupt_boot_prompt, timeout=20)
            else:  # mstar platform, mstar/mstar-938
                connection.expect('U-Boot', timeout=20)

            for i in range(100):
                connection.sendline('')
                time.sleep(0.06)
        else:
            self._soft_reboot(connection)

    def _enter_bootloader(self, connection):
        try:
            start = time.time()
            # add below line, 2016.09.18
            connection.expect(self.config.bootloader_prompt, timeout=self.config.bootloader_timeout)
            connection.empty_buffer()
            # Record the time it takes to enter the bootloader.
            enter_bootloader_time = '{0:.2f}'.format(time.time() - start)
            self.context.test_data.add_result('enter_bootloader', 'pass',
                                              enter_bootloader_time, 'seconds')
        except pexpect.TIMEOUT:
            msg = 'Infrastructure Error: failed to enter the bootloader.'
            logging.error(msg)
            self.context.test_data.add_result('enter_bootloader', 'fail', message=msg)
            raise

    def _boot_cmds_preprocessing(self, boot_cmds):
        """ preprocess boot_cmds to prevent the boot procedure from some errors
        (1)Delete the redundant element "" at the end of boot_cmds
        (2)(we can add more actions for preprocessing here).
        """
        # Delete the redundant element "" at the end of boot_cmds
        while True:
            if boot_cmds and boot_cmds[-1] == "":
                del boot_cmds[-1]
            else:
                break
        # we can add more actions here
        logging.debug('boot_cmds(after preprocessing): %s', boot_cmds)
        return boot_cmds

    def _tag_boot_cmds(self, boot_cmds, boot_tags):
        for i, cmd in enumerate(boot_cmds):
            for key, value in boot_tags.iteritems():
                if key in cmd:
                    boot_cmds[i] = boot_cmds[i].replace(key, value)

        return boot_cmds

    def _monitor_boot(self, connection, ps1, ps1_pattern, is_master=False):
        # get deploy_whaley_image parameters
        image = self.image_params.get('image', '')
        model_index = self.image_params.get('model_index')

        # get boot_whaley_image parameters
        skip = self.boot_params.get('skip', False)
        emmc = self.boot_params.get('emmc', False)

        if not skip and emmc:  # skip=False, emmc=True
            if 'mstar' in self.config.device_type:
                logging.info('[EMMC MSTAR] wait for end of auto_update.txt or auto_update_factory.txt')
                # timeout = 3600s
                connection.expect(self.config.interrupt_boot_prompt, timeout=self.config.image_boot_msg_timeout)
                for i in range(10):
                    connection.sendline('')
                connection.expect(self.config.bootloader_prompt)
                # clear connection buffer
                connection.empty_buffer()
                if self.config.device_type == 'mstar-938':
                    logging.info('[EMMC MSTAR] set factory mode for mstar 938')
                    connection.sendline('ufts set fts.fac.factory_mode 1', send_char=self.config.send_char)
                    connection.expect(self.config.bootloader_prompt)
                self._burn_factory_mstar_emmc(connection)
                self._show_factory_mstar_emmc(connection)
                self._wipe_data_mstar_emmc(connection)
                self._burn_mboot_script_mstar_emmc(connection)
                self._dump_emmc_mstar_emmc(connection)
                return
            elif self.config.device_type == 'hisi':
                logging.info('[EMMC HISI] wait for end of auto.txt')
                connection.empty_buffer()
                # apollo#
                if 'auto.txt' in image:
                    connection.expect(self.config.interrupt_boot_prompt, timeout=self.config.image_boot_msg_timeout)
                    for i in range(30):
                        connection.sendline('')
                        time.sleep(0.08)
                    connection.expect(self.config.bootloader_prompt, timeout=self.config.image_boot_msg_timeout)
                    connection.empty_buffer()
                    logging.info('[EMMC HISI] set factory mode for hisi')
                    connection.sendline('ufts set fts.fac.factory_mode 1', send_char=self.config.send_char)
                    connection.expect(self.config.bootloader_prompt)
                self._burn_factory_hisi_emmc(connection)
                connection.empty_buffer()
                # write panel index to deviceinfo
                logging.info('[EMMC HISI] try use panel_index command to judge whether fastboot support')
                connection.sendline('panel_index')
                connection.expect(self.config.bootloader_prompt)
                if 'Unknown command' in connection.before:
                    logging.info('[EMMC HISI] use spi command to set panel parameter')
                    connection.sendline('reset')
                    time.sleep(60)
                    self._skip_guide_whaley(connection)
                    self._del_db_hisi_emmc(connection)
                    self._set_spi_hisi_emmc(connection, model_index)
                    connection.sendline('reboot', send_char=self.config.send_char)
                    logging.info('[EMMC HISI] reboot device to make spi parameter take effect')
                else:
                    logging.info('[EMMC HISI] use panel_index command to set panel parameter')
                    connection.sendline('panel_index write %s' % model_index, send_char=self.config.send_char)
                    connection.expect(self.config.bootloader_prompt)
                    connection.sendline('panel_index read')
                    connection.expect(self.config.bootloader_prompt)
                    connection.sendline('reset')
                time.sleep(120)
                self._show_pq_hisi_emmc(connection)
                connection.sendline('reboot r', send_char=self.config.send_char)
                connection.expect('StartGUI', timeout=150)
                time.sleep(15)
                self._dump_emmc_hisi_emmc(connection)
                return
        else:  # skip=False, emmc=False
            # burn factory image
            if self.config.device_type == 'mstar' or self.config.device_type == 'mstar-938':
                self._burn_factory_mstar(connection)
            elif self.config.device_type == 'hisi':
                self._burn_factory_hisi(connection)

            if 'R' in image and not skip:
                self._burn_su_image(connection)
                self._enter_recovery_whaley(connection)
                self._su_device_whaley(connection)

        good = 'pass'
        bad = 'fail'
        if not is_master:
            wait_for_image_boot = 'wait_for_image_boot_msg'
            wait_for_kernel_boot = 'wait_for_kernel_boot_msg'
            wait_for_login_prompt = 'wait_for_login_prompt'
            kernel_exception = 'test_kernel_exception_'
            wait_for_image_prompt = 'wait_for_test_image_prompt'
            image_boot = 'test_image_boot_time'
            kernel_boot = 'test_kernel_boot_time'
            userspace_boot = 'test_userspace_boot_time'
        else:
            wait_for_image_boot = 'wait_for_master_image_boot_msg'
            wait_for_kernel_boot = 'wait_for_master_kernel_boot_msg'
            wait_for_login_prompt = 'wait_for_master_login_prompt'
            kernel_exception = 'master_kernel_exception_'
            wait_for_image_prompt = 'wait_for_master_image_prompt'
            kernel_boot = 'master_kernel_boot_time'
            userspace_boot = 'master_userspace_boot_time'

        if self.config.has_kernel_messages:
            try:
                start = time.time()
                connection.expect(self.config.image_boot_msg,
                                  timeout=self.config.image_boot_msg_timeout)
                image_boot_time = "{0:.2f}".format(time.time() - start)
                start = time.time()
                self.context.test_data.add_result(wait_for_image_boot, good)
            except pexpect.TIMEOUT:
                msg = "Kernel Error: did not start booting."
                logging.error(msg)
                # add below to reset bootloader, and reboot device, at 2016.04.29
                logging.info("try to reset the bootloader, and reboot device")
                for i in range(5):
                    connection.sendcontrol('c')
                    time.sleep(2)
                    try:
                        connection.expect(self.config.bootloader_prompt, timeout=3)
                        connection.sendline("reset")  # restart device
                        break  # stop the tftp successfully
                    except:
                        logging.warning("can't stop tftp, try again")
                self.context.test_data.add_result(wait_for_image_boot, bad, message=msg)
                raise

            try:
                done = False
                warnings = 0
                while not done:
                    pl = [self.config.kernel_boot_msg,
                          'Freeing init memory',
                          '-+\[ cut here \]-+\s+(.*\s+-+\[ end trace (\w*) \]-+)',
                          '(Unhandled fault.*)\r\n']
                    i = connection.expect(pl, timeout=self.config.kernel_boot_msg_timeout)
                    if i == 0 or i == 1:
                        # Kernel booted normally
                        done = True
                    elif i == 2:
                        warnings += 1
                        logging.info('Kernel exception detected, logging error')
                        kwarn = kernel_exception + str(warnings)
                        kwarnings = connection.match.group(1)
                        self.context.test_data.add_result(kwarn, 'fail', message=kwarnings)
                        continue
                    elif i == 3:
                        warnings += 1
                        logging.info('Kernel exception detected, logging error')
                        kwarn = kernel_exception + str(warnings)
                        kwarnings = connection.match.group(0)
                        self.context.test_data.add_result(kwarn, 'fail', message=kwarnings)
                        continue
                kernel_boot_time = "{0:.2f}".format(time.time() - start)
                self.context.test_data.add_result(wait_for_kernel_boot, good)
                start = time.time()
            except pexpect.TIMEOUT:
                self.context.test_data.add_result(wait_for_kernel_boot, bad)
                raise

            # add below 2 functions to skip guide and install busybox
            # add is_skip in the future
            self._skip_guide_whaley(connection)
            # display usb info
            self._display_usb_whaley(connection)
            # install busybox
            self._install_busybox_whaley(connection)
            # set shutdown time to -1, no shutdown
            self._close_shutdown_whaley(connection)
            # remove helios guide
            self._remove_helios_guide(connection)
            # set factory info, mac addr, sn
            self._set_factory_whaley(connection)
            # set logctl
            # self._set_logctl_whlay(connection)
            # display usb info
            self._display_usb_whaley(connection)
            # reboot device
            connection.sendline('reboot', send_char=self.config.send_char)
            time.sleep(50)
            # wait for system reboot
            self._skip_guide_whaley(connection)
            # set vip account
            self._set_vip_whaley(connection)

        # try:
        #     self._auto_login(connection, is_master)
        # except pexpect.TIMEOUT:
        #     msg = "Userspace Error: auto login prompt not found."
        #     logging.error(msg)
        #     self.context.test_data.add_result(wait_for_login_prompt, bad, message=msg)
        #     raise
        #
        # try:
        #     if is_master:
        #         pattern = self.config.master_str
        #     else:
        #         pattern = self.config.test_image_prompts
        #     logging.info("test image prompts pattern: %s" % pattern)
        #     self._wait_for_prompt(connection, pattern, self.config.boot_linaro_timeout)
        #     if not is_master:
        #         if self.target_distro == 'android':
        #             # Gain root access
        #             connection.sendline('su')
        #             self._wait_for_prompt(connection, pattern, timeout=10)
        #     connection.sendline('export PS1="%s"' % ps1,
        #                         send_char=self.config.send_char)
        #     self._wait_for_prompt(connection, ps1_pattern, timeout=10)
        #     if self.config.has_kernel_messages:
        #         userspace_boot_time = "{0:.2f}".format(time.time() - start)
        #     self.context.test_data.add_result(wait_for_image_prompt, good)
        # except pexpect.TIMEOUT:
        #     msg = "Userspace Error: image prompt not found."
        #     logging.error(msg)
        #     self.context.test_data.add_result(wait_for_image_prompt, bad)
        #     raise
        #
        # # Record results
        # boot_meta = {}
        # boot_meta['dtb-append'] = str(self.config.append_dtb)
        # self.context.test_data.add_metadata(boot_meta)
        # if self.config.has_kernel_messages:
        #     self.context.test_data.add_result(image_boot, 'pass',
        #                                       image_boot_time, 'seconds')
        #     self.context.test_data.add_result(kernel_boot, 'pass',
        #                                       kernel_boot_time, 'seconds')
        #     self.context.test_data.add_result(userspace_boot, 'pass',
        #                                       userspace_boot_time, 'seconds')
        #     logging.info("Image boot time: %s seconds" % image_boot_time)
        #     logging.info("Kernel boot time: %s seconds" % kernel_boot_time)
        #     logging.info("Userspace boot time: %s seconds" % userspace_boot_time)

    def _burn_mboot_mstar_emmc(self, connection):
        image = self.image_params.get('image', '')
        image_server_ip = self.image_params.get('image_server_ip', '')
        if self.config.device_type == 'mstar':
            logging.info('[EMMC MSTAR] burn mboot through tftp with auto_update_mboot.txt')
            mboot_txt = os.path.join(os.path.dirname(image), 'auto_update_mboot.txt')
            logging.info('[EMMC MSTAR] path of auto_update_mboot.txt: %s' % mboot_txt)
        else:
            logging.info('[EMMC MSTAR] burn mboot through tftp with [[mboot')
            mboot_txt = os.path.join(os.path.dirname(image), 'scripts', '[[mboot')
            logging.info('[EMMC MSTAR] path of mboot: %s' % mboot_txt)
        connection.sendline('setenv bootdelay 10', send_char=self.config.send_char)
        connection.sendline('setenv macaddr', send_char=self.config.send_char)
        connection.sendline('setenv ethaddr', send_char=self.config.send_char)
        connection.sendline('setenv serverip %s' % image_server_ip, send_char=self.config.send_char)
        connection.sendline('saveenv', send_char=self.config.send_char)
        connection.expect('done')
        connection.empty_buffer()
        connection.sendline('estart', send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=20)
        connection.sendline('dhcp', send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=20)
        connection.sendline('mstar %s' % mboot_txt, send_char=self.config.send_char)
        if self.config.device_type == 'mstar-938':
            connection.expect(self.config.bootloader_prompt, timeout=300)
            connection.sendline('reset')
        connection.expect(self.config.interrupt_boot_prompt, timeout=300)
        for i in range(10):
            connection.sendline('')
        # << MStar >>#
        connection.expect(self.config.bootloader_prompt)
        connection.empty_buffer()
        logging.info('[EMMC MSTAR] clean all env for mstar platfrom')
        connection.sendline('cleanallenv')
        connection.expect(self.config.bootloader_prompt)
        if self.config.device_type == 'mstar-938':
            connection.sendline('ufts reset')
            connection.expect(self.config.bootloader_prompt)
        connection.sendline('setenv bootdelay 10')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('saveenv')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('reset')
        connection.expect(self.config.interrupt_boot_prompt, timeout=60)
        for i in range(10):
            connection.sendline('')
        # << MStar >>#
        connection.expect(self.config.bootloader_prompt)
        connection.empty_buffer()
        logging.info('[EMMC MSTAR] end of burn mboot')

    def _burn_fastboot_hisi_emmc(self, connection):
        image = self.image_params.get('image', '')
        image_server_ip = self.image_params.get('image_server_ip', '')
        logging.info('[EMMC HISI] burn fastboot through tftp with factory.txt')
        fastboot_path = os.path.join(os.path.dirname(image), 'fastboot.txt')
        logging.info('fastboot path is: %s' % fastboot_path)
        connection.empty_buffer()
        mac_addr = self._get_macaddr_whaley()
        connection.sendline('setenv ethaddr %s' % mac_addr, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('setenv serverip %s' % image_server_ip, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('exec %s' % fastboot_path, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=600)
        connection.sendline('reset')
        connection.expect(self.config.interrupt_boot_prompt, timeout=600)
        for i in range(50):
            connection.sendline('')
            time.sleep(0.06)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('ufts reset', send_char=self.config.send_char)
        connection.sendline('setenv ethaddr %s' % mac_addr, send_char=self.config.send_char)
        connection.empty_buffer()
        logging.info('[EMMC HISI] end of burn fastboot')

    def _burn_factory_mstar_emmc(self, connection):
        logging.info("[EMMC MSTAR] burn factory through tftp")
        factory = self._generate_factory_image()
        logging.info("[EMMC MSTAR] path of factory image: %s" % factory)
        connection.sendline('setenv serverip %s' % self.context.config.lava_server_ip, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('estart')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('dhcp')
        connection.expect(self.config.bootloader_prompt, timeout=100)
        connection.sendline('mstar %s' % factory, send_char=self.config.send_char)
        # << MStar >>#
        connection.expect(self.config.bootloader_prompt, timeout=600)
        # clear connection buffer
        connection.empty_buffer()
        logging.info('[EMMC MSTAR] end of burn factory')

    def _generate_factory_image(self):
        logging.info('context.config: %s' % self.context.config)
        logging.info('config: %s' % self.config)
        current = os.getcwd()
        # /var/lib/lava/dispatcher/tmp
        image_tmpdir = self.context.config.lava_image_tmpdir
        # factory_tool path
        factory_tool = os.path.join(image_tmpdir, 'factory')
        # get current job id
        output_dir = self.context.output.output_dir
        logging.info('current job output directory: %s' % output_dir)
        job_id = output_dir.strip().split('/')[-1]
        job_id = job_id.split('-')[-1]
        logging.info('job id: % s' % job_id)
        # scratch dir
        # /var/lib/lava/dispatcher/tmp/xxxx/factory
        factory = os.path.join(self.scratch_dir, 'factory')
        shutil.copytree(factory_tool, factory)
        logging.info('change workspace to %s' % factory)
        os.chdir(factory)
        project_name = self.image_params.get('project_name', '')
        model_index = self.image_params.get('model_index', '')
        product_name = self.image_params.get('product_name', '')
        yun_os = self.image_params.get('yun_os', 'false')
        command = ['sudo', '-u', 'root', './factory.sh', job_id, project_name, model_index, product_name, yun_os]
        subprocess.call(command)
        if project_name in ['apollo', 'phoebus']:
            if os.path.isfile(os.path.join(factory, 'image', job_id, 'factory')) and \
                    os.path.isfile(os.path.join(factory, 'image', job_id, 'factory.ext4.gz')):
                logging.info('generate factory image successfully')
                os.system('sudo -u root mv image/%s %s' % (job_id, self.context.config.lava_image_tmpdir))
                os.chdir(current)
                return os.path.join(job_id, 'factory')
            else:
                os.chdir(current)
                raise CriticalError('can not generate factory image')
        elif project_name in ['sphinx', 'titan', 'helios']:
            if os.path.isfile(os.path.join(factory, 'image', job_id, 'factory')) and \
                    os.path.isfile(os.path.join(factory, 'image', job_id, 'factory.img')):
                logging.info('generate factory image successfully')
                os.system('sudo -u root mv image/%s %s' % (job_id, self.context.config.lava_image_tmpdir))
                os.chdir(current)
                return os.path.join(job_id, 'factory')
            else:
                os.chdir(current)
                raise CriticalError('can not generate factory image')
        else:
            os.chdir(current)
            logging.warning('only support apollo, helios, sphinx, titan')
            raise CriticalError('only support apollo, helios, sphinx, titan')

    def _show_factory_mstar_emmc(self, connection):
        connection.sendline('recovery')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('reset')
        connection.expect('/ #', timeout=100)
        time.sleep(10)
        connection.sendcontrol('c')
        connection.expect(['/ #', pexpect.TIMEOUT])
        connection.sendline('busybox ls -lh /factory')
        time.sleep(2)
        connection.sendline('busybox cat /factory/model_index.ini')
        time.sleep(2)
        connection.sendline('busybox cat /factory/factory.prop')
        time.sleep(2)
        connection.sendline('busybox reboot -f')
        connection.expect(self.config.interrupt_boot_prompt, timeout=100)
        for i in range(10):
            connection.sendline('')
        connection.expect(self.config.bootloader_prompt)
        # clear connection buffer
        logging.info('clear connection buffer')
        connection.empty_buffer()
        connection.sendcontrol('c')
        connection.expect(self.config.bootloader_prompt)
        logging.info('[EMMC MSTAR] end of show factory partition')

    def _burn_factory_mstar(self, connection):
        logging.info('start to burn mstar factory image')
        connection.expect(self.config.interrupt_boot_prompt, timeout=self.config.image_boot_msg_timeout)
        # timeout = 3600s
        for i in range(10):
            connection.sendline('')
        # << MStar >>#
        connection.expect(self.config.bootloader_prompt)
        # clear the buffer
        connection.empty_buffer()
        connection.sendline('setenv serverip %s' % self.context.config.lava_server_ip, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('estart')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('dhcp')
        connection.expect(self.config.bootloader_prompt, timeout=100)
        try:
            factory = self._generate_factory_image()
            connection.sendline('mstar %s' % factory, send_char=self.config.send_char)
            connection.expect([self.config.bootloader_prompt, pexpect.TIMEOUT], timeout=600)
        except CriticalError:
            logging.warning('skip burn factory image')
        finally:
            connection.sendline('reset', send_char=self.config.send_char)
        logging.info('end of burn mstar factory')

    def _burn_factory_hisi(self, connection):
        logging.info('start to burn hisi factory')
        connection.expect(self.config.interrupt_boot_prompt, timeout=self.config.image_boot_msg_timeout)
        # timeout = 3600s
        for i in range(30):
            connection.sendline('')
            time.sleep(0.06)
        # apollo#
        connection.expect(self.config.bootloader_prompt)
        # clear the buffer
        connection.empty_buffer()
        connection.sendline('setenv serverip %s' % self.context.config.lava_server_ip, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('dhcp')
        connection.expect(self.config.bootloader_prompt, timeout=100)
        try:
            factory = self._generate_factory_image()
            connection.sendline('exec %s' % factory, send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt, timeout=600)
        except CriticalError:
            logging.warning('skip burn factory image')
        finally:
            connection.sendline('reset', send_char=self.config.send_char)
        logging.info('end of burn hisi factory')
    
    def _burn_factory_hisi_emmc(self, connection):
        factory = self._generate_factory_image()
        logging.info('[EMMC HISI] start to burn hisi factory')
        # clear the buffer
        connection.empty_buffer()
        connection.sendline('setenv serverip %s' % self.context.config.lava_server_ip, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('dhcp')
        connection.expect(self.config.bootloader_prompt, timeout=100)
        connection.sendline('exec %s' % factory, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=600)
        connection.empty_buffer()
        connection.sendline('printenv')
        connection.expect(self.config.bootloader_prompt, timeout=60)
        connection.sendline('ufts list')
        connection.expect(self.config.bootloader_prompt)
        logging.info('[EMMC HISI] end of burn hisi factory')
    
    def _del_db_hisi_emmc(self, connection):
        logging.info('[EMMC HISI] delete database')
        connection.sendline('rm -rf /tvdatabase/db/*')
        connection.sendline('rm -rf /tvdatabase/dtv/*')
        connection.sendline('rm -rf /atv/db/*')
        connection.sendline('sync')
        connection.empty_buffer()
        logging.info('[EMMC HISI] end of delete database')
    
    def _set_spi_hisi_emmc(self, connection, model_index):
        logging.info('[EMMC HISI] set panel index with spi')
        connection.sendline('hidebug')
        connection.expect('TV')
        connection.sendline('factory')
        connection.expect('factory@TV')
        connection.sendline('spi %s' % model_index)
        connection.expect('factory@TV')
        connection.sendline('q')
        connection.expect('TV')
        connection.sendline('q')
        connection.expect('shell@')
        self._show_pq_hisi_emmc(connection)
        logging.info('[EMMC HISI] end of set panel index with spi')
    
    def _show_pq_hisi_emmc(self, connection):
        logging.info('[EMMC HISI] show pq and factory files')
        connection.sendline('cat /proc/msp/pdm')
        connection.expect('shell@')
        connection.sendline('cat /proc/msp/pq')
        connection.expect('shell@')
        connection.sendline('busybox ls -lh /factory')
        time.sleep(2)
        connection.sendline('cat /factory/factory.prop')
        time.sleep(2)
        connection.sendline('cat /factory/model_index.ini')
        time.sleep(2)
        connection.empty_buffer()
        logging.info('[EMMC HISI] end of show pq and factory files')

    def _wipe_data_mstar_emmc(self, connection):
        logging.info('[EMMC MSTAR] wipe data partition')
        connection.sendline('setenv db_table 0')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('saveenv')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('recovery_wipe_partition data', send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=30)
        connection.sendline('reset', send_char=self.config.send_char)
        connection.expect('/ #', timeout=300)
        logging.info('[EMMC MSTAR] end of wipe data partition')

    def _burn_mboot_script_mstar_emmc(self, connection):
        logging.info('[EMMC MSTAR] wait for android booted')
        index = connection.expect(['start test', 'TVOS'], timeout=self.config.image_boot_msg_timeout)
        if index == 1:
            time.sleep(200)
        self._hard_reboot(connection)
        connection.expect(self.config.bootloader_prompt, timeout=30)
        # clear the buffer
        connection.empty_buffer()
        logging.info('[EMMC MSTAR] start to burn [[mboot')
        image = self.image_params.get('image', '')
        image_server_ip = self.image_params.get('image_server_ip', '')
        mboot_script = os.path.join(os.path.dirname(image), 'scripts', '[[mboot')
        logging.info('[EMMC MSTAR] path of [[mboot: %s' % mboot_script)
        connection.sendline('setenv serverip %s' % image_server_ip, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('estart')
        connection.expect(self.config.bootloader_prompt)
        connection.sendline('dhcp')
        connection.expect(self.config.bootloader_prompt, timeout=100)
        connection.sendline('mstar %s' % mboot_script, send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=600)
        logging.info('[EMMC MSTAR] end of burn [[mboot')

    def _dump_emmc_mstar_emmc(self, connection):
        logging.info('[EMMC MSTAR] begin to dump emmc to usb disk')
        connection.empty_buffer()
        connection.sendline('setenv bootdelay', send_char=self.config.send_char)
        connection.sendline('setenv deployargs', send_char=self.config.send_char)
        connection.sendline('setenv bootcmd', send_char=self.config.send_char)
        connection.sendline('setenv macaddr 00:30:1B:BA:02:DB', send_char=self.config.send_char)
        connection.sendline('saveenv', send_char=self.config.send_char)
        connection.expect('done')
        connection.empty_buffer()
        connection.sendline('mmc erase.boot 2 0 512', send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=60)
        connection.sendline('printenv')
        connection.expect(self.config.bootloader_prompt, timeout=60)
        if self.config.device_type == 'mstar-938':
            connection.sendline('ufts list', send_char=self.config.send_char)
            connection.expect(self.config.bootloader_prompt)
        connection.empty_buffer()
        connection.sendline('usb start 3', send_char=self.config.send_char)
        connection.expect(self.config.bootloader_prompt, timeout=60)
        connection.sendline('mmc dd mmc2usb 3', send_char=self.config.send_char)
        connection.expect('Dump Block', timeout=self.config.image_boot_msg_timeout)
        time.sleep(10)
        logging.info('[EMMC MSTAR] end of dump emmc to usb disk')
    
    def _dump_emmc_hisi_emmc(self, connection):
        logging.info('[EMMC HISI] begin to dump emmc to usb disk in recovery mode')
        connection.sendcontrol('c')
        connection.expect('/ #')
        connection.empty_buffer()
        connection.sendline('busybox --install /sbin', send_char=self.config.send_char)
        connection.sendline('busybox mkdir /tmp/disk', send_char=self.config.send_char)
        connection.sendline('sda=`busybox ls /dev/block/sda* | busybox grep "/dev/block/sda."`', send_char=self.config.send_char)
        time.sleep(2)
        connection.sendline('busybox mount $sda /tmp/disk', send_char=self.config.send_char)
        time.sleep(2)
        connection.empty_buffer()
        connection.sendline('busybox dd if=/dev/block/mmcblk0 of=/tmp/disk/android.bin bs=512', send_char=self.config.send_char)
        connection.expect('/ #', timeout=3600)
        connection.sendline('busybox md5sum /tmp/disk/android.bin', send_char=self.config.send_char)
        connection.expect('/ #', timeout=600)
        connection.sendline('busybox umount /tmp/disk', send_char=self.config.send_char)
        connection.expect('/ #')
        logging.info('[EMMC HISI] end of dump emmc to usb disk')

    def _customize_bootloader(self, connection, boot_cmds):
        # get deploy_whaley_image parameters
        image = self.image_params.get('image', '')
        image_server_ip = self.image_params.get('image_server_ip', '')
        # get boot_whaley_image parameters
        skip = self.boot_params.get('skip', False)
        emmc = self.boot_params.get('emmc', False)

        if not skip and emmc:  # skip=False, emmc=True
            if self.config.device_type == 'mstar' or self.config.device_type == 'mstar-938':
                logging.info('[EMMC MSTAR] make emmc image for mstar platform')
                self._burn_mboot_mstar_emmc(connection)
                logging.info('[EMMC MSTAR] burn image through tftp with auto_update_factory.txt or auto_update.txt')
                logging.info('[EMMC MSTAR] path of image path: %s' % image)
            elif self.config.device_type == 'hisi':
                logging.info('[EMMC HISI] make emmc image for hisi platform')
                self._burn_fastboot_hisi_emmc(connection)
                logging.info('[EMMC HISI] burn factory image through tftp with auto_factory.txt')
                logging.info('[EMMC HISI] path of auto_factory.txt: %s' % image)
            else:
                logging.warning('no device type mstar or hisi found')
        else:  # skip=False, emmc=False
            logging.info('burn normal image, not factory emmc image')
            if 'mstar' in self.config.device_type:
                logging.info('burn mboot firstly for mstar platform')
                mboot_path = os.path.join(os.path.dirname(image), 'auto_update_mboot.txt')
                logging.info('mboot path is: %s' % mboot_path)
                connection.empty_buffer()
                if self.config.device_type == 'mstar':
                    connection.sendline('cleanallenv')
                    connection.expect(self.config.bootloader_prompt)
                    connection.sendline('setenv bootdelay 10')
                    connection.expect(self.config.bootloader_prompt)
                elif self.config.device_type == 'mstar-938':
                    connection.sendline('cleanallenv')
                    connection.expect(self.config.bootloader_prompt)
                    connection.sendline('setenv bootdelay 10')
                    connection.expect(self.config.bootloader_prompt)
                    connection.sendline('ufts reset', send_char=self.config.send_char)
                    connection.expect(self.config.bootloader_prompt)
                connection.sendline('saveenv', send_char=self.config.send_char)
                connection.expect(self.config.bootloader_prompt)
                connection.sendline('reset')
                connection.expect(self.config.interrupt_boot_prompt, timeout=100)
                for i in range(10):
                    connection.sendline('')
                    time.sleep(0.1)
                connection.expect(self.config.bootloader_prompt)
                # clear the buffer
                connection.empty_buffer()
                connection.sendline('setenv serverip %s' % image_server_ip, send_char=self.config.send_char)
                connection.expect(self.config.bootloader_prompt)
                self._set_macaddr_whaley(connection)
                connection.sendline('mstar %s' % mboot_path, send_char=self.config.send_char)
                connection.expect(self.config.interrupt_boot_prompt, timeout=600)
                for i in range(10):
                    connection.sendline('')
                    time.sleep(0.1)
                # << MStar >>#
                connection.expect(self.config.bootloader_prompt)
                # clear the buffer
                connection.empty_buffer()
            elif self.config.device_type == 'hisi':
                logging.info('burn fastboot firstly for hisi platform')
                fastboot_path = os.path.join(os.path.dirname(image), 'fastboot.txt')
                logging.info('fastboot path is: %s' % fastboot_path)
                connection.empty_buffer()
                self._set_macaddr_whaley(connection)
                connection.sendline('setenv serverip %s' % image_server_ip, send_char=self.config.send_char)
                connection.expect(self.config.bootloader_prompt)
                connection.sendline('ufts reset', send_char=self.config.send_char)
                connection.expect(self.config.bootloader_prompt)
                connection.sendline('exec %s' % fastboot_path, send_char=self.config.send_char)
                connection.expect(self.config.bootloader_prompt, timeout=600)
                connection.sendline('reset')
                connection.expect(self.config.interrupt_boot_prompt, timeout=600)
                for i in range(50):
                    connection.sendline('')
                    time.sleep(0.06)
                connection.expect(self.config.bootloader_prompt)
                connection.empty_buffer()
                mac_addr = self._get_macaddr_whaley()
                connection.sendline('setenv ethaddr %s' % mac_addr, send_char=self.config.send_char)
                connection.expect(self.config.bootloader_prompt)
            else:
                logging.warning('no device type mstar/mstar-938 or hisi found')

        delay = self.config.bootloader_serial_delay_ms
        _boot_cmds = self._boot_cmds_preprocessing(boot_cmds)
        start = time.time()

        try:
            for line in _boot_cmds:
                parts = re.match('^(?P<action>sendline|sendcontrol|expect)\s*(?P<command>.*)',
                                 line)
                if parts:
                    try:
                        action = parts.group('action')
                        command = parts.group('command')
                    except AttributeError as e:
                        raise Exception("Badly formatted command in \
                                          boot_cmds %s" % e)
                    if action == "sendline":
                        connection.send(command, delay,
                                        send_char=self.config.send_char)
                        connection.sendline('', delay,
                                            send_char=self.config.send_char)
                    elif action == "sendcontrol":
                        connection.sendcontrol(command)
                    elif action == "expect":
                        command = re.escape(command)
                        connection.expect(command,
                                          timeout=self.config.boot_cmd_timeout)
                else:
                    self._wait_for_prompt(connection, self.config.bootloader_prompt,
                                          timeout=self.config.boot_cmd_timeout)
                    # add below line to record boot commands
                    logging.info("boot command: %s" % line)
                    connection.sendline(line, delay, send_char=self.config.send_char)
            self.context.test_data.add_result('execute_boot_cmds', 'pass')
        except pexpect.TIMEOUT:
            msg = "Bootloader Error: boot command execution failed."
            logging.error(msg)
            self.context.test_data.add_result('execute_boot_cmds',
                                              'fail', message=msg)
            raise

        # Record boot_cmds execution time
        execution_time = "{0:.2f}".format(time.time() - start)
        self.context.test_data.add_result('boot_cmds_execution_time', 'pass',
                                          execution_time, 'seconds')

    def _target_extract(self, runner, tar_file, dest, timeout=-1, busybox=False):
        # tar_file = /tmp/fs.tgz
        # dest = /data/local/tmp
        # tmpdir = /var/lib/lava/dispatcher/tmp/
        # url = http://%(LAVA_SERVER_IP)s/tmp
        tmpdir = self.context.config.lava_image_tmpdir
        url = self.context.config.lava_image_url
        # tar_file = /tmp/fs.tgz
        tar_file = tar_file.replace(tmpdir, '')
        # tar_url = http://lava_server_ip/fs.tgz
        tar_url = '/'.join(u.strip('/') for u in [url, tar_file])
        self._target_extract_url(runner, tar_url, dest, timeout=timeout, busybox=busybox)

    def _target_extract_url(self, runner, tar_url, dest, timeout=-1, busybox=False):
        decompression_cmd = ''

        # if tar_url.endswith('.gz') or tar_url.endswith('.tgz'):
        #     decompression_cmd = '| /bin/gzip -dc'
        # elif tar_url.endswith('.bz2'):
        #     decompression_cmd = '| /bin/bzip2 -dc'
        # elif tar_url.endswith('.xz'):
        #     decompression_cmd = '| /usr/bin/xz -dc'
        # elif tar_url.endswith('.tar'):
        #     decompression_cmd = ''
        # else:
        #     raise RuntimeError('bad file extension: %s' % tar_url)

        if tar_url.endswith('.gz') or tar_url.endswith('.tgz'):
            decompression_cmd = '| busybox gzip -dc'
        elif tar_url.endswith('.bz2'):
            decompression_cmd = '| busybox bzip2 -dc'
        elif tar_url.endswith('.xz'):
            decompression_cmd = '| busybox xz -dc'
        elif tar_url.endswith('.tar'):
            decompression_cmd = ''
        else:
            raise RuntimeError('bad file extension: %s' % tar_url)

        wget_options = runner.get_wget_options()

        if self._image_has_selinux_support(runner, 3):
            self.context.selinux = '--selinux'
        else:
            self.context.selinux = ''
        # runner.run('wget %s -O - %s %s | /bin/tar %s -C %s -xmf -'
        #            % (wget_options, tar_url, decompression_cmd, self.context.selinux, dest),
        #            timeout=timeout)
        # download fs.tgz and extract into /data/local/tmp/
        runner.run('busybox wget %s -O - %s %s | busybox tar %s -C %s -xmf -'
                   % (wget_options, tar_url, decompression_cmd, self.context.selinux, dest),
                   timeout=timeout)

    @contextlib.contextmanager
    def _python_file_system(self, runner, directory, prompt_pattern, mounted=False):
        connection = runner.get_connection()
        error_detected = False
        try:
            if mounted:
                targetdir = os.path.abspath(os.path.join('/mnt/%s' % directory))
            else:
                targetdir = os.path.abspath(os.path.join('/', directory))

            runner.run('mkdir -p %s' % targetdir)

            parent_dir, target_name = os.path.split(targetdir)

            runner.run('nice tar -czf /tmp/fs.tgz -C %s %s' %
                       (parent_dir, target_name))
            runner.run('cd /tmp')  # need to be in same dir as fs.tgz

            try:
                ip = runner.get_target_ip()
            except NetworkError as e:
                error_detected = True
                raise CriticalError("Network error detected..aborting")

            connection.sendline('python -m SimpleHTTPServer 0 2>/dev/null')
            match_id = connection.expect([
                'Serving HTTP on 0.0.0.0 port (\d+) \.\.',
                pexpect.EOF, pexpect.TIMEOUT])
            if match_id != 0:
                msg = "Unable to start HTTP server"
                logging.error(msg)
                raise CriticalError(msg)
            port = connection.match.groups()[match_id]

            url = "http://%s:%s/fs.tgz" % (ip, port)
            tf = download_image(url, self.context, self.scratch_dir, decompress=False)

            tfdir = os.path.join(self.scratch_dir, str(time.time()))
            try:
                utils.ensure_directory(tfdir)
                self.context.run_command('nice tar --selinux -C %s -xzf %s' % (tfdir, tf))
                yield os.path.join(tfdir, target_name)

            finally:
                tf = os.path.join(self.scratch_dir, 'fs.tgz')
                utils.mk_targz(tf, tfdir)
                utils.rmtree(tfdir)

                connection.sendcontrol('c')  # kill SimpleHTTPServer
                self._wait_for_prompt(connection,
                                      prompt_pattern,
                                      timeout=30)

                # get the last 2 parts of tf, ie "scratchdir/tf.tgz"
                tf = '/'.join(tf.split('/')[-2:])
                runner.run('rm -rf %s' % targetdir)
                self._target_extract(runner, tf, parent_dir)

        finally:
            if not error_detected:
                # kill SimpleHTTPServer
                connection.sendcontrol('c')
                self._wait_for_prompt(connection,
                                      prompt_pattern,
                                      timeout=30)
            if mounted:
                runner.run('umount /mnt')

    @contextlib.contextmanager
    def _busybox_file_system(self, runner, directory, mounted=False):
        # runner: NetworkCommandRunner
        # directory: 'lava_test_results_dir': "/data/local/tmp/lava-device_host_name",
        error_detected = False
        try:
            if mounted:
                targetdir = os.path.abspath(os.path.join('/mnt/%s' % directory))
            else:
                # targetdir = /data/local/tmp/lava-%s
                targetdir = os.path.abspath(os.path.join('/', directory))

            # mkdir -p /data/local/tmp/lava-mstar01
            runner.run('mkdir -p %s' % targetdir)

            # parent_dir = /data/local/tmp
            # target_name = lava-mstar01
            parent_dir, target_name = os.path.split(targetdir)

            # change command to busybox
            # runner.run('/bin/tar -cmzf /tmp/fs.tgz -C %s %s'
            #            % (parent_dir, target_name))
            # tar parent_dir/target_name to /tmp/fs.tgz
            runner.run('busybox tar -cmzf /tmp/fs.tgz -C %s %s'
                       % (parent_dir, target_name))
            runner.run('cd /tmp')  # need to be in same dir as fs.tgz

            try:
                # get the target device ip
                ip = runner.get_target_ip()
            except NetworkError as e:
                error_detected = True
                raise CriticalError("Network error detected..aborting")

            url_base = self._start_busybox_http_server(runner, ip)

            # url = http://ip:http_port/fs.tgz
            url = url_base + '/fs.tgz'
            logging.info("Fetching url: %s", url)
            # scratch_dir = /var/lib/lava/dispatcher/tmp/tempdir/
            tf = download_image(url, self.context, self.scratch_dir,
                                decompress=False)

            tfdir = os.path.join(self.scratch_dir, str(time.time()))

            try:
                utils.ensure_directory(tfdir)
                self.context.run_command('/bin/tar -C %s -xzf %s'
                                         % (tfdir, tf))
                # tfdir = /var/lib/lava/dispatcher/tmp/tempdir/time
                # target_name = device hostname
                # /var/lib/lava/dispatcher/tmp/tempdir/time/device_hostname
                yield os.path.join(tfdir, target_name)
            finally:
                # tf = /var/lib/lava/dispatcher/tmp/tempdir/fs.tgz
                tf = os.path.join(self.scratch_dir, 'fs.tgz')
                utils.mk_targz(tf, tfdir)
                utils.rmtree(tfdir)

                # get the last 2 parts of tf, ie "scratchdir/tf.tgz"
                # tf = /tmp/fs.tgz
                tf = '/'.join(tf.split('/')[-2:])
                # targetdir = /data/local/tmp/lava-%s
                runner.run('rm -rf %s' % targetdir)
                # (runner, /tmp/fs.tgz, /data/local/tmp, True)
                # download the fs.tgz and extract into /data/local/tmp
                self._target_extract(runner, tf, parent_dir, busybox=True)
        finally:
            if not error_detected:
                self._stop_busybox_http_server(runner)
            if mounted:
                runner.run('umount /mnt')

    def _start_busybox_http_server(self, runner, ip):
        runner.run('busybox httpd -f -p %d &' % self.config.busybox_http_port)
        runner.run('echo $! > /tmp/httpd.pid')
        url_base = "http://%s:%d" % (ip, self.config.busybox_http_port)
        return url_base

    def _stop_busybox_http_server(self, runner):
        runner.run('kill `cat /tmp/httpd.pid`')

    def _customize_prompt_hostname(self, rootdir, profile_path):
        if re.search("%s", profile_path):
            # If profile path is expecting a rootdir in it, perform string
            # substitution.
            profile_path = profile_path % rootdir

        if os.path.exists(profile_path):
            with open(profile_path, 'a') as f:
                f.write('export PS1="%s"\n' % self.tester_ps1)
        if os.path.exists('%s/etc/hostname' % rootdir):
            with open('%s/etc/hostname' % rootdir, 'w') as f:
                f.write('%s\n' % self.config.hostname)

    @property
    def target_distro(self):
        return self.deployment_data['distro']

    @property
    def tester_ps1(self):
        # return self._get_from_config_or_deployment_data('tester_ps1')
        return ''

    @property
    def tester_ps1_pattern(self):
        # return self._get_from_config_or_deployment_data('tester_ps1_pattern')
        return ''

    @property
    def tester_ps1_includes_rc(self):
        # tester_ps1_includes_rc is a string so we can decode it here as
        # yes/no/ not set. If it isn't set, we stick with the device
        # default. We can't do the tri-state logic as a BoolOption because an
        # unset BoolOption returns False, not None, so we can't detect not set.
        # value = self._get_from_config_or_deployment_data(
        #     'tester_ps1_includes_rc')
        #
        # if isinstance(value, bool):
        #     return value
        #
        # if value.lower() in ['y', '1', 'yes', 'on', 'true']:
        #     return True
        # elif value.lower() in ['n', '0', 'no', 'off', 'false']:
        #     return False
        # else:
        #     raise ValueError("Unable to determine boolosity of %r" % value)
        return False

    @property
    def tester_rc_cmd(self):
        return self._get_from_config_or_deployment_data('tester_rc_cmd')

    @property
    def lava_test_dir(self):
        lava_test_dir = self._get_from_config_or_deployment_data('lava_test_dir')
        if re.match('.*%s', lava_test_dir):
            lava_test_dir = lava_test_dir % self.config.hostname
        return lava_test_dir

    @property
    def lava_test_results_dir(self):
        lava_test_results_dir = self._get_from_config_or_deployment_data('lava_test_results_dir')
        if re.match('.*%s', lava_test_results_dir):
            lava_test_results_dir = lava_test_results_dir % self.config.hostname
        return lava_test_results_dir

    def _get_from_config_or_deployment_data(self, key):
        value = getattr(self.config, key.lower())
        if value is None:
            keys = [key, key.upper(), key.lower()]
            for test_key in keys:
                value = self.deployment_data.get(test_key)
                if value is not None:
                    return value

            # At this point we didn't find anything.
            raise KeyError("Unable to find value for key %s" % key)
        else:
            return value

    def _customize_linux(self):
        # XXX Re-examine what to do here in light of deployment_data import.
        # perhaps make self.deployment_data = deployment_data({overrides: dict})
        # and remove the write function completely?

        os_release_id = 'linux'
        mnt = self.mount_info['rootfs']
        os_release_file = '%s/etc/os-release' % mnt
        if os.path.exists(os_release_file):
            for line in open(os_release_file):
                if line.startswith('ID='):
                    os_release_id = line[(len('ID=')):]
                    os_release_id = os_release_id.strip('\"\n')
                    break

        profile_path = "%s/etc/profile" % mnt
        if os_release_id == 'debian' or os_release_id == 'ubuntu' or \
                os.path.exists('%s/etc/debian_version' % mnt):
            self.deployment_data = deployment_data.ubuntu
            profile_path = '%s/root/.bashrc' % mnt
        elif os_release_id == 'fedora':
            self.deployment_data = deployment_data.fedora
        else:
            # assume an OE based image. This is actually pretty safe
            # because we are doing pretty standard linux stuff, just
            # just no upstart or dash assumptions
            self.deployment_data = deployment_data.oe

        self._customize_prompt_hostname(mnt, profile_path)

    def _pre_download_src(self, customize_info, image=None):
        # for self.customize_image

        if image is not None:
            for customize_object in customize_info["image"]:
                image_path = ImagePathHandle(image, customize_object["src"], self.config, self.mount_info)
                temp_file = image_path.copy_to(self.context, None)
                customize_object["src"] = temp_file
        else:
            customize_info["image"] = []
            logging.debug("There are not image files which will be pre-download to temp dir!")

        for customize_object in customize_info["remote"]:
            temp_file = download_image(customize_object["src"], self.context)
            customize_object["src"] = temp_file

    def _reorganize_customize_files(self):
        # for self.customize_image
        # translate the raw customize info from
        #    "customize": {
        #    "http://my.server/files/startup.nsh": ["boot:/EFI/BOOT/", "boot:/startup_backup.nsh"],
        #    "http://my.server/files/my-crazy-bash-binary": ["rootfs:/bin/bash"],
        #    "rootfs:/lib/modules/eth.ko": ["rootfs:/lib/modules/firmware/eth.ko", "delete"]
        #    }
        #
        # to a specific object
        #   customize_info = {
        #       "delete":[image_path_1, image_path_2],
        #       "image":[
        #           {"src":"image_path_1", "des":[image_path_1]},
        #           {"src":"image_path_2", "des":[image_path_1, image_path_2]}
        #       ],
        #       "remote":[
        #           {"src":"url_1", "des":[image_path_1, image_path_2]},
        #           {"src":"url_2", "des":[image_path_1]}
        #       ]
        #   }
        #
        # make this info easy to be processed
        #

        customize_info = {
            "delete": [],
            "image": [],
            "remote": []
        }
        image_part = ["boot", "root"]

        for src, des in self.config.customize.items():
            temp_dic = {"src": src, "des": des}
            for des_tmp in temp_dic["des"]:
                if des_tmp[:5] != "boot:" and des_tmp[:7] != "rootfs:" and des_tmp != "delete":
                    logging.error('Customize function only support <boot, rootfs>:<path> as image path, for now!')
                    raise CriticalError("Unrecognized image path %s, Please check your test definition!" % des_tmp)
                    # temp_dic["des"].remove(des_tmp)
            if src[:4] in image_part:
                if "delete" in temp_dic["des"]:
                    customize_info["delete"].append(src)
                    temp_dic["des"].remove("delete")
                customize_info["image"].append(temp_dic)
            else:
                if "delete" in temp_dic["des"]:
                    logging.warning("Do not try to delete the remote file %s", temp_dic["src"])
                    temp_dic["des"].remove("delete")
                customize_info["remote"].append(temp_dic)

        logging.debug("Do customizing image with %s", customize_info)

        return customize_info

    def _customize_image(self, image, boot_mnt, rootfs_mnt):
        self.mount_info = {'boot': boot_mnt, 'rootfs': rootfs_mnt}

        # for _customize_linux integration
        self._customize_linux()

        # for files injection function.
        if self.config.customize is not None and image is not None:
            # format raw config.customize to customize_info object
            customize_info = self._reorganize_customize_files()

            # fetch all the src file into the local temp dir
            self._pre_download_src(customize_info, image)

            # delete file or dir in image
            for delete_item in customize_info["delete"]:
                image_item = ImagePathHandle(image, delete_item, self.config, self.mount_info)
                image_item.remove()

            # inject files/dirs, all the items should be pre-downloaded into temp dir.
            for customize_object in customize_info["image"]:
                for des_image_path in customize_object["des"]:
                    def_item = ImagePathHandle(image, des_image_path, self.config, self.mount_info)
                    def_item.copy_from(customize_object["src"])
            for customize_object in customize_info["remote"]:
                for des_image_path in customize_object["des"]:
                    def_item = ImagePathHandle(image, des_image_path, self.config, self.mount_info)
                    def_item.copy_from(customize_object["src"])
        else:
            logging.debug("Skip customizing temp image %s !", image)
            logging.debug("Customize object is %s !", self.config.customize)

    def customize_image(self, image=None):
        if self.config.boot_part != self.config.root_part:
            with image_partition_mounted(image, self.config.boot_part) as boot_mnt:
                with image_partition_mounted(image, self.config.root_part) as rootfs_mnt:
                    self._customize_image(image, boot_mnt, rootfs_mnt)
        else:
            with image_partition_mounted(image, self.config.boot_part) as boot_mnt:
                self._customize_image(image, boot_mnt, boot_mnt)

    def _config_network_bridge(self, bridge, ifname):
        logging.debug("Creating tap interface: %s" % ifname)
        self.context.run_command("ip tuntap add dev %s mode tap user lavaserver" % ifname)
        self.context.run_command("ifconfig %s 0.0.0.0 promisc up" % ifname)
        self.context.run_command("brctl addif %s %s" % (bridge, ifname))
        self._bridge_configured = True

    def _teardown_network_bridge(self, bridge, ifname):
        logging.debug("Destroying tap interface: %s" % ifname)
        self.context.run_command("brctl delif %s %s" % (bridge, ifname))
        self.context.run_command("ifconfig %s down" % ifname)
        self.context.run_command("ip tuntap del dev %s mode tap" % ifname)
        self._bridge_configured = False
