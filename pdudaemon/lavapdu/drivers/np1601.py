#! /usr/bin/python

#  Create at 2016.01.06 to offer support for Synaccess NP1601DT
#  Author: Wang Bo <wang.bo@whaley.cn>

import logging
import pexpect


class NP1601(object):
    connection = None

    def __init__(self, hostname, pdus):
        logging.getLogger().name = "NP1601"
        self.hostname = hostname
        self.telnetport = 23
        self.pdus = pdus
        if "telnetport" in pdus[hostname]:
            self.telnetport = pdus[hostname]["telnetport"]
        self.exec_string = "/usr/bin/telnet %s %d" % (self.hostname, self.telnetport)
        self._get_connection()

    def _get_connection(self):
        logging.debug("Connection to NP1601 PDU with: %s" % self.exec_string)
        self.connection = pexpect.spawn(self.exec_string)
        username = self.pdus[self.hostname]["username"]
        password = self.pdus[self.hostname]["password"]
        self._pdu_login(username, password)

    def _pdu_login(self, username, password):
        logging.debug("Attempting login with username %s, password %s" % (username, password))
        self.connection.sendline("")
        self.connection.expect(">")
        self.connection.sendline("login")
        self.connection.expect("User ID:")
        self.connection.sendline("%s" % username)
        self.connection.expect("Password:")
        self.connection.sendline("%s" % password)

    def _pdu_logout(self):
        self._back_to_main()
        logging.debug("Logging out")
        self.connection.sendline("logout")

    def _back_to_main(self):
        logging.debug("Returning to main menu")
        self.connection.sendline("")
        self.connection.expect(">")

    def _port_interaction(self, command, port):
        logging.debug("Attempting command: %s port: %i" % (command, port))
        self._back_to_main()
        if command == "on":
            self.connection.sendline("pset %s 1" % port)
            self.connection.expect(">")
        else:
            self.connection.sendline("pset %s 0" % port)
            self.connection.expect(">")

    def handle(self, request, port, delay=0):
        logging.debug("Driver np1601 request: %s port: %s delay: %s" % (request, port, delay))
        if request == "on":
            self._port_interaction("on", port)
        elif request == "off":
            self._port_interaction("off", port)
        else:
            logging.debug("Unknown request to handle")
            raise NotImplementedError("Driver doesn't know how to %s" % request)
        self._pdu_logout()

    def bombout(self):
        logging.debug("Bombing out of driver: %s", self.connection)
        self.connection.close(force=True)
        del self
