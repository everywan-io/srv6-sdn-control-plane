#!/usr/bin/python

# Copyright (C) 2018 Carmine Scarpitta, Pier Luigi Ventre, Stefano Salsano - (CNIT and University of Rome "Tor Vergata")
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Utils for VPN use case
# 
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#


import telnetlib
import socket
from optparse import OptionParser


class VPNIntent:
    def __init__(self, name, interfaces, tenant_id):
      self.name = name
      # An interface is a tuple (router_id, interface_name, subnet)
      self.interfaces = interfaces
      self.tenant_id = tenant_id


def reconfigure_addressing_plan(router, port, intf, old_prefix, new_prefix, old_ipaddr, new_ipaddr):
	# Establish a telnet connection with the zebra daemon
	# and try to reconfigure the addressing plan of the router
	router = str(router)
	port = str(port)
	intf = str(intf)
	old_prefix = str(old_prefix)
	new_prefix = str(new_prefix)
	old_ipaddr = str(old_ipaddr)
	new_ipaddr = str(new_ipaddr)
	try:
		print "%s - Trying to reconfigure addressing plan" % router
		password = "srv6"
		# Init telnet
		tn = telnetlib.Telnet(router, port)
		# Password
		tn.read_until("Password: ")
		tn.write("%s\r\n" % password)
		# Terminal length set to 0 to not have interruptions
		tn.write("terminal length 0\r\n")
		# Enable
		tn.write("enable\r\n")
		# Password
		tn.read_until("Password: ")
		tn.write("%s\r\n" % password)
		# Configure terminal
		tn.write("configure terminal\r\n")
		# Interface configuration
		tn.write("interface %s\r\n" % intf)
		# Remove old IPv6 prefix
		tn.write("no ipv6 nd prefix %s\r\n" % old_prefix)
		# Add the new IPv6 prefix
		tn.write("ipv6 nd prefix %s\r\n" % new_prefix)
		# Remove old IPv6 address
		tn.write("no ipv6 address %s\r\n" % old_ipaddr)
		# Add the new IPv6 address
		tn.write("ipv6 address %s\r\n" % new_ipaddr)
		# Close interface configuration
		tn.write("q" + "\r\n")
		# Close configuration mode
		tn.write("q" + "\r\n")
		# Close privileged mode
		tn.write("q" + "\r\n")
		#print tn.read_all()
		# Close telnet
		tn.close()
	except socket.error:
		print "Error: cannot establish a connection to %s on port %s" % (str(router), str(port))
