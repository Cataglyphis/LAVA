# -*- coding: utf-8 -*-

# traverse the definition in /sys/class/tty/,
# and modify the corresponding device defined in ser2net.conf

# ttyUSB0 -> ../../devices/pci0000:00/0000:00:14.0/usb3/3-2/3-2.3/3-2.3:1.0/ttyUSB0/tty/ttyUSB0
# ttyUSB1 -> ../../devices/pci0000:00/0000:00:14.0/usb3/3-2/3-2.2/3-2.2:1.0/ttyUSB1/tty/ttyUSB1
# ttyUSB2 -> ../../devices/pci0000:00/0000:00:14.0/usb3/3-1/3-1.3/3-1.3:1.0/ttyUSB2/tty/ttyUSB2
# ttyUSB3 -> ../../devices/pci0000:00/0000:00:14.0/usb3/3-1/3-1.2/3-1.2:1.0/ttyUSB3/tty/ttyUSB3

# ttyUSB4 -> ../../devices/pci0000:00/0000:00:1c.2/0000:02:00.0/usb5/5-4/5-4:1.0/ttyUSB4/tty/ttyUSB4
# ttyUSB5 -> ../../devices/pci0000:00/0000:00:1c.2/0000:02:00.0/usb5/5-3/5-3:1.0/ttyUSB5/tty/ttyUSB5
# ttyUSB6 -> ../../devices/pci0000:00/0000:00:14.0/usb3/3-9/3-9.3/3-9.3:1.0/ttyUSB6/tty/ttyUSB6
# ttyUSB7 -> ../../devices/pci0000:00/0000:00:14.0/usb3/3-9/3-9.2/3-9.2:1.0/ttyUSB7/tty/ttyUSB7

# 2000:telnet:600:/dev/ttyUSB0:115200 8DATABITS NONE 1STOPBIT banner
# 2001:telnet:600:/dev/ttyUSB1:115200 8DATABITS NONE 1STOPBIT banner
# 2002:telnet:600:/dev/ttyUSB2:115200 8DATABITS NONE 1STOPBIT banner
# 2003:telnet:600:/dev/ttyUSB3:115200 8DATABITS NONE 1STOPBIT banner
# 2004:telnet:600:/dev/ttyUSB4:115200 8DATABITS NONE 1STOPBIT banner
# 2005:telnet:600:/dev/ttyUSB5:115200 8DATABITS NONE 1STOPBIT banner
# 2006:telnet:600:/dev/ttyUSB6:115200 8DATABITS NONE 1STOPBIT banner
# 2007:telnet:600:/dev/ttyUSB7:115200 8DATABITS NONE 1STOPBIT banner

# follow below rules:
# 2000 -> usb3/3-2/3-2.3/3-2.3:1.0 -> MSTAR-43-001
# 2001 -> usb3/3-2/3-2.2/3-2.2:1.0 -> MSTAR-43-003
# 2002 -> usb3/3-1/3-1.3/3-1.3:1.0 -> MSTAR-43-002
# 2003 -> usb3/3-1/3-1.2/3-1.2:1.0 -> MSTAR-43-004
# 2004 -> usb5/5-4/5-4:1.0 -> MSTAR-43-005
# 2005 -> usb5/5-3/5-3:1.0 -> MSTAR-43-007
# 2006 -> usb3/3-9/3-9.3/3-9.3:1.0 -> MSTAR-43-006
# 2007 -> usb3/3-9/3-9.2/3-9.2:1.0 -> MSTAR-43-007

import os
from subprocess import Popen, PIPE

proc = Popen('ls -l /sys/class/tty', shell=True, stdout=PIPE, stderr=PIPE)
proc.wait()

ttyUSBResults = {}
portDef = ['2000:', '2001:', '2002:', '2003:', '2004:', '2005:', '2006:', '2007:']
ser2netPort = {'2000:': '3-2.3',
               '2001:': '3-2.2',
               '2002:': '3-1.3',
               '2003:': '3-1.2',
               '2004:': '5-4',
               '2005:': '5-3',
               '2006:': '3-9.3',
               '2007:': '3-9.2'
               }

for line in proc.stdout.readlines():
    if 'ttyUSB' in line:
        # 3-2.3, 3-2.2, etc.
        port = line.split(':')[-2].split('/')[-1]
        ttyUSB = line.split('/')[-1].strip()
        ttyUSBResults[port] = ttyUSB

# ttyUSBResults = {'3-2.3': 'ttyUSB0', '3-2.2': 'ttyUSB1', ...}
print 'ttyUSB port: ', ttyUSBResults

for key, value in ser2netPort.items():
    ser2netPort[key] = ttyUSBResults[value]

# ser2netPort = {'2000:': 'ttyUSB0', '2001:': 'ttyUSB1', ...}
print 'ser2net port:', ser2netPort

# modify ser2net.conf
os.system('sudo service ser2net stop')
# backup the original conf file
os.rename('/etc/ser2net.conf', '/etc/ser2net_bak.conf')
with open('/etc/ser2net_bak.conf', 'r') as fin:
    with open('/etc/ser2net.conf', 'w') as fout:
        for line in fin.readlines():
            for port in portDef:
                if port in line:
                    line = line.replace(line.split(':')[3], '/dev/'+ser2netPort[port])
            fout.write('%s' % line)

os.system('sudo service ser2net start')
