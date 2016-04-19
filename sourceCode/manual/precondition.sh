#! /bin/sh

set -e

sudo apt-get install debhelper dh-python python-all python-dev python-all-dev python-pip \
    python3-sphinx python-setuptools devscripts xvfb xserver-xephyr vnc4server

sudo pip install selenium pyvirtualdisplay

# lava-dev

sudo apt-get install build-essential ca-certificates dpkg-dev fakeroot po-debconf xsltproc
sudo apt-get install lava-dev


# lava-tool

sudo apt-get install libpython2.7-stdlib python-argcomplete python-jinja2 python-json-schema-validator \
    python-keyring python-xdg python-yaml python-mock

# lava-coordinator

sudo apt-get install python-daemon


# lava-pdu
# lavapdu-daemon

sudo apt-get install postgresql postgresql-client postgresql-common python-lockfile python-pexpect \
    python-psycopg2 telnet

# lavapdu-client


# lava-dispatcher -> lava-tool

sudo apt-get install kpartx ser2net sshfs tftpd-hpa u-boot-tools unzip xz-utils python-configglue python-lzma \
    python-netifaces python-nose python-zmq python-requests python-serial bridge-utils bzr htop lxc nfs-kernel-server \
    ntp openbsd-inetd python-launchpadlib python-setproctitle rpcbind


# lava-server
# lava-server-doc
# lava-server -> lava-dispatcher, lava-tool
sudo apt-get install apache2 debconf fuse iproute2 libapache2-mod-uwsgi libapache2-mod-wsgi libjs-excanvas python-dateutil \
    python-django-auth-ldap python-twisted libjs-jquery-cookie libjs-jquery-flot lshw openssh-client openssh-server \
    python-django-auth-openid python-django-kvstore python-django-restricted-resource python-django-south python-django-tables2 \
    python-docutils python-markdown python-markupsafe python-pygments python-simplejson python-voluptuous


# lava
sudo apt-get install binfmt-support btrfs-tools linaro-image-tools python-linaro-image-tools python-parted qemu-user-static
sudo a2enmod wsgi


