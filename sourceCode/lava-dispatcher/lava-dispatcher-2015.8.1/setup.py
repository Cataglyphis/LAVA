#!/usr/bin/env python

from setuptools import setup, find_packages
from version import version_tag


setup(
    name="lava-dispatcher",
    version=version_tag(),
    url='http://git.linaro.org/git/lava/lava-dispatcher.git',
    license='GPL v2 or later',
    description="Part of the LAVA framework for dispatching test jobs",
    author='Linaro Validation Team',
    author_email='linaro-validation@lists.linaro.org',
    namespace_packages=['lava'],
    test_suite='lava_dispatcher.tests.test_suite',
    entry_points="""
    [lava.commands]
    dispatch = lava.dispatcher.commands:dispatch
    connect = lava.dispatcher.commands:connect
    devices = lava.dispatcher.commands:devices
    power-cycle = lava.dispatcher.commands:power_cycle

    [lava.signal_handlers]
    add-duration = lava_dispatcher.signals.duration:AddDuration
    arm-probe = lava_dispatcher.signals.armprobe:ArmProbe
    shell-hooks = lava_dispatcher.signals.shellhooks:ShellHooks
    """,
    packages=find_packages(),
    package_data={
        'lava_dispatcher': [
            'default-config/lava-dispatcher/lava-dispatcher.conf',
            'default-config/lava-dispatcher/lava-dispatcher.conf',
            'default-config/lava-dispatcher/device-defaults.conf',
            'default-config/lava-dispatcher/device-types/*.conf',
            'default-config/lava-dispatcher/devices/*.conf',
            'pipeline/device_types/*.conf',
            'pipeline/devices/*.conf',
            'pipeline/devices/*.yaml',
            'device/sdmux.sh',
            'device/dynamic_vm_keys/lava*',
            'lava_test_shell/lava-background-process-start',
            'lava_test_shell/lava-background-process-stop',
            'lava_test_shell/lava-vm-groups-setup-host',
            'lava_test_shell/lava-installed-packages',
            'lava_test_shell/lava-os-build',
            'lava_test_shell/lava-test-case',
            'lava_test_shell/lava-test-case-attach',
            'lava_test_shell/lava-test-case-metadata',
            'lava_test_shell/lava-test-run-attach',
            'lava_test_shell/lava-test-runner',
            'lava_test_shell/lava-test-shell',
            'lava_test_shell/multi_node/*',
            'lava_test_shell/lmp/*',
            'lava_test_shell/distro/fedora/*',
            'lava_test_shell/distro/android/*',
            'lava_test_shell/distro/ubuntu/*',
            'lava_test_shell/distro/debian/*',
            'lava_test_shell/distro/oe/*',
        ],
        'linaro_dashboard_bundle': [
            'schemas/*',
            'test_documents/*',
        ],
    },
    install_requires=[
        'json-schema-validator >= 2.3',
        'lava-tool >= 0.4',
        'pexpect >= 2.3',
        'configglue',
        'PyYAML',
        'pyserial >= 2.6',
        'pyliblzma >= 0.5.3',
        'requests',
        'netifaces >= 0.10.0',
        'nose',
        'pyzmq'
    ],
    tests_require=[
        'pep8 >= 1.4.6',
        'testscenarios >= 0.4'
    ],
    data_files=[
        ('/usr/share/lava-dispatcher/',
            ['etc/tftpd-hpa']),
        ('/etc/exports.d',
            ['etc/lava-dispatcher-nfs.exports']),
        ('/etc/modprobe.d',
            ['etc/lava-options.conf']),
        ('/etc/modules-load.d/',
            ['etc/lava-modules.conf']),
        ('/etc/init.d/',
            ['etc/lava-slave.init']),
        ('/usr/share/lava-dispatcher/',
            ['etc/lava-slave.service'])
    ],
    scripts=[
        'lava-dispatch',
        'lava/dispatcher/lava-dispatcher-slave',
        'lava/dispatcher/lava-slave'
    ],
)
