#! /usr/bin/python
# -*- coding: utf-8 -*-
#
#  add_device.py
#
#  Copyright 2014 Linaro Limited
#  Author: Neil Williams <neil.williams@linaro.org>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

# The aim of this script is to be a stand-alone helper to add new
# devices to a LAVA instance - wrapping local calls to lava-server manage
# on that instance. It is intended for use by local admins or
# community packagers instead of LAVA users and hence is not part
# of lava-tool and is explicitly not intended to gain XMLRPC support.
# The script renders files suitable for use with ConfigFile, it is not
# intended to gain Django settings.


import optparse
import simplejson
import subprocess
import os
import tempfile


def template_bundle_stream():
    """
    Returns the current definition of the dashboard_app.BundleStream
    model to a template JSON. The fields need to be updated
    when new migrations are added which affect the BundleStream model.
    """
    stream_json = subprocess.check_output([
        "lava-server",
        "manage",
        "dumpdata",
        "--format=json",
        "dashboard_app.BundleStream"
    ])
    devices = simplejson.loads(stream_json)
    if len(devices) > 0:
        return None
    return {
        'fields': {
            "is_public": True,
            "group": None,
            "is_anonymous": True,
            "slug": "lab-health",
            "name": "lab-health",
            "pathname": "/anonymous/lab-health/",
            "user": 1,
        },
        "model": "dashboard_app.bundlestream",
    }


def template_device():
    """
    Returns the current definition of the lava_scheduler_app.Device
    model to a template JSON. The fields need to be updated
    when new migrations are added which affect the Device model.
    """
    device_json = subprocess.check_output([
        "lava-server",
        "manage",
        "dumpdata",
        "--format=json",
        "lava_scheduler_app.Device"
    ])
    devices = simplejson.loads(device_json)
    if len(devices) == 0:
        template = {
            'fields': {},
            "model": "lava_scheduler_app.device",
        }
    else:
        template = devices[0]  # borrow the layout of the first device
    template['pk'] = "HOSTNAME"
    template['fields']['current_job'] = None
    template['fields']['status'] = 1  # Device.IDLE
    template['fields']['group'] = None
    template['fields']['description'] = ''
    template['fields']['tags'] = []
    template['fields']['last_health_report_job'] = None
    template['fields']['device_version'] = ''
    template['fields']['health_status'] = 0  # unknown
    template['fields']['worker_host'] = None
    template['fields']['user'] = None
    template['fields']['device_type'] = "DEVICE_TYPE"
    template['fields']['physical_group'] = None
    template['fields']['is_public'] = True
    template['fields']['physical_owner'] = None
    return template


def template_device_type():
    """
    Returns the current definition of the lava_scheduler_app.DeviceType
    model to a template JSON. The script needs to be updated
    when new migrations are added which affect the DeviceType model.
    """
    type_json = subprocess.check_output([
        "lava-server",
        "manage",
        "dumpdata",
        "--format=json",
        "lava_scheduler_app.DeviceType"
    ])
    types = simplejson.loads(type_json)
    if len(types) == 0:
        template = {
            'fields': {},
            "model": "lava_scheduler_app.devicetype",
        }
    else:
        template = types[0]
    template['pk'] = "DEVICE_TYPE"
    template['fields']['health_check_job'] = ''
    template['fields']['display'] = True
    return template


def main(dt, name, options):
    config = {}
    # add power_on_cmd at 2016.03.22, wang.bo
    sequence = [
        'device_type',
        'hostname',
        'connection_command',
        'hard_reset_command',
        'power_off_cmd',
        'power_on_cmd'
    ]
    default_type = os.path.join("/etc/lava-dispatcher/device-types", "%s%s" % (dt, ".conf"))
    if not os.path.exists(default_type):
        # FIXME: integrate this into lava CLI to prevent the need
        # for this hardcoded path.
        default_type = os.path.join(
            "/usr/lib/python2.7/dist-packages/lava_dispatcher/",
            "default-config/lava-dispatcher/device-types/",
            "%s%s" % (dt, ".conf"))
        if not os.path.exists(default_type):
            print ("'%s' is not an existing device-type for this instance." % dt)
            print ("A default device_type configuration needs to be written as %s" % default_type)
            exit(1)
    config['device_type'] = dt
    deviceconf = os.path.join("/etc/lava-dispatcher/devices", "%s%s" % (name, ".conf"))
    if os.path.exists(deviceconf):
        print ("'%s' is an existing device on this instance." % name)
        print ("If you want to add another device of type %s, use a different hostname." % default_type)
        exit(1)
    config['hostname'] = name
    # FIXME: need a config file for daemon, pdu hostname and telnet ser2net host
    if options.pduport:
        try:
            pdu_ip = options.pduport.split(":")[0]
            pdu_port = int(options.pduport.split(":")[1])
        except ValueError:
            print ("Unable to parse %s as a port number" % options.pduport)
            exit(1)
        # add power_off_cmd and power_on_cmd,, wang.bo
        config['hard_reset_command'] = "/usr/bin/pduclient " \
                                       "--daemon localhost " \
                                       "--hostname %s --command reboot " \
                                       "--port %02d" % (pdu_ip, pdu_port)
        config['power_off_cmd'] = "/usr/bin/pduclient " \
                                  "--daemon localhost " \
                                  "--hostname %s --command off " \
                                  "--port %02d" % (pdu_ip, pdu_port)
        config['power_on_cmd'] = "/usr/bin/pduclient " \
                                 "--daemon localhost " \
                                 "--hostname %s --command on " \
                                 "--port %02d" % (pdu_ip, pdu_port)
    else:
        print("Skipping hard_reset_command for %s" % name)

    if options.socatport:
        # config['connection_command'] = "telnet localhost %d" % options.telnetport
        config['connection_command'] = "socat stdin,raw,echo=0 tcp:%s" % options.socatport
    else:
        print("Skipping connection_command for %s" % name)

    if options.macaddr:
        config['macaddr'] = options.macaddr
    else:
        print("Skipping macaddr for %s" % name)

    if options.sn:
        config['sn'] = options.sn
    else:
        print("Skipping sn for %s" % name)

    if options.signal:
        config['signal'] = options.signal
    else:
        print("Skipping signal for %s" % name)
        config['signal'] = 'false'

    template = [template_device_type()]
    template[0]['pk'] = dt
    template.append(template_device())
    template[1]['pk'] = name
    template[1]['fields']['device_type'] = dt
    if options.simulate:
        for key in sequence:
            if key in config:
                print "%s = %s" % (key, config[key])
        print simplejson.dumps(template, indent=4)
        return 0
    with open(deviceconf, 'w') as f:
        for key in sequence:
            if key in config:
                f.write("%s = %s\n" % (key, config[key]))
    fd, json = tempfile.mkstemp(suffix=".json", text=True)
    if options.bundlestream:
        template.append(template_bundle_stream())
    with open(json, 'w') as f:
        simplejson.dump(template, f, indent=4)
        f.write("\n")
    # sadly, lava-server manage loaddata exits 0 even if no data was loaded
    # so this only catches errors in lava-server itself.
    loaded = subprocess.check_call([
        "lava-server",
        "manage",
        "loaddata",
        "%s" % json
    ])
    if loaded:
        print "lava-server manage loaddata failed for %s" % json
        exit(1)
    else:
        os.close(fd)
        os.unlink(json)
    return 0

if __name__ == '__main__':
    usage = "Usage: %prog devicetype devicename [-p pduport] [-t socatport] [-m macaddr] [-n sn] [-g signal]"
    description = "LAVA device helper. Allows local admins to add devices to a " \
                  "running instance by creating the database entry and creating an initial " \
                  "device configuration. Optionally add the pdu port and ser2net port to use " \
                  "for serial connections using socat. This script is intended for initial setup only." \
                  "pduport settings are intended to support lavapdu only." \
                  "socat settings are intended to support socat only." \
                  "macaddr set device mac address." \
                  "sn set device sn." \
                  "signal judge device has signale connected.\n" \
                  "2016.06.24, wang.bo"
    pduport = None
    socatport = None
    macaddr = None
    sn = None
    signal = None
    parser = optparse.OptionParser(usage=usage, description=description)
    parser.add_option("-p", "--pduport", dest="pduport", action="store",
                      type="string", help="PDU ip and port number (ex: 172.16.117.10:04)")
    parser.add_option("-t", "--socatport", dest="socatport", action="store",
                      type="string", help="socat port (ex: 172.16.117.20:4196)")
    parser.add_option("-m", "--macaddr", dest="macaddr", action="store",
                      type="string", help="device mac address (ex: 9C:A6:9D:00:01:FF)")
    parser.add_option("-n", "--sn", dest="sn", action="store",
                      type="string", help="device sn")
    parser.add_option("-g", "--signal", dest="signal", action="store",
                      type="string", help="device has signal connected (ex: true)")
    parser.add_option("-b", "--bundlestream", dest="bundlestream", action="store_true",
                      help="add a lab health bundle stream if no streams exist.")
    parser.add_option("-s", "--simulate", dest="simulate", action="store_true",
                      help="output the data files without adding the device.")
    (options, args) = parser.parse_args()
    if len(args) < 2:
        print("Missing devicetype and/or device hostname option, try -h for help")
        exit(1)
    main(args[0], args[1], options)
