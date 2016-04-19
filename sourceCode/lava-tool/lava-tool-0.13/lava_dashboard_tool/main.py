# Copyright (C) 2011  Linaro Limited
#
# Author: Zygmunt Krynicki <zygmunt.krynicki@linaro.org>
# Author: Michael Hudson-Doyle <michael.hudson@linaro.org>
#
# This file is part of lava-dashboard-tool.
#
# lava-dashboard-tool is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# as published by the Free Software Foundation
#
# lava-dashboard-tool is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with lava-dashboard-tool.  If not, see <http://www.gnu.org/licenses/>.


from lava_tool.dispatcher import LavaDispatcher, run_with_dispatcher_class


class LaunchControlDispatcher(LavaDispatcher):

    toolname = 'lava_dashboard_tool'
    description = """
    Command line tool for interacting with Lava Dashboard
    """
    epilog = """
    All bugs should be reported to Linaro at -
    https://bugs.linaro.org/enter_bug.cgi?product=LAVA%20Framework
    """


def main():
    run_with_dispatcher_class(LaunchControlDispatcher)
