#!/usr/bin/python

# Copyright (C) 2018 Carmine Scarpitta, Pier Luigi Ventre, Stefano Salsano - (CNIT and University of Rome 'Tor Vergata')
#
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Server of a Northbound interface based on gRPC protocol
#
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#

from __future__ import absolute_import, division, print_function

# General imports
from sshutil.cmd import SSHCommand
import sys
import logging
import telnetlib
import socket
import json
import time
import os
import random
from socket import AF_INET
from socket import AF_INET6
# ipaddress dependencies
from ipaddress import IPv4Interface, IPv6Interface
from ipaddress import IPv4Network, IPv6Network
from ipaddress import IPv4Address
from ipaddress import AddressValueError
# NetworkX dependencies
import networkx as nx
from networkx.readwrite import json_graph

ZEBRA_PORT = 2601
SSH_PORT = 22
MIN_TABLE_ID = 2
# Linux kernel supports up to 255 different tables
MAX_TABLE_ID = 255
# Table where we store our seg6local routes
LOCAL_SID_TABLE = 1
# Reserved table IDs
RESERVED_TABLEIDS = [0, 253, 254, 255]
RESERVED_TABLEIDS.append(LOCAL_SID_TABLE)

WAIT_TOPOLOGY_INTERVAL = 1

# SRv6 dependencies
from srv6_generators import SIDAllocator

# Logger reference
logger = logging.getLogger(__name__)


class VTEPIPv6NetAllocator:

  bit = 16
  net = u"fcfb::/%d" % bit
  prefix = 64

  def __init__(self): 
    print("*** Calculating Available Mgmt Addresses")
    self.hosts = (IPv6Network(self.net)).hosts()
  
  def nextVTEPAddress(self):
    n_host = next(self.hosts)
    return n_host.__str__()


class VTEPIPv4NetAllocator:

  bit = 8
  net = u"10.0.0.0/%d" % bit
  prefix = 16

  def __init__(self): 
    print("*** Calculating Available Mgmt Addresses")
    self.vtepnet = (IPv4Network(self.net)).hosts()
  
  def nextVTEPAddress(self):
    n_host = next(self.vtepnet)
    return n_host.__str__()


# Utiliy function to check if the provided table ID is valid
def validate_table_id(tableid):
    return tableid >= MIN_TABLE_ID and tableid <= MAX_TABLE_ID


def validate_tenantid(tenantid):
    return tenantid >= 0 and tenantid <= 2**32-1


def validate_vpn_type(vpn_type):
    return True     # TODO


# Utiliy function to check if the IP
# is a valid IPv6 address
def validate_ipv6_address(ip):
    if ip is None:
        return False
    try:
        IPv6Interface(ip)
        return True
    except AddressValueError:
        return False


# Utiliy function to check if the IP
# is a valid IPv4 address
def validate_ipv4_address(ip):
    if ip is None:
        return False
    try:
        IPv4Interface(ip)
        return True
    except AddressValueError:
        return False


# Utiliy function to check if the IP
# is a valid address
def validate_ip_address(ip):
    return validate_ipv4_address(ip) or validate_ipv6_address(ip)


# Utiliy function to get the IP address family
def getAddressFamily(ip):
    if validate_ipv6_address(ip):
        # IPv6 address
        return AF_INET6
    elif validate_ipv4_address(ip):
        # IPv4 address
        return AF_INET
    else:
        # Invalid address
        return None


class VPNType:
    IPv4VPN = 1
    IPv6VPN = 2

class VPN:
    def __init__(self, vpn_name, vpn_type, interfaces, tenantid, tunnel_mode): #tableid=-1):
        # VPN name
        self.vpn_name = vpn_name
        # VPN type
        self.vpn_type = vpn_type
        # Interfaces belonging to the VPN
        self.interfaces = dict()
        for interface in interfaces:
            routerid = interface.routerid
            interface_name = interface.interface_name
            if self.interfaces.get(routerid) is None:
                self.interfaces[routerid] = dict()
            self.interfaces[routerid][interface_name] = interface
        # Tenant ID
        self.tenantid = tenantid
        # Table ID
        #self.tableid = tableid
        #self.tunnel_specific_data = dict()
        self.tunnel_mode = tunnel_mode

    def removeInterface(self, routerid, interface_name):
        if self.interfaces.get(routerid) is not None \
                and self.interfaces[routerid].get(interface_name):
            del self.interfaces[routerid][interface_name]
            return True
        return False

    def numberOfInterfaces(self, routerid):
        return len(self.interfaces.get(routerid, dict()))

    def getInterface(self, routerid, interface_name):
        if self.interfaces.get(routerid) is not None:
            return self.interfaces[routerid].get(interface_name, None)
        return None


class Interface:
    def __init__(self, routerid, interface_name, interface_ip=None, subnets=None):
        # Router ID
        self.routerid = routerid
        # Interface name
        self.interface_name = interface_name
        # Router IP
        self.interface_ip = interface_ip
        # VPN prefix
        self.subnets = subnets


# IPv6 utility functions

def del_ipv6_nd_prefix_quagga(router, intf, prefix):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    prefix = str(prefix)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Remove old IPv6 prefix
        tn.write(b'no ipv6 nd prefix %s\r\n' % prefix)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection ' \
               'to %s on port %s' % (str(router), str(port)))


def add_ipv6_nd_prefix_quagga(router, intf, prefix):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    prefix = str(prefix)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Remove old IPv6 prefix
        tn.write(b'ipv6 nd prefix %s\r\n' % prefix.encode())
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection ' \
               'to %s on port %s' % (str(router), str(port)))


def add_ipv6_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IPv6 address
        tn.write(b'ipv6 address %s\r\n' % ip.encode())
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection ' \
               'to %s on port %s' % (str(router), str(port)))


def del_ipv6_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IPv6 address
        tn.write(b'no ipv6 address %s\r\n' % ip)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection ' \
               'to %s on port %s' % (str(router), str(port)))


def flush_ipv6_addresses_ssh(router, intf):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Flush addresses
    cmd = 'ip -6 addr flush dev %s scope global' % intf
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def add_ipv6_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip -6 addr add %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def del_ipv6_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip -6 addr del %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


# IPv4 utility functions

def add_ipv4_default_via(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the default via
    cmd = 'ip route add default via %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def del_ipv4_default_via(router):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the default via
    cmd = 'ip route del default'
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def add_ipv4_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IP address
        tn.write(b'ip address %s\r\n' % ip)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection ' \
                    'to %s on port %s' % (str(router), str(port)))


def del_ipv4_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IP address
        tn.write(b'no ip address %s\r\n' % ip)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection ' \
                    'to %s on port %s' % (str(router), str(port)))


def flush_ipv4_addresses_ssh(router, intf):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Flush addresses
    cmd = 'ip addr flush dev %s' % intf
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def add_ipv4_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip addr add %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def del_ipv4_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip addr del %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


# Read topology JSON and return the topology graph
def json_file_to_graph(topo_file):
    # Read JSON file
    with open(topo_file) as f:
        topo_json = json.load(f)
    # Return graph from JSON file
    return json_graph.node_link_graph(topo_json)


# Table ID Allocator
class TableIDAllocator:
    def __init__(self):
        # Mapping VPN name to table ID
        self.vpn_to_tableid = dict()
        # Mapping table ID to tenant ID
        self.tableid_to_tenantid = dict()
        # Set of reusable table IDs
        self.reusable_tableids = set()
        # Last used table ID
        self.last_allocated_tableid = -1

    # Allocate and return a new table ID for a VPN
    def get_new_tableid(self, vpn_name, tenantid):
        if self.vpn_to_tableid.get(vpn_name):
            # The VPN already has an associated table ID
            return -1
        else:
            # Check if a reusable table ID is available
            if self.reusable_tableids:
                tableid = self.reusable_tableids.pop()
            else:
                # If not, get a new table ID
                self.last_allocated_tableid += 1
                while self.last_allocated_tableid in RESERVED_TABLEIDS:
                    # Skip reserved table IDs
                    self.last_allocated_tableid += 1
                tableid = self.last_allocated_tableid
            # Assign the table ID to the VPN name
            self.vpn_to_tableid[vpn_name] = tableid
            # Associate the table ID to the tenant ID
            self.tableid_to_tenantid[tableid] = tenantid
            # And return
            return tableid

    # Return the table ID assigned to the VPN
    # If the VPN has no assigned table IDs, return -1
    def get_tableid(self, vpn_name):
        return self.vpn_to_tableid.get(vpn_name, -1)

    # Release a table ID and mark it as reusable
    def release_tableid(self, vpn_name):
        # Check if the VPN has an associated table ID
        if self.vpn_to_tableid.get(vpn_name):
            # The VPN has an associated table ID
            tableid = self.vpn_to_tableid[vpn_name]
            # Unassign the table ID
            del self.vpn_to_tableid[vpn_name]
            # Delete the association table ID - tenant ID
            del self.tableid_to_tenantid[tableid]
            # Mark the table ID as reusable
            self.reusable_tableids.add(tableid)
            # Return the table ID
            return tableid
        else:
            # The VPN has not an associated table ID
            return -1


class ControllerState:
    """This class maintains the state of the SRv6 controller and provides some
       methods to handle it
    """

    def __init__(self, topology, devices, vpn_dict, vpn_file):
        # Topology graph
        self.topology = topology
        # Devices
        self.devices = devices
        # VPN file
        self.vpn_file = vpn_file
        # VPNs dict
        self.vpns = vpn_dict
        # Keep track of how many VPNs are installed in each router
        self.num_vpn_installed_on_router = dict()
        # Initiated tunnels
        self.initiated_tunnels = set()
        # Number of tunneled interfaces
        self.num_tunneled_interfaces = dict()
        # Table ID allocator
        self.tableid_allocator = TableIDAllocator()
        # If VPN dumping is enabled, import the VPNs from the dump
        '''
        if vpn_file is not None:
            try:
                self.import_vpns_from_dump()
            except:
                print('Corrupted VPN file')
        '''

    # Return True if the VPN exists, False otherwise
    def vpn_exists(self, vpn_name):
        if self.vpns.get(vpn_name) is not None:
            # The VPN exists
            return True
        else:
            # The VPN does not exist
            return False
    '''
    # Return True if the router exists, False otherwise
    def router_exists(self, routerid):
        if self.topology.has_node(routerid):
            # Found router ID
            return True
        else:
            # The router ID has not been found
            return False
    '''

    # Return True if the router exists, False otherwise
    def router_exists(self, routerid):
        #routerid = int(IPv4Address(routerid))
        if routerid in self.devices:
            # Found router ID
            return True
        else:
            # The router ID has not been found
            return False
    
    '''
    # Return True if the specified interface exists
    def interface_exists(self, interface_name, routerid):
        router = self.topology.node[routerid]
        if router is None or router['interfaces'] is None:
            return False
        interface_names = []
        for interface in router['interfaces'].values():
            interface_names.append(interface['ifname'])
        if interface_name in interface_names:
            # The interface exists
            return True
        else:
            # The interface does not exist
            return False
    '''

    # Return True if the specified interface exists
    def interface_exists(self, interface_name, routerid):
        #routerid = int(IPv4Address(routerid))
        if routerid not in self.devices or self.devices[routerid].get('interfaces') is None:
            return False
        if interface_name in self.devices[routerid]['interfaces']:
            # The interface exists
            return True
        else:
            # The interface does not exist
            return False

    # Return True if the VPN is installed on the specified router,
    # False otherwise
    def is_vpn_installed_on_router(self, vpn_name, routerid):
        if self.vpn_exists(vpn_name):
            if routerid in self.vpns[vpn_name].interfaces:
                # The VPN is configured in the router
                return True
        # The VPN is not configured in the router
        return False

    # Return the number of the VPNs installed in the router
    def get_num_vpn_installed_on_router(self, routerid):
        return self.num_vpn_installed_on_router.get(routerid, 0)

    # Return True if the interface is assigned to the VPN, False otherwise
    def interface_in_vpn(self, routerid, interface_name, vpn_name):
        if self.vpns.get(vpn_name) is not None \
                and self.vpns[vpn_name].interfaces.get(routerid) is not None \
                and self.vpns[vpn_name].interfaces[routerid].get(interface_name):
            # The interface is assigned to the VPN
            return True
        # The interface is not assigned to the VPN
        return False

    # Return True if the interface is assigned to any VPN, False otherwise
    def interface_in_any_vpn(self, routerid, ifname):
        for vpn_name in self.vpns:
            interfaces = self.vpns[vpn_name].interfaces.get(routerid)
            if interfaces is not None and interfaces.get(ifname) is not None:
                # The interface is assigned to the VPN
                return True
        # The interface is not assigned to the VPN
        return False

    # Get router's loopback IP address
    def get_loopbackip(self, routerid):
        #routerid = int(IPv4Address(routerid))
        return self.devices[routerid]['interfaces']['lo']['ipv6_addrs'][0]['addr']

    '''
    # Get router's loopback IP address
    def get_loopbackip(self, routerid):
        return self.topology.node[routerid]['loopbackip']

    # Get router's management IP address
    def get_managementip(self, routerid):
        return self.topology.node[routerid]['managementip']
    '''

    # Get router's management IP address
    def get_router_mgmtip(self, routerid):
        #routerid = int(IPv4Address(routerid))
        return self.devices[routerid]['mgmtip']

    '''
    # Get router address
    def get_router_address(self, routerid):
        if self.use_mgmt_ip:
            return self.get_managementip(routerid)
        else:
            return self.get_loopbackip(routerid)
    '''

    '''
    # Get random router interface
    def get_random_interface(self, routerid):
        router_info = self.topology.node[routerid]
        return random.choice(list(router_info['interfaces'].values()))['ifname']

    # Get first router interface
    def get_first_interface(self, routerid):
        interfaces = list()
        router_info = self.topology.node[routerid]
        for interface in router_info['interfaces'].values():
            interfaces.append(interface['ifname'])
        interfaces.sort()
        return interfaces[0]
    '''

    def get_loopback_ip(self, routerid):
        #routerid = int(IPv4Address(routerid))
        return self.devices[routerid]['interfaces']['lo']['addr']


    # Get random router interface
    def get_non_loopback_interface(self, routerid):
        #routerid = int(IPv4Address(routerid))
        interfaces = self.devices[routerid]['interfaces']
        for interface in iter(interfaces):
            # Skip loopback interfaces
            if interface != 'lo':
                return interface
        # No non-loopback interfaces
        return None

    # Add a VPN to the controller state
    def add_vpn(self, vpn_name, vpn_type, tenantid, tunnel_mode): #, tableid):
        # If the VPN already exists, return False
        if vpn_name in self.vpns:
            return False
        # Add the VPN to the VPNs dict
        self.vpns[vpn_name] = VPN(vpn_name, vpn_type, set(), tenantid, tunnel_mode) #, tableid)
        # Success, return True
        return True

    # Add a router to a VPN and increase the number of VPNs installed on a
    # router
    def add_router_to_vpn(self, routerid, vpn_name):
        # If the VPN does not exist, return False
        if vpn_name not in self.vpns:
            return False
        # Increase the number of VPNs installed on the router
        num_of_vpns = self.get_num_vpn_installed_on_router(routerid)
        self.num_vpn_installed_on_router[routerid] = num_of_vpns + 1
        # Add the router to the VPN
        self.vpns[vpn_name].interfaces[routerid] = dict()
        return True

    # Remove a VPN from a router and
    # decrease the number of VPNs installed on a router
    def remove_vpn_from_router(self, vpn_name, routerid):
        # Remove the VPN from the VPNs dict, if it has no more interfaces
        if len(self.vpns[vpn_name].interfaces[routerid]) == 0:
            del self.vpns[vpn_name].interfaces[routerid]
            # Update the number of VPNs installed on the router
            num_of_vpns = self.get_num_vpn_installed_on_router(routerid)
            self.num_vpn_installed_on_router[routerid] = num_of_vpns - 1
            return True
        return False

    # Remove a VPN
    def remove_vpn(self, vpn_name):
        # Remove the VPN from the VPNs dict
        if vpn_name not in self.vpns:
            return False
        del self.vpns[vpn_name]
        return True

    # Return VPN type
    def get_vpn_type(self, vpn_name):
        if vpn_name not in self.vpns:
            return None
        return self.vpns[vpn_name].vpn_type

    # Return VPN type
    #def get_vpn_tableid(self, vpn_name):
    #    print(self.vpns)
    #    if vpn_name not in self.vpns:
    #        return None
    #    return self.vpns[vpn_name].tableid

    # Return SID
    #def get_sid(self, routerid, tableid):
    #    return self.sid_allocator.getSID(routerid, tableid)

    # Return SID
    #def get_sid_family(self, routerid):
    #    return self.sid_allocator.getSIDFamily(routerid)

    # Return VPN interfaces
    def get_vpn_interfaces(self, vpn_name, routerid=None):
        if self.vpns.get(vpn_name) is None:
            return None
        interfaces = list()
        for _interfaces in self.vpns[vpn_name].interfaces.values():
            for _interface in _interfaces.values():
                if routerid is not None and _interface.routerid != routerid:
                    continue
                interfaces.append(_interface)
        return interfaces

    # Return VPN interfaces
    def get_vpn_interface_names(self, vpn_name, routerid=None):
        #if self.vpns.get(vpn_name) is None:
        #    return None
        interfaces = set()
        if self.vpns.get(vpn_name) is None:
            return interfaces
        for _interfaces in self.vpns[vpn_name].interfaces.values():
            for _interface in _interfaces.values():
                if routerid is not None and _interface.routerid != routerid:
                    continue
                interfaces.add(_interface.interface_name)
        return interfaces

    # Add an interface to a VPN
    def add_interface_to_vpn(self, vpn_name, routerid, interface_name,
                             interface_ip, vpn_prefix):
        self.vpns[vpn_name].interfaces[routerid][interface_name] = Interface(
            routerid, interface_name, interface_ip, vpn_prefix
        )

    # Return VPN prefix assigned to an interface
    def get_vpn_prefix(self, vpn_name, routerid, interface_name):
        return self.vpns[vpn_name].interfaces[routerid][interface_name].vpn_prefix

    # Return VPN prefix assigned to an interface
    def get_vpn_interface_ip(self, vpn_name, routerid, interface_name):
        return self.vpns[vpn_name].interfaces[routerid][interface_name].interface_ip

    # Remove an interface from a VPN
    def remove_interface_from_vpn(self, routerid, interface_name, vpn_name):
        return self.vpns[vpn_name].removeInterface(routerid, interface_name)

    # Return the number of the interface in the VPN
    def get_number_of_interfaces(self, vpn_name, routerid):
        return self.vpns[vpn_name].numberOfInterfaces(routerid)

    '''
    # Return the IP addresses associated to an interface
    def get_interface_ips(self, routerid, interface_name):
        for interface in self.topology.node[routerid]['interfaces'].values():
            if interface['ifname'] == interface_name:
                return interface['ipaddr']
        return None
    '''

    # Return the IP addresses associated to an interface
    def get_interface_ipv4(self, routerid, interface_name):
        #routerid = int(IPv4Address(routerid))
        ips = list()
        for addr in self.devices[routerid]['interfaces'][interface_name]['ipv4_addrs']:
            ips.append('%s/%s' % (addr['addr'], addr['netmask']))
        return ips

    # Return the IP addresses associated to an interface
    def get_interface_ipv6(self, routerid, interface_name):
        #routerid = int(IPv4Address(routerid))
        ips = list()
        for addr in self.devices[routerid]['interfaces'][interface_name]['ipv6_addrs']:
            ips.append('%s/%s' % (addr['addr'], addr['netmask']))
        return ips

    # Return the IP addresses associated to an interface
    def get_interface_ips(self, routerid, interface_name):
        return self.get_interface_ipv4(routerid, interface_name) + self.get_interface_ipv6(routerid, interface_name)

    # Return the VPNs
    def get_vpns(self):
        return self.vpns.values()

    def get_routers_in_vpn(self, vpn_name):
        routers = set()
        for routerid in self.vpns[vpn_name].interfaces:
            routers.add(routerid)
        return routers

    # Create a dump of the VPNs
    def save_vpns_dump(self):
        # Build VPN dump dict
        """The dict has the following structure
           #
           vpn_dump_dict = dict({
                'vpns': dict(),
                'reusable_tableids': list(),
                'tableid_to_tenantid': dict(),
                'last_allocated_tableid': -1
        })
        """
        vpn_dump_dict = dict()
        # Parse VPN dump and fill data structures
        #
        # Process VPNs information
        vpn_dump_dict['vpns'] = dict()
        for vpn in self.vpns.values():
            # Build the list of the interfaces
            interfaces = list()
            # Iterate on all interfaces
            for _interfaces in vpn.interfaces.values():
                for _interface in _interfaces.values():
                    # Add a new interface to the list
                    interfaces.append({
                        'routerid': _interface.routerid,
                        'interface_name': _interface.interface_name,
                        'interface_ip': _interface.interface_ip,
                        'vpn_prefix': _interface.vpn_prefix
                    })
            # Add VPN to the mapping
            vpn_dump_dict['vpns'][vpn.vpn_name] = {
                'vpn_name':vpn.vpn_name,
                'tableid': vpn.tableid,
                'tenantid': vpn.tenantid,
                'interfaces': interfaces
            }
        # Process reusable table IDs set
        #reusable_tableids = list(self.tableid_allocator.reusable_tableids)
        #vpn_dump_dict['reusable_tableids'] = reusable_tableids
        # Process table IDs
        #tableid_to_tenantid = self.tableid_allocator.tableid_to_tenantid
        #vpn_dump_dict['tableid_to_tenantid'] = tableid_to_tenantid
        # Process last table ID
        #last_allocated_tableid = self.tableid_allocator.last_allocated_tableid
        #vpn_dump_dict['last_allocated_tableid'] = last_allocated_tableid
        # Write the dump to file
        with open(self.vpn_file, 'w') as outfile:
            json.dump(vpn_dump_dict, outfile, sort_keys=True, indent=2)

    # Import VPNs from dump
    def import_vpns_from_dump(self):
        try:
            # Open VPN dump file
            with open(self.vpn_file) as json_file:
                vpn_dump_dict = json.load(json_file)
            # Parse VPN dump and fill data structures
            #
            # Process VPNs information
            for vpn in vpn_dump_dict['vpns'].values():
                # table ID
                #vpn_to_tableid[vpn] = int(vpn['tableid'])
                # Interfaces
                interfaces = set()
                for interface in vpn['interfaces']:
                    interface = Interface(
                            interface['routerid'],
                            interface['interface_name'],
                            interface['interface_ip'],
                            interface['vpn_prefix']
                    )
                    interfaces.add(interface)
                # Tenant ID
                tenantid = vpn['tenantid']
                # VPN type
                vpn_type = vpn['vpn_type']
                # VPN name
                vpn_name = vpn['vpn_name']
                # Table ID
                tableid = vpn['tableid']
                # Build VPN and add the VPN to the VPNs dict
                self.vpns[vpn.vpn_name] = VPN(vpn_name, vpn_type, interfaces, tenantid) #, tableid)
            # Process reusable table IDs
            #for _id in vpn_dump_dict['reusable_tableids']:
            #    self.tableid_allocator.reusable_tableids.add(int(_id))
            # Process table IDs
            #tableid_to_tenantid = vpn_dump_dict['tableid_to_tenantid']
            #for tableid, tenantid in tableid_to_tenantid.items():
            #    tableid = int(tableid)
            #    tenantid = int(tenantid)
            #    self.tableid_allocator.tableid_to_tenantid[tableid] = tenantid
            # Process last table ID
            #last_tableid = int(vpn_dump_dict['last_allocated_tableid'])
            #self.tableid_allocator.last_allocated_tableid = last_tableid
        except IOError:
            print('VPN file not found')

    # Get a new table ID
    #def get_new_tableid(self, vpn_name, tenantid):
    #    return self.tableid_allocator.get_new_tableid(vpn_name, tenantid)

    # Release a table ID
    #def release_tableid(self, vpn_name):
    #    return self.tableid_allocator.release_tableid(vpn_name)

    '''
    # Update the topology from a JSON file
    def load_topology_from_json_dump(self, block=True):
        ready = False
        while not ready:
            try:
                logger.debug('Try to retrieve the updated topology')
                self.topology = json_file_to_graph(self.topo_file)
                if self.topology is not None:
                    ready = True
            except Exception:
                # Error
                logger.warning('Error while retrieving the topology from the file %s' % self.topo_file)
                print('*** Waiting for the topology getting ready')
                time.sleep(WAIT_TOPOLOGY_INTERVAL)
        # Success
        logger.info('The topology has been updated')
        return True
    '''

'''
# Update the topology from a JSON file
def load_topology_from_json_dump(topo_file, block=True):
    ready = False
    while not ready:
        try:
            logger.debug('Try to retrieve the updated topology')
            topology = json_file_to_graph(topo_file)
            if self.topology is not None:
                ready = True
        except Exception:
            # Error
            logger.warning('Error while retrieving the topology from the file %s' % topo_file)
            print('*** Waiting for the topology getting ready')
            time.sleep(WAIT_TOPOLOGY_INTERVAL)
    # Success
    logger.info('The topology has been updated')
    return topology
'''
