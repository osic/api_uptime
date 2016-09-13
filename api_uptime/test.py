import datetime
from time import sleep
from multiprocessing import Pipe, Process
import sys

from novaclient import client as novaclient
from neutronclient.v2_0 import client as neutronclient
from cinderclient import client as cinderclient
from swiftclient import client as swiftclient


class ApiUptime():
    def __init__(self, version, username, password, tenant, auth_url):
        self.nova = novaclient.Client(version, username, password, tenant, auth_url)
	self.neutron = neutronclient.Client(username=username, password=password, project_name=tenant, auth_url=auth_url)
	self.cinder = cinderclient.Client('2', username, password, tenant, auth_url)
	self.swift = swiftclient.Connection(authurl=auth_url, user=username, tenant_name=tenant, key=password, auth_version='2')

    def _proc_helper(self, function, conn, additional_args=None):
        try:
            if additional_args <> None:
                function(additional_args)
            else:
                function()
            conn.send(True)
            conn.close()
        except:
            conn.send(False)
            conn.close()

    def _uptime(self, conn, service, times, function, additional_args=None):
        start_time = datetime.datetime.now()
        if times is True:
            times = xrange(sys.maxint)
        else:
            times = xrange(times)
        pipes = []
        for _ in times:
            if conn.poll() and conn.recv() == "STOP":
                break
            p, c = Pipe()
            pipes.append(p)
            Process(target=self._proc_helper, args=(function, c, additional_args)).start()
            c.close()
            sleep(1)
        output = [pipe.recv() for pipe in pipes]
        # outputs is a list of True & False values, sum(output) will return
        # the amount of True values in the list (as True is equivalent to 1 in
        # Python and False is equivalent to 0)
        self.report(conn, service, sum(output), len(output), str(start_time), str(datetime.datetime.now()))

    def uptime(self, conn, service, times):
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

    def report(self, conn, service, success, total, start_time, end_time):
        uptime_pct = 100 * (success/total)
        conn.send({
            service: {
                "uptime_pct": uptime_pct,
                "total_requests": total,
                "successful_requests": success,
                "failed_requests": total - success,
                "start_time": start_time,
                "end_time": end_time}})
        conn.close()
