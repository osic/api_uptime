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

import datetime
from multiprocessing import Pipe
from multiprocessing import Process
import sys
from time import sleep

from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient
from swiftclient import client as swiftclient


class ApiUptime(object):
    def __init__(self, version, username, password, tenant, auth_url, verbose):
        self.verbose = verbose
        if self.verbose:
            print('ApiUptime.__init__ entering')
        self.nova = novaclient.Client(version, username, password, tenant,
                                      auth_url)
        self.neutron = neutronclient.Client(username=username,
                                            password=password,
                                            project_name=tenant,
                                            auth_url=auth_url)
        self.cinder = cinderclient.Client('2', username, password, tenant,
                                          auth_url)
        self.swift = swiftclient.Connection(authurl=auth_url, user=username,
                                            tenant_name=tenant, key=password,
                                            auth_version='2')

        if self.verbose:
            print('ApiUptime.__init__ leaving')

    def _proc_helper(self, function, conn, additional_args=None):
        try:
            if additional_args is not None:
                function(additional_args)
            else:
                function()
            conn.send(True)
            conn.close()
        except Exception:
            conn.send(False)
            conn.close()

    def _uptime(self, conn, service, times, function, additional_args=None):
        if self.verbose:
            print('ApiUptime._uptime entering, service={0}'.format(service))
            print('                            times={0}'.format(times))
        start_time = datetime.datetime.now()
        if times is True:
            times = xrange(sys.maxint)
        else:
            times = xrange(times)
        pipes = []
        for _ in times:
            if conn.poll() and conn.recv() == "STOP":
                break
            if self.verbose:
                print('ApiUptime._uptime pinging service={0} at {1}'.format(
                    service, datetime.datetime.now()))
            p, c = Pipe()
            pipes.append(p)
            Process(target=self._proc_helper,
                    args=(function, c, additional_args)).start()
            c.close()
            sleep(1)
        if self.verbose:
            print("ApiUptime._uptime: done with pings")
        output = [pipe.recv() for pipe in pipes]
        # outputs is a list of True & False values, sum(output) will return
        # the amount of True values in the list (as True is equivalent to 1 in
        # Python and False is equivalent to 0)
        self.report(conn, service, sum(output), len(output), str(start_time),
                    str(datetime.datetime.now()))

        if self.verbose:
            print('ApiUptime._uptime leaving, service={0}'.format(service))

    def uptime(self, conn, service, times):
        if self.verbose:
            print('ApiUptime.uptime entering, service={0}'.format(service))
        if service == "neutron":
            self._uptime(conn, "neutron", times, self.neutron.list_subnets)
        elif service == "glance":
            self._uptime(conn, "glance", times, self.nova.images.list)
        elif service == "nova":
            self._uptime(conn, "nova", times, self.nova.servers.list)
        elif service == "cinder":
            self._uptime(conn, "cinder", times, self.cinder.volumes.list)
        elif service == "swift":
            self._uptime(conn, "swift", times, self.swift.get_account)
        if self.verbose:
            print('ApiUptime.uptime leaving, service={0}'.format(service))

    def report(self, conn, service, success, total, start_time, end_time):
        if self.verbose:
            print('ApiUptime.report entered')
        uptime_pct = 100 * (float(success)/ total)
        conn.send({
            service: {
                "uptime_pct": uptime_pct,
                "total_requests": total,
                "successful_requests": success,
                "failed_requests": total - success,
                "start_time": start_time,
                "end_time": end_time}})
        conn.close()
        if self.verbose:
            print('ApiUptime.report leaving')
