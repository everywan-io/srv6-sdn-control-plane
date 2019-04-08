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
# Add path of gRPC APIs
sys.path.append(SB_GRPC_FOLDER)

from vpn_utils import *

import srv6_vpn_nb_pb2_grpc
import srv6_vpn_nb_pb2

import srv6_vpn_msg_pb2_grpc
import srv6_vpn_msg_pb2

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
# Validate interfaces
VALIDATE_INTERFACES = True

# Topology file
TOPOLOGY_FILE = CONTROL_PLANE_FOLDER + "topology/topo_extraction/topology.json"
# Interfaces file
INTERFACES_FILE = CONTROL_PLANE_FOLDER + "interface_discovery/interfaces.json"
# Loopback prefix used by routers
LOOPBACK_PREFIX = 'fdff::/16'
# VPN file
VPN_FILE = "%svpn.json" % (VPN_FOLDER)
# Linux kernel supports up to 2^32 different tables
MAX_tableid = 2**32  # 2^32

# Check if VPN_FOLDER exists, if not create it
if not os.path.exists(VPN_FOLDER):
    os.makedirs(VPN_FOLDER)


routerid_to_mgmtip = {"0.0.0.1": "2000::1", "0.0.0.2": "2000::2", "0.0.0.3": "2000::3"}

class VPNIntentGenerator:
    def __init__(self):
       # Mapping VPN to intent
        self.vpn_to_intent = dict()

    def get_vpns(self):
        # Return the list of VPN names
        return self.vpn_to_intent.keys()

    def add_intent(self, intent):
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
        self.last_allocated_tableid = -1

    def get_new_tableid(self, vpn_name, tenantid):
        if self.vpn_to_tableid.get(vpn_name):
            # The VPN already has an associated table ID
            return -1
        else:
            # Check if a reusable table id is available
            if len(self.reusable_tableids) > 0:
                tableid = self.reusable_tableids.pop()
            else:
                # If not, get a new table ID
                self.last_allocated_tableid += 1
                while self.last_allocated_tableid in [0, 1, 253, 254, 255]:
                    # Skip reserved table IDs
                    self.last_allocated_tableid += 1
                tableid = self.last_allocated_tableid
            # Associate the table ID to the VPN name
            self.vpn_to_tableid[vpn_name] = tableid
            # Associate the table ID to the tenant ID
            self.tableid_to_tenantid[tableid] = tenantid
            # And return
            return tableid

    def get_tableid(self, vpn_name):
      # Return the table ID associated to the VPN name
      # if not exists return -1
      return self.vpn_to_tableid.get(vpn_name, -1)

    def release_tableid(self, vpn_name):
      if self.vpn_to_tableid.get(vpn_name):
        # The VPN has an associated table ID
        tableid = self.vpn_to_tableid[vpn_name]
        # delete correspondence
        del self.vpn_to_tableid[vpn_name]
        # Delete the association table ID - tenant ID
        del self.tableid_to_tenantid[tableid]
        # Mark the table ID as reusable
        self.reusable_tableids.add(tableid)
        # ...and return table ID
        return tableid
      else:
        # The VPN has not an associated table ID
        return -1


class SIDGenerator:

    def get_sid(self, loopback_prefix, tableid):
        # A SID has three components
        # the loopback prefix of the router
        loopbacknet = IPv6Network(unicode(loopback_prefix))
        # a prefix which identifies the SIDs class
        sid_net = next(islice(loopbacknet.subnets(prefixlen_diff=1), 1, 2))
        # the identifier of the VPN (corresponding to the table ID)
        sid = next(islice(sid_net.hosts(), tableid-1, tableid)).__str__()
        # Return the SID
        return sid


class VPNHandler(srv6_vpn_nb_pb2_grpc.SRv6NorthboundVPNServicer):
    """gRPC request handler"""
    
    def __init__(self):
        self.srv6_vpn_handler = SRv6SouthboundVPN()
        self.intent_generator = VPNIntentGenerator()
        self.tableid_allocator = TableIDAllocator()
        self.sid_generator = SIDGenerator()
        self.flush_vpns()
        self.load_dump()
        self._get_vpns()

    # Get all VPNs from the routers
    def _get_vpns(self):
        # Get the network topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the loopback prefixes of the routers
        routerid_to_loopbacknet = nx.get_node_attributes(topology,'loopbacknet')
        # Re-create the VPNs starting from the controller state
        for vpn_name in self.intent_generator.get_vpns():
            intent = self.intent_generator.get_intent(vpn_name)
            self._createVPN(intent)
        return "OK"

    def _createVPN(self, intent):
        # Get the topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the loopback prefixes address of the routers
        routerid_to_loopbacknet = nx.get_node_attributes(topology,'loopbacknet')
        # Get the interfaces
        interfaces_file = self.read_interface_info(INTERFACES_FILE)
        # Get the name of the VPN
        vpn_name = intent.name
        # Get the tenantid
        tenantid = intent.tenantid
        # Get the interfaces
        interfaces = intent.interfaces
        # Validate the interfaces
        if VALIDATE_INTERFACES:
            for intf in intent.interfaces:
                # Get router name
                router = intf[0]
                # Get interface name
                intf_name = intf[1]
                # Get management ip address of the router
                router_mgmtip = routerid_to_mgmtip[router]
                # Check if the interface exists
                if interfaces_file.get(router_mgmtip) == None or interfaces_file[router_mgmtip].get(intf_name) == None:
                    return "Error: Cannot create the VPN - The interface %s does not exist on router %s" % (intf_name, router)
        # Check if the VPN already exist
        if (self.tableid_allocator.get_tableid(vpn_name) != -1
                or self.intent_generator.get_intent(vpn_name) != -1):
            return "Error: Cannot create the VPN - VPN %s already exists" % vpn_name
        # Get a new table ID
        tableid = self.tableid_allocator.get_new_tableid(vpn_name, tenantid)
        # Get the routers of the VPN
        routers = {intf[0] for intf in interfaces}
        # Create the VPN
        for router in routers:
            # Get management ip address of the router
            router_mgmtip = routerid_to_mgmtip[router]
            # Get the loopback network of the router
            loopbacknet = routerid_to_loopbacknet[router]
            # Get SID
            sid = self.sid_generator.get_sid(loopbacknet, tableid)
            # Send the creation command to the router
            if self.srv6_vpn_handler.create_vpn(router_mgmtip, vpn_name, tableid, sid) == False:
                return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
        # Save the intent
        self.intent_generator.add_intent(intent)
        return "OK"

    def _removeVPN(self, tenantid, vpn_name):
        # Get the table ID
        tableid = self.tableid_allocator.get_tableid(vpn_name)
        # Get the intent
        intent = self.intent_generator.get_intent(vpn_name)
        # Check if the VPN already exist
        if (tableid == -1 or intent == -1):
            return "Error: Cannot remove the VPN - VPN %s does not exist" % vpn_name
        for intf in intent.interfaces.copy():
            router = intf[0]
            interface = intf[1]
            self._removeInterfaceFromVPN(tenantid, vpn_name, router, interface)
        # Update VPNs information
        if self.tableid_allocator.release_tableid(vpn_name) == -1:
            return "Error: Cannot remove the VPN - VPN %s has no table ID associated" % vpn_name
        if self.intent_generator.remove_intent(vpn_name) == -1:
            return "Error: Cannot create the VPN - VPN %s has no intent associated" % vpn_name
        return "OK"

    def _addInterfaceToVPN(self, tenantid, vpn_name, router, intf_name, prefix, ipaddr):
        # Get the topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the loopback prefixes address of the routers
        routerid_to_loopbacknet = nx.get_node_attributes(topology,'loopbacknet')
        # Get the interfaces
        interfaces_file = self.read_interface_info(INTERFACES_FILE)
        # Get the VPN intent
        intent = self.intent_generator.get_intent(vpn_name)
        # Get the table ID associated to the VPN
        tableid = self.tableid_allocator.get_tableid(vpn_name)
        # Validate the interface
        if VALIDATE_INTERFACES:
            # Get management ip address of the router
            router_mgmtip = routerid_to_mgmtip[router]
            if interfaces_file.get(router_mgmtip) == None or interfaces_file[router_mgmtip].get(intf_name) == None:
                return "Error: Cannot create add interface - The interface %s does not exist on router %s" % (intf_name, router)
        # Check if the VPN already exist
        if (intent == -1 or tableid == -1):
            return "Error: Cannot add interface - VPN %s does not exists" % vpn_name
        # Get the routers already in the VPN
        routers = {intf[0] for intf in intent.interfaces}
        # Get the loopback network prefix of the router
        loopbacknet = routerid_to_loopbacknet[router]
        # Get the SID associated to the VPN
        sid = self.sid_generator.get_sid(loopbacknet, tableid)
        # If the router is not in the VPN, first create a new VPN
        if router not in routers:
            # Get management IP address of the router
            router_mgmtip = routerid_to_mgmtip[router]
            # Create the VPN in the router
            if self.srv6_vpn_handler.create_vpn(router_mgmtip, vpn_name, tableid, sid) == False:
                return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
            # Now the router is part of the VPN
            routers.add(router)
        # Add the interface to each router in the VPN
        for r in routers:
            # Get management IP address of the router
            router_mgmtip = routerid_to_mgmtip[r]
            # Add the interface to the VPN
            if r == router:
                # The interface is local to the router
                if self.srv6_vpn_handler.add_local_interface_to_vpn(router_mgmtip, vpn_name, intf_name, ipaddr) == False:
                    return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
            else:
                # The interface is remote to the router
                # Get the loopback net of the router...
                loopbacknet = routerid_to_loopbacknet[router]
                # ...and get the SID associated to the VPN
                sid = self.sid_generator.get_sid(loopbacknet, tableid)
                # Add the remote interface to the VPN
                if self.srv6_vpn_handler.add_remote_interface_to_vpn(router_mgmtip, prefix, tableid, sid) == False:
                    return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
        # Add the new interface to the intent
        interface = (router, intf_name, prefix, ipaddr)
        # Update the intent
        self.intent_generator.get_intent(vpn_name).interfaces.add(interface)
        return "OK"

    def _removeInterfaceFromVPN(self, tenantid, vpn_name, router, interface):
        # Get the topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Get the loopback prefixes address of the routers
        routerid_to_loopbacknet = nx.get_node_attributes(topology,'loopbacknet')
        # Get the table ID associated to the VPN
        tableid = self.tableid_allocator.get_tableid(vpn_name)
        # Get the intent associated to the VPN
        intent = self.intent_generator.get_intent(vpn_name)
        # Check if the VPN already exist
        if (tableid == -1 or intent == -1):
            return "Error: Cannot remove interface - VPN %s does not exists" % vpn_name
        # Get the routers in the VPN
        routers = {intf[0] for intf in intent.interfaces}
        # Get the prefixes of the interfaces
        prefixes = {(intf[0], intf[1]) : intf[2] for intf in intent.interfaces}
        # Check if the interface belongs to the VPN
        if prefixes.get((router, interface)) == None:
            return "Error: Cannot remove interface - The interface %s on the router %s does not belong to the VPN %s" % (interface, router, vpn_name)         
        # Remove the interface from the VPN in each router
        for r in routers:
            # Get management IP address of the router
            router_mgmtip = routerid_to_mgmtip[r]
            # Remove the interface from the VPN
            if r == router:
                # The interface is local to the router
                if self.srv6_vpn_handler.remove_local_interface_from_vpn(router_mgmtip, interface) == False:
                    return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
            else:
                # The interface is remote to the router
                # Get the prefix of the interface
                prefix = prefixes[(router, interface)]
                # Remove the remote interface from the VPN
                if self.srv6_vpn_handler.remove_remote_interface_from_vpn(router_mgmtip, prefix, tableid) == False:
                    return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
        # Update the intent
        count = 0
        for intf in intent.interfaces.copy():
            # Search for the interface to be removed in the intent...
            r = intf[0]
            i = intf[1]
            if r == router:
                if i == interface:
                    # ... and remove it
                    self.intent_generator.get_intent(vpn_name).interfaces.remove(intf)
                else:
                    # Count the remaining interfaces belonging to the router in the VPN
                    count += 1
        if count == 0:
            # The router has no interface in the VPN
            # Get management IP address of the router
            router_mgmtip = routerid_to_mgmtip[router]
            # Get the loopback net of the router...
            loopbacknet = routerid_to_loopbacknet[intf[0]]
            # ...and get the SID associated to the VPN
            sid = self.sid_generator.get_sid(loopbacknet, tableid)
            # Remove the router from the VPN
            if self.srv6_vpn_handler.remove_vpn(router_mgmtip, vpn_name, tableid, sid) == False:
                return srv6_vpn_msg_pb2.SRv6VPNReply(message="")
        return "OK"


    """ gRPC Server """

    # Create a VPN from an intent received through the northbound interface
    def CreateVPN(self, request, context):
        logger.debug("config received:\n%s", request)
        # Get the tenant ID
        tenantid = request.tenantid
        # Get the name of the VPN
        vpn_name = request.name
        # Generate the full name of the VPN, including the tenant id
        vpn_name = "%s-%s" % (tenantid, vpn_name)
        # Get the interfaces of the VPN from the intent
        interfaces = set()
        for intf in request.interfaces:
            # An interface is a tuple (routerid, interface_name, private_ip_address)
            router = intf.routerid
            intf_name = intf.name
            prefix = intf.prefix
            ipaddr = intf.ipaddr
            interfaces.add((router, intf_name, prefix, ipaddr))
        # Generate the intent
        intent = VPNIntent(vpn_name, interfaces, tenantid)
        response = self._createVPN(intent)
        if response != "OK":
            return srv6_vpn_msg_pb2.SRv6VPNReply(message=response)
        # Add the interfaces to the VPN
        for intf in interfaces:
            router = intf[0]
            intf_name = intf[1]
            prefix = intf[2]
            ipaddr = intf[3]
            response = self._addInterfaceToVPN(tenantid, vpn_name, router, intf_name, prefix, ipaddr)
            if response != "OK":
                return srv6_vpn_msg_pb2.SRv6VPNReply(message=response)
        # Dump the information
        self.dump()
        # Create the response
        return srv6_vpn_msg_pb2.SRv6VPNReply(message="OK")

    # Remove a VPN
    def RemoveVPN(self, request, context):
        logger.debug("Remove VPN request received:\n%s", request)
        # Extract the tenant ID from the request
        tenantid = str(request.tenantid)
        # Extract the name from the request
        vpn_name = str(request.name)
        # Get the full name of the VPN
        vpn_name = "%s-%s" % (tenantid, vpn_name)
        response = self._removeVPN(tenantid, vpn_name)
        if response != "OK":
            return srv6_vpn_msg_pb2.SRv6VPNReply(message=response)
        # Dump the information
        self.dump()
        # Create the response
        return srv6_vpn_msg_pb2.SRv6VPNReply(message="OK")

    # Add an interface to an existing a VPN
    def AddInterfaceToVPN(self, request, context):
        logger.debug("config received:\n%s", request)
        # Extract the tenant ID of the VPN from the request
        tenantid = str(request.tenantid)
        # Extract the name of the VPN from the request
        vpn_name = str(request.name)
        # Get the full name of the VPN
        vpn_name = "%s-%s" % (tenantid, vpn_name)
        # Extract the router to be added to the VPN
        router = request.interface.routerid
        # Extract the name of the interface to be added to the VPN
        intf_name = request.interface.name
        # Extract the private network prefix of the interface
        prefix = request.interface.prefix
        # Extract the private IP address of the interface
        ipaddr = request.interface.ipaddr
        # Add the interface
        response = self._addInterfaceToVPN(tenantid, vpn_name, router, intf_name, prefix, ipaddr)
        if response != "OK":
            return srv6_vpn_msg_pb2.SRv6VPNReply(message=response)
        # Dump the VPNs
        self.dump()
        # Create the response
        return srv6_vpn_msg_pb2.SRv6VPNReply(message="OK")

    # Remove an interface from an existing a VPN
    def RemoveInterfaceFromVPN(self, request, context):
        logger.debug("Remove VPN request received:\n%s", request)
        # Extract the tenant ID of the VPN from the request
        tenantid = str(request.tenantid)
        # Extract the name of the VPN from the request
        vpn_name = str(request.name)
        # Get the full name of the VPN
        vpn_name = "%s-%s" % (tenantid, vpn_name)
        # Extract the router to which the interface belongs to
        router = request.routerid
        # Extract the interface to be added
        interface = request.interface
        # Remove the interface
        response = self._removeInterfaceFromVPN(tenantid, vpn_name, router, interface)
        if response != "OK":
            return srv6_vpn_msg_pb2.SRv6VPNReply(message=response)
        # Dump the information
        self.dump()
        # Create the response
        return srv6_vpn_msg_pb2.SRv6VPNReply(message="OK")

    # Get VPNs from the controller inventory
    def GetVPNs(self, request, context):
        # Get VPNs list
        vpns = self.intent_generator.get_vpns()
        vpn_list = srv6_vpn_msg_pb2.SRv6VPNList()
        for vpn_name in vpns:
            vpn = vpn_list.vpns.add()
            vpn.name = vpn_name
            vpn.tableid = self.tableid_allocator.get_tableid(vpn_name)
            for intf in self.intent_generator.get_intent(vpn_name).interfaces: 
                interface = vpn.interfaces.append(str(intf))
        # Return the list
        return vpn_list

    # Read the topology graph and convert to a NetworkX object
    def read_json_file(self, filename):
        with open(filename) as f:
            js_graph = json.load(f)
        return json_graph.node_link_graph(js_graph)

    # Read the topology graph and convert to a NetworkX object
    def read_interface_info(self, filename):
        with open(filename) as f:
            js = json.load(f)
        return js

    # Delete all VPNs
    def flush_vpns(self):
        # Get the topology
        topology = self.read_json_file(TOPOLOGY_FILE)
        # Remove informations in each router
        for router in routerid_to_mgmtip:
            router_mgmt = routerid_to_mgmtip[router]
            if self.srv6_vpn_handler.flush_vpns(router_mgmt) == False:
               return

    # Create a dump of the VPNs
    def dump(self):
        # Get VPNs
        vpns = self.intent_generator.get_vpns()
        # Build results
        ret = dict()
        ret['vpns'] = dict()
        for vpn in vpns:
            ret['vpns'][vpn] = dict()
            ret['vpns'][vpn]['tableid'] = self.tableid_allocator.get_tableid(vpn)
            intent = self.intent_generator.get_intent(vpn)
            ret['vpns'][vpn]['intent'] = dict()
            ret['vpns'][vpn]['intent']['name'] = intent.name
            ret['vpns'][vpn]['intent']['interfaces'] = list(intent.interfaces)
            ret['vpns'][vpn]['intent']['tenantid'] = intent.tenantid
        ret['reusable_tableids'] = list(self.tableid_allocator.reusable_tableids)
        ret['tableid_to_tenantid'] = self.tableid_allocator.tableid_to_tenantid
        ret['last_allocated_tableid'] = self.tableid_allocator.last_allocated_tableid
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
                self.tableid_allocator.vpn_to_tableid[vpn] = int(vpns['vpns'][vpn]['tableid'])
                name = vpns['vpns'][vpn]['intent']['name']
                _interfaces = vpns['vpns'][vpn]['intent']['interfaces']
                interfaces = set()
                for intf in _interfaces:
                  interfaces.add(tuple(intf))
                tenantid = vpns['vpns'][vpn]['intent']['tenantid']
                intent = VPNIntent(name, interfaces, tenantid) 
                self.intent_generator.vpn_to_intent[vpn] = intent
            self.tableid_allocator.reusable_tableids = set()
            for _id in vpns['reusable_tableids']:
              self.tableid_allocator.reusable_tableids.add(int(_id))
            self.tableid_allocator.tableid_to_tenantid = dict()
            for tableid in vpns['tableid_to_tenantid']:
              self.tableid_allocator.tableid_to_tenantid[int(tableid)] = int(vpns['tableid_to_tenantid'][tableid])
            self.tableid_allocator.last_allocated_tableid = int(vpns['last_allocated_tableid'])
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
        srv6_vpn_nb_pb2_grpc.add_SRv6NorthboundVPNServicer_to_server(VPNHandler(),
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
