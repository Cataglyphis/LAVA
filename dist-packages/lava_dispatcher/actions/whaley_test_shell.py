#!/usr/bin/python

# Author: Bo Wang <wang.bo@whaley.cn>
# Date: 2016.01.29
# add _results() at 2016.02.24

import shutil
import time
import logging
import stat
import os

from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from pyvirtualdisplay import Display
from lava_dispatcher.actions import BaseAction

# 755 file permissions
XMOD = stat.S_IRWXU | stat.S_IXGRP | stat.S_IRGRP | stat.S_IXOTH | stat.S_IROTH


class cmd_whaley_test_shell(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'script': {'type': 'string', 'optional': False},
            'debug': {'type': 'boolean', 'optional': True, 'default': False},
            'case_debug': {'type': 'string', 'optional': True},
        },
        'additionalProperties': False,
    }

    def __init__(self, context):
        super(cmd_whaley_test_shell, self).__init__(context)

    def run(self, script=None, debug=False, case_debug=None):
        # bootloader
        target = self.client.target_device
        # script = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py /home/.../LAVA.json"
        # script_name = "/home/dqa/workspace/LAVA/android-automation/TAP/whaleyTAP.py"
        # script_path = "/home/dqa/workspace/LAVA/android-automation/TAP"
        script = str(script).strip()
        script_name = script.split(' ')[0]
        script_path = os.path.split(script_name)[0]
        logging.info("Script name is: %s", script_name)
        logging.info("Script path is: %s", script_path)
        if os.path.isfile(script_name) and os.path.isdir(script_path):
            current_dir = os.getcwd()
            target_dir = script_path
            logging.info("change dir to %s", target_dir)
            os.chdir(target_dir)
            current_user = os.listdir("/home")[0]
            logging.info("pull the latest code with cmd: sudo -u %s git pull", current_user)
            os.system("sudo -u %s git pull" % current_user)
            os.chdir(current_dir)
            case_json = target.whaley_file_system(script_path, debug, case_debug)
            os.chmod(script_name, XMOD)
            logging.info("run command in file: %s", script_name)
            logging.info("command parameter: %s", case_json)
            script_name = script_name + " " + case_json
            self.context.run_command(script_name)
        else:
            # script invalid, use '/tmp/' instead
            logging.warning("invalid script parameter, use /tmp/ instead")
            target.whaley_file_system('/tmp/', debug, case_debug)

        # reconnect the serial connection
        target.whaley_file_system(script_path, debug, case_debug)
        # self._results(script_path)

    # for robot framework, extract the result of each case
    # report_path: path of report.html
    def _results(self, path):
        logging.info("log directory: %s" % self.context.output.output_dir)
        logging.debug("get the current directory of report.html")
        deviceinfo_path = os.path.join(path, "deviceInfo.conf")
        report_path = ""
        with open(deviceinfo_path, 'r') as fin:
            for line in fin.readlines():
                # use "output=" instead of "output"
                if "output=" in line:
                    report_path = line.strip().split("=")[1]
                    break
            else:
                logging.warning("No output path found in deviceInfo.conf")
                return
        logging.info("current directory of report.html is: %s" % report_path)
        target = os.path.join(self.context.output.output_dir, "output")
        logging.info("copy report.html from %s to %s" % (report_path, target))
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(report_path, target)
        logging.info("extract report.html")
        log_file_path = os.path.join(self.context.output.output_dir, "browser.log")
        log_file = open(log_file_path, "w")
        # open one xvfb, set size to (1024, 768)
        display = Display(visible=0, size=(1024, 768))
        display.start()
        firefox_binary = FirefoxBinary(log_file=log_file)
        browser = webdriver.Firefox(firefox_binary=firefox_binary)
        # set browser size to the same value as display window
        # otherwise, can't click some element in the website
        browser.set_window_size(1024, 768)
        # file:///, os.path.join already add /
        file_path = "file://" + os.path.join(target, "report.html")
        browser.get(file_path)
        time.sleep(3)
        try:
            browser.find_element_by_css_selector("a[href=\"#totals?all\"]").click()
            time.sleep(5)
            browser.find_element_by_id("test-details")
            logging.info("Click all tests successfully")
            browser.find_element_by_xpath("//table[@id=\"test-details\"]/thead/tr/th[8]").click()
            time.sleep(5)
            table = "//table[@id=\"test-details\"]/tbody/tr"
            for element in browser.find_elements_by_xpath(table):
                name = element.get_attribute("title").split(".")[-1]
                status = element.find_element_by_class_name("details-col-status").text
                if status == "FAIL":
                    status = "fail"
                else:
                    status = "pass"
                # change elapsed from "00:01:20.234" to seconds
                elapsed = element.find_element_by_class_name("details-col-elapsed").text.strip().split(".")[0]
                elapsed = elapsed.split(":")
                elapsed = map(int, elapsed)
                execution_time = elapsed[0] * 60.0 * 60.0 + elapsed[1] * 60.0 + elapsed[2]
                execution_time = "{0:.2f}".format(execution_time)
                msg = element.find_element_by_class_name("details-col-msg").text
                # tag = element.find_element_by_class_name("details-col-tags").text
                self.context.test_data.add_result(name, status, execution_time, 'seconds', message=msg)
        except Exception as e:
            logging.warning("cant't get test results from report.html")
            logging.warning("exception info: %s" % unicode(str(e)))
        finally:
            # close browser, display and log_file
            browser.quit()
            display.stop()
            log_file.close()
