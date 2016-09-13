# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import argparse
from ConfigParser import SafeConfigParser
import json
from multiprocessing import Pipe
from multiprocessing import Process
import os
import sys
import test


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        desc = "Tests uptime for a list of services."
        usage_string =\
            "[-s/--services] ([-t/--time] | [-d/--daemon]) [-o/--output-file]"

        super(ArgumentParser, self).__init__(usage=usage_string,
                                             description=desc)

        self.add_argument(
            "-s", "--services", metavar="<comma-delimited services list>",
            required=False, default=None)

        group = self.add_mutually_exclusive_group()
        group.add_argument(
            "-t", "--times", metavar="<amount of seconds to run>",
            required=False, default=60, type=int)
        group.add_argument(
            "-d", "--daemon", required=False, action='store_true')

        self.add_argument(
            "-o", "--output-file", metavar="<path to output file>",
            required=False, default=None)


def entry_point():
    cl_args = ArgumentParser().parse_args()

    # Initialize Config Variables
    config = SafeConfigParser()
    config.read("os.cnf")
    version = config.get("openstack", "version")
    user = config.get("openstack", "user")
    password = config.get("openstack", "password")
    tenant = config.get("openstack", "tenant")
    auth_url = config.get("openstack", "auth_url")
    services_list = config.get("openstack", "services_list")
    daemon_file = config.get("openstack", "daemon_file") or os.path.join(
        sys.prefix, "api.uptime.stop")
    output_file = cl_args.output_file or config.get("openstack", "output_file")

    if cl_args.daemon and os.path.exists(daemon_file):
        os.remove(daemon_file)

    services = [service.strip() for service in
                (cl_args.services or services_list).split(",")]

    mad = test.ApiUptime(version, user, password, tenant, auth_url)

    time_value = cl_args.daemon if cl_args.daemon else cl_args.times

    pipes = []
    for s in services:
        p, c = Pipe()
        pipes.append(p)
        Process(target=mad.uptime, args=(c, s, time_value,)).start()
        c.close()

    if cl_args.daemon:
        while True:
            if os.path.exists(daemon_file):
                for pipe in pipes:
                    pipe.send("STOP")
                break

    outputs = [pipe.recv() for pipe in pipes]
    final_output = {k: v for d in outputs for k, v in d.items()}

    if output_file is None or output_file == '':
        print('{0}'.format(json.dumps(final_output)))
    else:
        with open(output_file, 'w') as out:
            out.write(json.dumps(final_output))


if __name__ == "__main__":
    entry_point()
