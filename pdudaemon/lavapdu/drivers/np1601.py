#! /usr/bin/python

import logging
from lavapdu.drivers.apcbase import APCBase
log = logging.getLogger(__name__)


class NP1601(APCBase):

    @classmethod
    def accepts(cls, drivername):
        if drivername == "np1601":
            return True
        return False

    def _pdu_logout(self):
        self._back_to_main()
        log.debug("Logging out")
        self.connection.sendline("logout")

    def _back_to_main(self):
        log.debug("Returning to main menu")
        self.connection.sendline("")
        self.connection.expect('>')

    def _port_interaction(self, command, port_number):
        log.debug("Attempting command: %s port: %i",
                  command, port_number)
        # make sure in main menu here
        self._back_to_main()
        self.connection.sendline("")
        self.connection.expect(">")
        if command == "on":
            self.connection.sendline("pset %s 1" % port_number)
            self.connection.expect(">")
        elif command == "off":
            self.connection.sendline("pset %s 0" % port_number)
            self.connection.expect(">")
        else:
            log.debug("Unknown command!")

