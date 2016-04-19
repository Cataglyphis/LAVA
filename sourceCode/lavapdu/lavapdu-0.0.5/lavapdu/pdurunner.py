#! /usr/bin/python

#  Copyright 2013 Linaro Limited
#  Author Matt Hart <matthew.hart@linaro.org>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

# Modify at 2016.03.21 to offer support for Synaccess NP1601DT
# Author: Wang Bo <wang.bo@whaley.cn>

import logging
import time
import traceback
from lavapdu.dbhandler import DBHandler
from lavapdu.drivers.np1601 import NP1601


class PDURunner(object):

    def __init__(self, config):
        self.pdus = config["pdus"]
        self.settings = config["daemon"]
        logging.basicConfig(level=self.settings["logging_level"])
        logging.getLogger().setLevel(self.settings["logging_level"])
        logging.getLogger().name = "PDURunner"

    def get_one(self, db):
        job = db.get_next_job()
        if job:
            job_id, hostname, port, request = job
            logging.debug(job)
            logging.info("Processing queue item: (%s %s) on hostname: %s" % (request, port, hostname))
            self.do_job(hostname, port, request)
            db.delete_row(job_id)
        else:
            logging.debug("Found nothing to do in database")

    def driver_from_hostname(self, hostname):
        logging.debug("Trying to find a driver for hostname %s" % hostname)
        logging.debug(self.pdus)
        if hostname in self.pdus:
            drivername = (self.pdus[hostname]["driver"])
        else:
            raise NotImplementedError("No configuration available for hostname %s\n"
                                      "Is there a section in the lavapdu.conf?" % hostname)
        logging.debug("Config file wants driver: %s" % drivername)
        # modify by Wang Bo @ 2016.01.06
        if drivername == "np1601":
            conn = NP1601(hostname, self.pdus)
            return conn
        else:
            logging.warn("No driver np1601 found in hostname %s\n" % hostname)
            exit(1)

    def do_job(self, hostname, port, request, delay=0):
        retries = self.settings["retries"]
        conn = None
        while retries > 0:
            try:
                conn = self.driver_from_hostname(hostname)
                return conn.handle(request, port, delay)
            except Exception as e:
                logging.warn(traceback.format_exc())
                logging.warn("Failed to execute job: %s %s %s (attempts left %i) error was %s" %
                             (hostname, port, request, retries, e.message))
                if conn:
                    conn.bombout()
                time.sleep(5)
                retries -= 1
        return False

    def run_me(self):
        logging.info("Starting up the PDURunner")
        while 1:
            db = DBHandler(self.settings)
            self.get_one(db)
            db.close()
            del db
            time.sleep(2)
