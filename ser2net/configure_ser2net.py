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

from subprocess import Popen, PIPE

proc = Popen('ls -l /sys/class/tty', shell=True, stdout=PIPE, stderr=PIPE)
proc.wait()

ttyUSBResults = []

for line in proc.stdout.readlines():
    if 'ttyUSB' in line:
        print line


