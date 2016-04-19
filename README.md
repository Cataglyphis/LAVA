## LAVA
branch master: configuration of LAVA on Ubuntu 14.04 LTS

branch werewolf: configuration of LAVA on Ubuntu 15.10

### Add bootstrap js file (for Ubuntu 14.04 only)
```shell
sudo cp bootstrap-3.1.1.min.js /usr/lib/python2.7/dist-packages/lava_server/lava-server/js/
```
### Add PDU driver for Synaccess NP1601DT
```shell
cd pdudaemon
sudo chmod a+x install
sudo ./install
```

### Add LAVA source code
```shell
cd dist-packages
sudo chmod a+x install
sudo ./install
```

### Add ser2net configuration
since the serial port may change after reboot, so traverse the definition in /sys/class/tty/, and modify the corresponding device defined in ser2net.conf
