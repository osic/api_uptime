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
import urllib2
import json
import requests
import os

from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient


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
	self.url = auth_url + '/'
        self.data = '{"auth":{"passwordCredentials":{"username":"' + username + '","password": "' + password + '"},"tenantName": "' + tenant + '"}}'
        self.headers = self._get_token()
	self.swift_url = self._get_swift_url()
	self.nova_url = self._get_nova_url()
	self.error_output = None

        if self.verbose:
            print('ApiUptime.__init__ leaving')
	
    def get_swift_info(self):
        response = str(requests.put(self.swift_url + 'info', headers=self.headers))
	
        if any(c in response for c in ('201','200','202')): return True
	if '401' in response:
	    print "Getting token, it may have expired."
            self.headers = self._get_token()
	    return True
        return False

    def nova_list_servers(self):
        response = str(requests.get(self.nova_url + 'servers', headers=self.headers))
        
	if any(c in response for c in ('201','200','202')): return True
        if '401' in response:
            print "Getting token, it may have expired."
            self.headers = self._get_token()
            return True
        return False

    def _get_token(self):
        get_token = None
        headers = {'Content-Type': 'application/json'}
        url = self.url + 'tokens'
        req = urllib2.Request(url, self.data, {'Content-Type': 'application/json'})

	try:
            f = urllib2.urlopen(req)
	except Exception as e:
	    if any(c in str(e) for c in ('503','404')):
		print "Error getting token"
		return False
	    else:
		self.error_output = str(e) + " on line 84"
		return False

        for x in f:
            d = json.loads(x)
            token = d['access']['token']['id']
	f.close()
        header = {'X-Auth-Token': token}
        return header

    def _get_swift_url(self):
	swift_url = None
        headers = {'Content-Type': 'application/json'}
        url = self.url + 'tokens'
        req = urllib2.Request(url, self.data, {'Content-Type': 'application/json'})

        try:
            f = urllib2.urlopen(req)
        except Exception as e:
	    print e 
	    if any(c in str(e) for c in ('503','404')):
		self.error_output = "Error getting swift url. Is swift installed?"
		print "Or Keystone maybe down, swift tests will not start."
                return False
	    else:
		self.error_output = str(e) + " on line 109"
		return False

	try:
            for x in f:
                d = json.loads(x)
                for j in d['access']['serviceCatalog']:
                    if j['name'] == 'swift':
                        for k in j['endpoints']:
                            swift_url = k['internalURL']
	except Exception as e:
	    self.error_output = str(e) + " on line 121"
	    print "Error getting swift url. Is swift installed?"
	    print "Or Keystone maybe down, swift tests will not start."
	    f.close()
	    return False
        f.close()

	if swift_url == None: return False
        return swift_url + '/'

    def _get_nova_url(self):
        nova_url = None
        headers = {'Content-Type': 'application/json'}
        url = self.url + 'tokens'
        req = urllib2.Request(url, self.data, {'Content-Type': 'application/json'})

        try:
            f = urllib2.urlopen(req)
        except Exception as e:
            print e
            if any(c in str(e) for c in ('503','404')):
                self.error_output = "Error getting nova url. Is nova installed?"
                print "Or Keystone maybe down, swift tests will not start."
                return False
	    else:
		self.error_output = str(e) + " on line 145"
		return False

        try:
            for x in f:
                d = json.loads(x)
                for j in d['access']['serviceCatalog']:
                    if j['name'] == 'nova':
                        for k in j['endpoints']:
                            nova_url = k['internalURL']
        except Exception as e:
            self.error_output = str(e) + " on line 157"
            print "Error getting nova url. Is nova installed?"
            print "Or Keystone maybe down, nova tests will not start."
            f.close()
            return False
        f.close()

        if nova_url == None: return False

        return nova_url + '/'


    def _proc_helper(self, service, function, build_start, duration, additional_args=None):
	response = True
        try:
            if additional_args is not None:
                function(additional_args)
	    elif service == 'swift' or service == 'nova':
		if function():
		    status = 1
                    #conn.send(True)
                    #conn.close()
		else:
		    status = 0
                    #conn.send(False)
                    #conn.close()
            else:
                function()
	        status = 1
                #conn.send(True)
                #conn.close()
        except Exception as e:
	    self.error_output = str(e) + " on line 189"
	    status = 0
            #conn.send(False)
            #conn.close()

	timestamp = str(datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"))
	log = {"service": service, "status": status, "timestamp": timestamp, "duration": duration, "total_down": 0, "error": self.error_output, "time_run_started": build_start}
        f = open('../../output/' + service + '_api_status.json','a')
        f.write(json.dumps(log) + "\n")
        f.close()

    def _uptime(self, conn, service, times, function, additional_args=None):
        if self.verbose:
            print('ApiUptime._uptime entering, service={0}'.format(service))
            print('                            times={0}'.format(times))
        start_time = str(datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"))
        count = 1
        if times is True:
            times = xrange(sys.maxint)
        else:
            times = xrange(times)
        pipes = []
        for _ in times:
            if conn.poll() and conn.recv() == "STOP":
                break
	    elif os.path.isfile('/usr/api.uptime.stop')
		break
            if self.verbose:
                print('ApiUptime._uptime pinging service={0} at {1}'.format(
                    service, datetime.datetime.now()))
            #p, c = Pipe()
            #pipes.append(p)
            Process(target=self._proc_helper,
                    args=(service, function, start_time, count, additional_args)).start()
            #c.close()
            sleep(1)
	    count += 1
        if self.verbose:
            print("ApiUptime._uptime: done with pings")
        #output = [pipe.recv() for pipe in pipes]
	#This is just filler stuff
	output = [1,1]
        # outputs is a list of True & False values, sum(output) will return
        # the amount of True values in the list (as True is equivalent to 1 in
        # Python and False is equivalent to 0)
        self.report(conn, service, sum(output), len(output), str(start_time),
                    str(datetime.datetime.now()))

        if self.verbose:
            print('ApiUptime._uptime leaving, service={0}'.format(service))

    def uptime(self, conn, service, times):

        open('../../output/' + service + '_api_status.json','w')

        if self.verbose:
            print('ApiUptime.uptime entering, service={0}'.format(service))
        if service == "neutron":
            self._uptime(conn, "neutron", times, self.neutron.list_subnets)
        elif service == "glance":
            self._uptime(conn, "glance", times, self.nova.images.list)
        elif service == "nova":
            #self._uptime(conn, "nova", times, self.nova.servers.list)
	    self._uptime(conn, "nova", times, self.nova_list_servers)
        elif service == "cinder":
            self._uptime(conn, "cinder", times, self.cinder.volumes.list)
        elif service == "swift":
            self._uptime(conn, "swift", times, self.get_swift_info)
        if self.verbose:
            print('ApiUptime.uptime leaving, service={0}'.format(service))

    def report(self, conn, service, success, total, start_time, end_time):
        if self.verbose:
            print('ApiUptime.report entered')
        uptime_pct = 100 * (float(success)/ total)
        uptime_pct = round(uptime_pct,2)
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
