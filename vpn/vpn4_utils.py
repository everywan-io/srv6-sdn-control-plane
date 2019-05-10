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


import sshutil

from sshutil.cmd import SSHCommand

import telnetlib
import socket
from optparse import OptionParser


def add_default_via(router, intf, ip):
	# Utility to close a ssh session
	def close_ssh_session(session):
	  # Close the session
	  remoteCmd.close()
	  # Flush the cache
	  remoteCmd.cache.flush()
	# Add the default via
	cmd = "ip route add default via %s dev %s" % (ip, intf)
	print router
	print cmd
	print
	remoteCmd = SSHCommand(cmd, router, 22, "root", "root")
	remoteCmd.run_status_stderr()
	# Close the session
	close_ssh_session(remoteCmd)


def del_default_via(router):
	# Utility to close a ssh session
	def close_ssh_session(session):
	  # Close the session
	  remoteCmd.close()
	  # Flush the cache
	  remoteCmd.cache.flush()
	# Add the default via
	cmd = "ip route del default"
	remoteCmd = SSHCommand(cmd, router, 22, "root", "root")
	remoteCmd.run_status_stderr()
	# Close the session
	close_ssh_session(remoteCmd)


def add_address_quagga(router, port, intf, ip):
	# Establish a telnet connection with the zebra daemon
	# and try to reconfigure the addressing plan of the router
	router = str(router)
	port = str(port)
	intf = str(intf)
	ip = str(ip)
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
		# Add the new IP address
		tn.write("ip address %s\r\n" % ip)
		# Close interface configuration
		tn.write("q" + "\r\n")
		# Close configuration mode
		tn.write("q" + "\r\n")
		# Close privileged mode
		tn.write("q" + "\r\n")
		# Close telnet
		tn.close()
	except socket.error:
		print "Error: cannot establish a connection to %s on port %s" % (str(router), str(port))


def del_address_quagga(router, port, intf, ip):
	# Establish a telnet connection with the zebra daemon
	# and try to reconfigure the addressing plan of the router
	router = str(router)
	port = str(port)
	intf = str(intf)
	ip = str(ip)
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
		# Add the new IP address
		tn.write("no ip address %s\r\n" % ip)
		# Close interface configuration
		tn.write("q" + "\r\n")
		# Close configuration mode
		tn.write("q" + "\r\n")
		# Close privileged mode
		tn.write("q" + "\r\n")
		# Close telnet
		tn.close()
	except socket.error:
		print "Error: cannot establish a connection to %s on port %s" % (str(router), str(port))

def flush_addresses_ssh(router, intf):
	# Utility to close a ssh session
	def close_ssh_session(session):
	  # Close the session
	  remoteCmd.close()
	  # Flush the cache
	  remoteCmd.cache.flush()
	# Flush addresses
	cmd = "ip addr flush dev %s" % intf
	remoteCmd = SSHCommand(cmd, router, 22, "root", "root")
	remoteCmd.run_status_stderr()
	# Close the session
	close_ssh_session(remoteCmd)

def add_address_ssh(router, intf, ip):
	# Utility to close a ssh session
	def close_ssh_session(session):
	  # Close the session
	  remoteCmd.close()
	  # Flush the cache
	  remoteCmd.cache.flush()
	# Add the address
	cmd = "ip addr add %s dev %s" % (ip, intf)
	remoteCmd = SSHCommand(cmd, router, 22, "root", "root")
	remoteCmd.run_status_stderr()
	# Close the session
	close_ssh_session(remoteCmd)

def del_address_ssh(router, intf, ip):
	# Utility to close a ssh session
	def close_ssh_session(session):
	  # Close the session
	  remoteCmd.close()
	  # Flush the cache
	  remoteCmd.cache.flush()
	# Add the address
	cmd = "ip addr del %s dev %s" % (ip, intf)
	remoteCmd = SSHCommand(cmd, router, 22, "root", "root")
	remoteCmd.run_status_stderr()
	# Close the session
	close_ssh_session(remoteCmd)