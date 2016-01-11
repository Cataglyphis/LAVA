## LAVA
configuration of LAVA on Ubuntu 14.04 LTS

### Add bootstrap js file
```shell
sudo cp bootstrap-3.1.1.min.js /usr/lib/python2.7/dist-packages/lava_server/lava-server/js/
```
### Add PDU driver for Synaccess NP1601DT
```shell
cd pdudaemon
sudo chmod a+x install
sudo ./install
```
