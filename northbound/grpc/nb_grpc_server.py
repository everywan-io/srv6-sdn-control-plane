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
# Server of a Northbound interface based on gRPC protocol
# 
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#


from concurrent import futures
from optparse import OptionParser
from google.protobuf import json_format

from socket import *

import logging
import time
import json
import grpc

import os
from itertools import islice

# Folders
CONTROL_PLANE_FOLDER = "/home/user/repos/srv6-sdn-control-plane/"
VPN_FOLDER = CONTROL_PLANE_FOLDER + "vpn/"
SB_GRPC_FOLDER = CONTROL_PLANE_FOLDER + "southbound/grpc/"
PROTO_FOLDER = "/home/user/repos/srv6-sdn-proto/"

# Add path of gRPC APIs
import sys
# Add path of proto files
sys.path.append(PROTO_FOLDER)
# Add path of VPN APIs
sys.path.append(VPN_FOLDER)
# Add path of VPN APIs
sys.path.append(SB_GRPC_FOLDER)

from vpn_utils import *

import srv6_vpn_pb2_grpc
import srv6_vpn_pb2

from sb_grpc_client import *

# ipaddress
from ipaddress import IPv6Address
from ipaddress import IPv6Network
from ipaddress import IPv6Interface

# NetworkX
import networkx as nx
from networkx.readwrite import json_graph


# Global variables definition

# Server reference
grpc_server = None
# Logger reference
logger = logging.getLogger(__name__)
# Server ip and port
GRPC_IP = "::"
GRPC_PORT = 12345
# Debug option
SERVER_DEBUG = False
# Secure option
SECURE = False
# Server certificate
CERTIFICATE = "cert_server.pem"
# Server key
KEY = "key_server.pem"

# Topology file
TOPOLOGY_FILE = "../../topology/topo_extraction/topology.json"
# Loopback prefix used by routers
LOOPBACK_PREFIX = 'fdff::/16'
# VPN file
VPN_FILE = "%svpn.json" % (VPN_FOLDER)
# Linux kernel supports up to 2^32 different tables
MAX_TABLE_ID = 2**32  # 2^32

# Check if VPN_FOLDER exists, if not create it
if not os.path.exists(VPN_FOLDER):
    os.makedirs(VPN_FOLDER)


class VPNIntentGenerator:
    def __init__(self):
       # Mapping VPN to intent
        self.vpn_to_intent = dict()

    def get_vpn_list(self):
        # Return the list of VPN names
        return self.vpn_to_intent.keys()

    def add_new_intent(self, intent):
        vpn_name = intent.name
        if self.vpn_to_intent.get(vpn_name):
            # The VPN already has an intent
            return -1
        else:
            # Add the intent to the mapping
            self.vpn_to_intent[vpn_name] = intent
            # And return
            return 0

    def get_intent(self, vpn_name):
        # Return the intent associated to the VPN name
        # if not exists return -1
        return self.vpn_to_intent.get(vpn_name, -1)

    def remove_intent(self, vpn_name):
        if self.vpn_to_intent.get(vpn_name):
            # The VPN has an associated intent
            # delete correspondence
            del self.vpn_to_intent[vpn_name]
            # ...and return
            return 0
        else:
            # The VPN has not an associated intent
            return -1


class TableIDAllocator:
    def __init__(self):
        self.vpn_to_tableid = dict()
        self.tableid_to_tenantid = dict()
        self.reusable_tableids = set()
        self.last_allocated_table_id = -1

    def get_new_table_id(self, vpn_name, tenant_id):
        if self.vpn_to_tableid.get(vpn_name):
            # The VPN already has an associated table ID
            return -1
        else:
            # Check if a reusable table id is available
            if len(self.reusable_tableids) > 0:
                table_id = self.reusable_tableids.pop()
            else:
                # If not, get a new table ID
                self.last_allocated_table_id += 1 
                while self.last_allocated_table_id in [0, 1, 253, 254, 255]:
                    # Skip reserved table IDs
                    self.last_allocated_table_id += 1
                table_id = self.last_allocated_table_id
            # Associate the table ID to the VPN name
            self.vpn_to_tableid[vpn_name] = table_id
            # Associate the table ID to the tenant ID
            self.tableid_to_tenantid[table_id] = tenant_id
            # And return
            return table_id

    def get_table_id(self, vpn_name):
      # Return the table ID associated to the VPN name
      # if not exists return -1
      return self.vpn_to_tableid.get(vpn_name, -1)

    def release_table_id(self, vpn_name):
      if self.vpn_to_tableid.get(vpn_name):
        # The VPN has an associated table ID
        table_id = self.vpn_to_tableid[vpn_name]
        # delete correspondence
        del self.vpn_to_tableid[vpn_name]
        # Delete the association table ID - tenant ID
        del self.tableid_to_tenantid[table_id]
        # Mark the table ID as reusable
        self.reusable_tableids.add(table_id)
        # ...and return table ID
        return table_id
      else:
        # The VPN has not an associated table ID
        return -1


class SIDGenerator:

    def get_sid(self, loopback_prefix, table_id):
        # A SID has three components
        # the loopback prefix of the router
        loopback_net = IPv6Network(unicode(loopback_prefix))
        # a prefix which identifies the SIDs class
        sid_net = next(islice(loopback_net.subnets(prefixlen_diff=1), 1, 2))
        # the identifier of the VPN (corresponding to the table ID)
        sid = next(islice(sid_net.hosts(), table_id, table_id+1)).__str__()
        # Return the SID
        return sid


class VPNHandler(srv6_vpn_pb2_grpc.SRv6VPNHandlerServicer):
    """gRPC request handler"""
    
    def __init__(self):
        self.srv6_vpn_handler = SRv6VPNHandler()
        self.intent_generator = VPNIntentGenerator()
        self.table_id_allocator = TableIDAllocator()
        self.sid_generator = SIDGenerator()
        self.flush_vpns()
        self.load_dump()
        self._get_vpns()

    # Get all VPNs from the routers
    def _get_vpns(self):
        # Get the network topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the network prefixes associated to the interfaces
        routerid_to_prefixes = nx.get_node_attributes(topology,'prefixes')
        # Get the ip addresses associated to the interfaces
        routerid_to_interfaces = nx.get_node_attributes(topology,'interfaces')
        # Get the loopback ip address of the routers
        routerid_to_loopbackip = nx.get_node_attributes(topology,'loopbackip')
        # Get the loopback prefixes associated to the routers
        routerid_to_loopbacknet = dict()
        for router in routerid_to_prefixes:
            # Scan all the prefixes and search for the loopback prefix
            for intf in routerid_to_prefixes[router]:
                net = routerid_to_prefixes[router][intf]
                if IPv6Network(unicode(net)).subnet_of(IPv6Network(unicode(LOOPBACK_PREFIX))):
                    # The prefix belongs to the loopback prefixes net
                    routerid_to_loopbacknet[router] = net
        # Get the management ip addresses of the routers
        routerid_to_mgmtip = nx.get_node_attributes(topology,'mgmtip')
        # Mapping interface name to prefix net
        lintf_to_prefix = {v : n1 for (n1, n2),v in nx.get_edge_attributes(topology, 'lhs_intf').iteritems()}
        rintf_to_prefix = {v : n2 for (n1, n2),v in nx.get_edge_attributes(topology, 'rhs_intf').iteritems()}
        # Mapping ip address to prefix net
        lip_to_prefix = {v : n1 for (n1, n2),v in nx.get_edge_attributes(topology, 'lhs_ip').iteritems()}
        rip_to_prefix = {v : n2 for (n1, n2),v in nx.get_edge_attributes(topology, 'rhs_ip').iteritems()}
        # Mapping prefix net to ip address
        prefix_to_lip = {v : k for k,v in lip_to_prefix.iteritems()}
        prefix_to_rip = {v : k for k,v in rip_to_prefix.iteritems()}
        # Mapping prefix net to interface name
        prefix_to_lintf = {v : k for k,v in lintf_to_prefix.iteritems()}
        prefix_to_rintf = {v : k for k,v in rintf_to_prefix.iteritems()}
        # Mapping interface name to ip address
        intf_to_ip = dict()
        for prefix in prefix_to_lip:
            # Get ip address associated to the prefix
            lip = prefix_to_lip[prefix]
            # Get interface name associated to the prefix
            lintf = prefix_to_lintf[prefix]
            # Add the correspondence to the mapping
            intf_to_ip[lintf] = lip
        for prefix in prefix_to_rip:
            # Get ip address associated to the prefix
            rip = prefix_to_rip[prefix]
            # Get interface name associated to the prefix
            rintf = prefix_to_rintf[prefix]
            # Add the correspondence to the mapping
            intf_to_ip[rintf] = rip
        # Re-create the VPNs starting from the controller state
        for vpn_name in self.intent_generator.get_vpn_list():
            # Get the VPN intent
            intent = self.intent_generator.get_intent(vpn_name)
            # Get the interfaces
            interfaces = intent.interfaces
            # Get the tenant ID
            tenant_id = intent.tenant_id
            # Retrieve routers to be added to the VPN
            routers = {intf[0] for intf in interfaces}
            # Get the table ID
            table_id = self.table_id_allocator.get_table_id(vpn_name)
            # Mapping interface name to the private address
            intf_to_private_addr = dict()
            for intf in intent.interfaces:
                if intf_to_private_addr.get(intf[0]) == None:
                    intf_to_private_addr[intf[0]] = dict()
                intf_to_private_addr[intf[0]][intf[1]] = intf[2]
            # Create the VPN
            for router in routers:
                # Get management ip address of the router
                router_mgmt = routerid_to_mgmtip[router]
                # Get loopback prefix of the router
                loopback_prefix = routerid_to_loopbacknet[router]
                # Get the SID
                sid = self.sid_generator.get_sid(loopback_prefix, table_id)
                # Send the creation command to the router
                if self.srv6_vpn_handler.create_vpn(router_mgmt, vpn_name, table_id, sid) == False:
                    return srv6_vpn_pb2.SRv6VPNReply(message="")
                # Add interfaces to the VPN
                for intf in interfaces:
                    if router == intf[0]:
                        # Interface is local to the router
                        # Get interface name
                        intf_name = intf[1]
                        # Get the ip address to add to the interface
                        new_ipaddr = IPv6Interface(unicode(intf[2])).__str__()
                        new_mask = IPv6Interface(unicode(intf[2])).network.prefixlen.__str__()
                        # Get the ip address to remove from the interface
                        old_ipaddr = IPv6Interface(unicode(routerid_to_interfaces[router][intf_name])).__str__()
                        # Get the old advertised prefix
                        old_prefix = routerid_to_prefixes[router][intf_name].__str__()
                        # Get the new prefix to advertise
                        new_prefix = IPv6Interface(unicode(intf[2])).network.__str__()
                        # Reconfigure addressing plan and prefix advertisements
                        reconfigure_addressing_plan(router_mgmt, 2601, intf_name, old_prefix, new_prefix, old_ipaddr, new_ipaddr)
                        # Add local interface to the VPN
                        if self.srv6_vpn_handler.add_local_interface_to_vpn(router_mgmt, vpn_name, intf_name) == False:
                            return srv6_vpn_pb2.SRv6VPNReply(message="")
                    else:
                        # Loopback ip of the remote router
                        loopback_net = routerid_to_loopbacknet[intf[0]]
                        # Get the private prefix of the interface
                        intf_prefix = intf_to_private_addr[intf[0]][intf[1]]
                        # Interface is remote to the router (it is on another router)
                        remote_sid = self.sid_generator.get_sid(loopback_net, table_id)
                        # Add the remote interface to the VPN
                        if self.srv6_vpn_handler.add_remote_interface_to_vpn(router_mgmt, intf_prefix, table_id, remote_sid) == False:
                            return srv6_vpn_pb2.SRv6VPNReply(message="")

    # Create a VPN from an intent received through the northbound interface
    def CreateVPNFromIntent(self, request, context):
        logger.debug("config received:\n%s", request)
        # Get topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the network prefixes associated to the interfaces
        routerid_to_prefixes = nx.get_node_attributes(topology,'prefixes')
        # Get the ip addresses associated to the interfaces
        routerid_to_interfaces = nx.get_node_attributes(topology,'interfaces')
        # Get the loopback ip address of the routers
        routerid_to_loopbackip = nx.get_node_attributes(topology,'loopbackip')
        # Get the loopback prefixes associated to the routers
        routerid_to_loopbacknet = dict()
        for router in routerid_to_prefixes:
            # Scan all the prefixes and search for the loopback prefix
            for intf in routerid_to_prefixes[router]:
                net = routerid_to_prefixes[router][intf]
                if IPv6Network(unicode(net)).subnet_of(IPv6Network(unicode(LOOPBACK_PREFIX))):
                    # The prefix belongs to the loopback prefixes net
                   routerid_to_loopbacknet[router] = net
        # Get the management ip addresses of the routers
        routerid_to_mgmtip = nx.get_node_attributes(topology,'mgmtip')
        # Get the tenant ID
        tenant_id = request.tenant_id
        # Get the name of the VPN
        vpn_name = request.name
        # Generate the full name of the VPN
        vpn_name= "%s-%s" % (tenant_id, vpn_name)
        # Get the interfaces of the VPN
        interfaces = list()
        for intf in request.interfaces:
            # An interface is a tuple (router_id, interface_name, private_ip_address)
            router_id = intf.router_id
            name = intf.name
            address = intf.ip_address
            interfaces.append((router_id, name, address))
        # Retrieve routers to be added to the VPN
        routers = {intf[0] for intf in interfaces}
        # Check if the VPN already exist
        if (self.table_id_allocator.get_table_id(vpn_name) != -1
                or self.intent_generator.get_intent(vpn_name) != -1):
            print "VPN %s already exists" % vpn_name
            return srv6_vpn_pb2.SRv6VPNReply(message="")
        # Get a new table ID
        table_id = self.table_id_allocator.get_new_table_id(vpn_name, tenant_id)
        # Save the intent
        intent = VPNIntent(vpn_name, interfaces, tenant_id)
        self.intent_generator.add_new_intent(intent)
        # Mapping interface name to the private address
        intf_to_private_addr = dict()
        for intf in intent.interfaces:
            if intf_to_private_addr.get(intf[0]) == None:
                intf_to_private_addr[intf[0]] = dict()
            intf_to_private_addr[intf[0]][intf[1]] = intf[2]
        # Create the VPN
        for router in routers:
            # Get management ip address of the router
            router_mgmt = routerid_to_mgmtip[router]
            # Get loopback ip prefix of the router
            loopback_prefix = routerid_to_loopbacknet[router]
            # Get SID
            sid = self.sid_generator.get_sid(loopback_prefix, table_id)
            # Send the creation command to the router
            if self.srv6_vpn_handler.create_vpn(router_mgmt, vpn_name, table_id, sid) == False:
                return srv6_vpn_pb2.SRv6VPNReply(message="")
            # Add the interfaces to the VPN
            for intf in interfaces:
                if router == intf[0]:
                  # Interface is local to the router
                  # Get interface name
                  intf_name = intf[1]
                  # Get the ip address to add to the interface
                  new_ipaddr = IPv6Interface(unicode(intf[2])).__str__()
                  new_mask = IPv6Interface(unicode(intf[2])).network.prefixlen.__str__()
                  # Get the ip address to remove from the interface
                  old_ipaddr = IPv6Interface(unicode(routerid_to_interfaces[router][intf_name])).__str__()
                  # Get the old advertised prefix
                  old_prefix = routerid_to_prefixes[router][intf_name].__str__()
                  # Get the new prefix to advertise
                  new_prefix = IPv6Interface(unicode(intf[2])).network.__str__()
                  # Reconfigure addressing plan and prefix advertisements
                  reconfigure_addressing_plan(router_mgmt, 2601, intf_name, old_prefix, new_prefix, old_ipaddr, new_ipaddr)
                  # Add local interface to the VPN
                  if self.srv6_vpn_handler.add_local_interface_to_vpn(router_mgmt, vpn_name, intf_name) == False:
                      return srv6_vpn_pb2.SRv6VPNReply(message="")
                else:
                    # Loopback ip of the remote router
                    remote_loopback = routerid_to_loopbacknet[intf[0]]
                    # Get the prefix of the interface
                    intf_prefix = intf_to_private_addr[intf[0]][intf[1]]
                    # Interface is remote to the router (it is on another router)
                    remote_sid = self.sid_generator.get_sid(remote_loopback, table_id)
                    # Add the remote interface to the VPN
                    if self.srv6_vpn_handler.add_remote_interface_to_vpn(router_mgmt, intf_prefix, table_id, remote_sid) == False:
                        return srv6_vpn_pb2.SRv6VPNReply(message="")
        # Dump the information
        self.dump()
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(message="OK")


    def RemoveVPNByName(self, request, context):
        logger.debug("Remove VPN request received:\n%s", request)
        # Extract name and tenant ID from the request
        name = str(request.name)
        tenant_id = str(request.tenant_id)
        # Get the full name of the VPN
        vpn_name = "%s-%s" % (tenant_id, name)
        # Get topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the network prefixes associated to the interfaces
        routerid_to_prefixes = nx.get_node_attributes(topology,'prefixes')
        # Get the loopback ip address of the routers
        routerid_to_loopbackip = nx.get_node_attributes(topology,'loopbackip')
        # Get the loopback prefixes associated to the routers
        routerid_to_loopbacknet = dict()
        for router in routerid_to_prefixes:
            # Scan all the prefixes and search for the loopback prefix
            for intf in routerid_to_prefixes[router]:
                net = routerid_to_prefixes[router][intf]
                if IPv6Network(unicode(net)).subnet_of(IPv6Network(unicode(LOOPBACK_PREFIX))):
                    # The prefix belongs to the loopback prefixes net
                    routerid_to_loopbacknet[router] = net
        # Get the management ip addresses of the routers
        routerid_to_mgmtip = nx.get_node_attributes(topology,'mgmtip')
        # Get table ID and intent
        table_id = self.table_id_allocator.get_table_id(vpn_name)
        intent = self.intent_generator.get_intent(vpn_name)
        # Check if the VPN already exist
        if (table_id == -1 or intent == -1):
            print "VPN %s does not exist" % vpn_name
            return srv6_vpn_pb2.SRv6VPNReply(message="")
        # Routers in the VPN
        routers = {intf[0] for intf in intent.interfaces}
        # Remove the VPN in all routers belonging to it
        for router in routers:
            # Get management ip address of the router
            router_mgmt = routerid_to_mgmtip[router]
            # Get loopback ip prefix of the router
            loopback_prefix = routerid_to_loopbacknet[router]
            # Get the SID
            sid = self.sid_generator.get_sid(loopback_prefix, table_id)
            # Remove the VPN
            if self.srv6_vpn_handler.remove_vpn(router_mgmt, vpn_name, table_id, sid) == False:
                return srv6_vpn_pb2.SRv6VPNReply(message="")
        # Update VPNs information
        if self.table_id_allocator.release_table_id(vpn_name) == -1:
            print "VPN %s has no table ID associated" % vpn_name
            return srv6_vpn_pb2.SRv6VPNReply(message="")
        if self.intent_generator.remove_intent(vpn_name) == -1:
            print "VPN %s has no intent associated" % vpn_name
            return srv6_vpn_pb2.SRv6VPNReply(message="")
        # Dump the information
        self.dump()
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(message="OK")


    # Get VPNs from the controller inventory
    def GetVPNs(self, request, context):
        # Get VPNs list
        vpns = self.intent_generator.get_vpn_list()
        vpn_list = srv6_vpn_pb2.SRv6VPNList()
        for vpn_name in vpns:
            vpn = vpn_list.vpns.add()
            vpn.name = vpn_name
            vpn.table_id = str(self.table_id_allocator.get_table_id(vpn_name))
            for intf in self.intent_generator.get_intent(vpn_name).interfaces: 
                interface = vpn.interfaces.append(str(intf))
        # Return the list
        return vpn_list


    # Read the topology graph and convert to a NetworkX object
    def read_json_file(self, filename):
        with open(filename) as f:
            js_graph = json.load(f)
        return json_graph.node_link_graph(js_graph)


    # Delete all VPNs
    def flush_vpns(self):
        # Get the topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the management ip addresses of the routers
        routerid_to_mgmtip = nx.get_node_attributes(topology,'mgmtip')
        # Remove informations in each router
        for router in routerid_to_mgmtip:
            router_mgmt = routerid_to_mgmtip[router]
            if self.srv6_vpn_handler.flush_vpns(router_mgmt) == False:
               return

    # Create a dump of the VPNs
    def dump(self):
        # Get VPNs
        vpns = self.intent_generator.get_vpn_list()
        # Build results
        ret = dict()
        ret['vpns'] = dict()
        for vpn in vpns:
            ret['vpns'][vpn] = dict()
            ret['vpns'][vpn]['table_id'] = self.table_id_allocator.get_table_id(vpn)
            intent = self.intent_generator.get_intent(vpn)
            ret['vpns'][vpn]['intent'] = dict()
            ret['vpns'][vpn]['intent']['name'] = intent.name
            ret['vpns'][vpn]['intent']['interfaces'] = list(intent.interfaces)
            ret['vpns'][vpn]['intent']['tenant_id'] = intent.tenant_id
        ret['reusable_tableids'] = list(self.table_id_allocator.reusable_tableids)
        ret['tableid_to_tenantid'] = self.table_id_allocator.tableid_to_tenantid
        ret['last_allocated_table_id'] = self.table_id_allocator.last_allocated_table_id
        # Json dump of the VPNs
        with open(VPN_FILE, 'w') as outfile:
            json.dump(ret, outfile, sort_keys = True, indent = 2)


    # Load a dump
    def load_dump(self):
        try:
            # Open VPN dump file
            with open(VPN_FILE) as file:
               vpns = json.load(file)
            # Parse VPN and fill data structures
            for vpn in vpns['vpns']:
                self.table_id_allocator.vpn_to_tableid[vpn] = int(vpns['vpns'][vpn]['table_id'])
                name = vpns['vpns'][vpn]['intent']['name']
                _interfaces = vpns['vpns'][vpn]['intent']['interfaces']
                interfaces = set()
                for intf in _interfaces:
                  interfaces.add(tuple(intf))
                tenant_id = vpns['vpns'][vpn]['intent']['tenant_id']
                intent = VPNIntent(name, interfaces, tenant_id) 
                self.intent_generator.vpn_to_intent[vpn] = intent
            self.table_id_allocator.reusable_tableids = set()
            for _id in vpns['reusable_tableids']:
              self.table_id_allocator.reusable_tableids.add(int(_id))
            self.table_id_allocator.tableid_to_tenantid = dict()
            for table_id in vpns['tableid_to_tenantid']:
              self.table_id_allocator.tableid_to_tenantid[int(table_id)] = int(vpns['tableid_to_tenantid'][table_id])
            self.table_id_allocator.last_allocated_table_id = int(vpns['last_allocated_table_id'])
        except IOError:
          print "No VPN file"


# Start gRPC server
def start_server():
    # Configure gRPC server listener and ip route
    global grpc_server
    # Setup gRPC server
    if grpc_server is not None:
       logger.error("gRPC Server is already up and running")
    else:
        # Create the server and add the handler
        grpc_server = grpc.server(futures.ThreadPoolExecutor())
        srv6_vpn_pb2_grpc.add_SRv6VPNHandlerServicer_to_server(VPNHandler(),
                                                                grpc_server)
        # If secure we need to create a secure endpoint
        if SECURE:
            # Read key and certificate
            with open(KEY) as f:
               key = f.read()
            with open(CERTIFICATE) as f:
               certificate = f.read()
            # Create server ssl credentials
            grpc_server_credentials = grpc.ssl_server_credentials(((key, certificate,),))
            # Create a secure endpoint
            grpc_server.add_secure_port("[%s]:%s" %(GRPC_IP, GRPC_PORT), grpc_server_credentials)
        else:
            # Create an insecure endpoint
            grpc_server.add_insecure_port("[%s]:%s" %(GRPC_IP, GRPC_PORT))
    # Start the loop for gRPC
    logger.info("Listening gRPC")
    grpc_server.start()
    while True:
      time.sleep(5)


# Parse options
def parse_options():
    global SECURE
    parser = OptionParser()
    parser.add_option("-d", "--debug", action="store_true", help="Activate debug logs")
    parser.add_option("-s", "--secure", action="store_true", help="Activate secure mode")
    # Parse input parameters
    (options, args) = parser.parse_args()
    # Setup properly the logger
    if options.debug:
       logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    # Setup properly the secure mode
    if options.secure:
        SECURE = True
    else:
        SECURE = False
    SERVER_DEBUG = logger.getEffectiveLevel() == logging.DEBUG
    logger.info("SERVER_DEBUG:" + str(SERVER_DEBUG))


if __name__ == "__main__":
    parse_options()
    start_server()