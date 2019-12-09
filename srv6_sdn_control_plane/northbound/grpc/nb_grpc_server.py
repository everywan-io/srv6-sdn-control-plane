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

from __future__ import absolute_import, division, print_function

# General imports
from six import text_type
from argparse import ArgumentParser
from concurrent import futures
import logging
import time
import grpc
import os
import sys
from socket import AF_UNSPEC
from socket import AF_INET
from socket import AF_INET6
# ipaddress dependencies
from ipaddress import IPv6Interface


################## Setup these variables ##################

# Path of the proto files
#PROTO_FOLDER = '../../../srv6-sdn-proto/'

###########################################################

# Path of gRPC client
#SB_GRPC_CLIENT_PATH = '../../southbound/grpc'
# Topology file
DEFAULT_TOPOLOGY_FILE = '/tmp/topology.json'
# VPN file
DEFAULT_VPN_DUMP = '/tmp/vpn.json'
# Use management IPs instead of loopback IPs
DEFAULT_USE_MGMT_IP = False

# Adjust relative paths
#script_path = os.path.dirname(os.path.abspath(__file__))
#PROTO_FOLDER = os.path.join(script_path, PROTO_FOLDER)
#SB_GRPC_CLIENT_PATH = os.path.join(script_path, SB_GRPC_CLIENT_PATH)

# Check paths
#if PROTO_FOLDER == '':
#    print('Error: Set PROTO_FOLDER variable in nb_grpc_server.py')
#    sys.exit(-2)
#if not os.path.exists(PROTO_FOLDER):
#    print('Error: PROTO_FOLDER variable in nb_grpc_server.py '
#          'points to a non existing folder\n')
#    sys.exit(-2)

# Add path of proto files
#sys.path.append(PROTO_FOLDER)
# Add path of gRPC APIs
#sys.path.append(SB_GRPC_CLIENT_PATH)
# SRv6 dependencies
#from . import nb_grpc_utils as utils
#from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils as utils
from . import nb_grpc_utils as utils
from srv6_sdn_proto import srv6_vpn_pb2_grpc
from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import inventory_service_pb2_grpc
from srv6_sdn_proto import inventory_service_pb2
#from ...southbound.grpc.sb_grpc_client import SRv6Manager
#from srv6_sdn_control_plane.southbound.grpc.sb_grpc_client import SRv6Manager
from ...southbound.grpc.sb_grpc_client import SRv6Manager
from srv6_sdn_proto import status_codes_pb2


# Global variables definition

# Default server ip and port
DEFAULT_GRPC_SERVER_IP = '::'
DEFAULT_GRPC_SERVER_PORT = 54321
DEFAULT_GRPC_CLIENT_PORT = 12345
# Secure option
DEFAULT_SECURE = False
# Server certificate
DEFAULT_CERTIFICATE = 'cert_server.pem'
# Server key
DEFAULT_KEY = 'key_server.pem'
# Southbound interface
DEFAULT_SB_INTERFACE = 'gRPC'
# Verbose mode
DEFAULT_VERBOSE = False
# Seconds between checks for interfaces.json
# and topology.json files
INTERVAL_CHECK_FILES = 5
# Supported southbound interfaces
SUPPORTED_SB_INTERFACES = ['gRPC']
# Logger reference
logger = logging.getLogger(__name__)


class InventoryService(inventory_service_pb2_grpc.InventoryServiceServicer):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 topo_graph=None, tunnels_dict=None,
                 devices=None, verbose=DEFAULT_VERBOSE):
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # Topology graph
        self.topo_graph = topo_graph
        # Tunnels dict
        self.tunnels_dict = tunnels_dict
        # Devices
        self.devices = devices


    def GetDeviceInformation(self, request, context):
        logger.debug('GetDeviceInformation request received')
        # Extract the device ids from the request
        ids = list()
        for id in request.ids:
            ids.append(id)
        # Read the topology graph
        #G = utils.json_file_to_graph(self.topo_file)
        # Create the response
        response = inventory_service_pb2.InventoryServiceReply(status=status_codes_pb2.STATUS_SUCCESS)
        '''
        # Build the devices list
        for node_id, node_info in self.topo_graph.nodes(data=True):
            if len(ids) > 0 and node_id not in ids:
                # Skip
                continue
            if node_info['type'] != 'router':
                # Skip stub networks
                continue
            device = response.device_information.devices.add()
            device.id = node_id
            if node_info.get('loopbackip'):
                device.loopbackip = node_info['loopbackip']
            if node_info.get('loopbacknet'):
                device.loopbacknet = node_info['loopbacknet']
            if node_info.get('managementip'):
                device.managementip = node_info['managementip']
            if node_info.get('interfaces'):
                for _interface, interface_info in node_info['interfaces'].items():
                    interface = device.interfaces.add()
                    interface.index = interface_info['ifindex']
                    interface.name = interface_info['ifname']
                    interface.macaddr = interface_info['macaddr']
                    interface.state = interface_info['state']
                    for ipaddr in interface_info['ipaddr']:
                        interface.ipaddrs.append(ipaddr)
        '''
        for device_id, device_info in self.devices.items():
            device = response.device_information.devices.add()
            device.id = text_type(device_id)
            _interfaces = device_info.get('interfaces', [])
            for ifname, ifinfo in _interfaces.items():
                interface = device.interfaces.add()
                interface.name = ifname
                for addr in ifinfo['mac_addrs']:
                    mac_addr = interface.mac_addrs.add()
                    mac_addr.broadcast = addr['broadcast']
                    mac_addr.addr = addr['addr']
                for addr in ifinfo['ipv4_addrs']:
                    ipv4_addr = interface.ipv4_addrs.add()
                    ipv4_addr.broadcast = addr['broadcast']
                    ipv4_addr.netmask = addr['netmask']
                    ipv4_addr.addr = addr['addr']
                for addr in ifinfo['ipv6_addrs']:
                    ipv6_addr = interface.ipv6_addrs.add()
                    ipv6_addr.broadcast = addr['broadcast']
                    ipv6_addr.netmask = addr['netmask']
                    ipv6_addr.addr = addr['addr']
        # Return the response
        logger.debug('Sending response:\n%s' % response)
        return response


    def GetTopologyInformation(self, request, context):
        logger.debug('GetTopologyInformation request received')
        # Read the topology graph
        #G = utils.json_file_to_graph(self.topo_file)
        # Create the response
        response = inventory_service_pb2.InventoryServiceReply(status=status_codes_pb2.STATUS_SUCCESS)
        # Build the topology
        routers = list()
        for node_id, node_info in self.topo_graph.nodes(data=True):
            if node_info['type'] != 'router':
                # Skip stub networks
                continue
            routers.append(node_id)
            response.topology_information.routers.append(node_id)
        for link in self.topo_graph.edges():
            if link[0] in routers and link[1] in routers:
                _link = response.topology_information.links.add()
                _link.l_router = link[0]
                _link.r_router = link[1]
        # Return the response
        logger.debug('Sending response:\n%s' % response)
        return response


    def GetTunnelInformation(self, request, context):
        logger.debug('GetTunnelInformation request received')
        # Read the topology graph
        #G = utils.json_file_to_graph(self.tunnel_file)
        # Create the response
        response = inventory_service_pb2.InventoryServiceReply(status=status_codes_pb2.STATUS_SUCCESS)
        # Build the tunnels list
        #for _tunnel in self.srv6_controller_state.get_vpns():
        for _tunnel in self.tunnels_dict:
            # Add a new tunnel to the tunnels list
            tunnel = response.tunnel_information.tunnels.add()
            # Set name
            tunnel.name = _tunnel.name
            # Set interfaces
            # Iterate on all interfaces
            for interface_info in _tunnel.interfaces.values():
                # Add a new interface to the tunnel
                _interface = tunnel.interfaces.add()
                # Add router ID
                _interface.routerid = interface_info.routerid
                # Add interface name
                _interface.interface_name = interface_info.interface_name
                # Add interface IP
                _interface.interface_ip = interface_info.interface_ip
                # Add site prefix
                _interface.site_prefix = interface_info.site_prefix
        # Return the tunnels list
        logger.debug('Sending response:\n%s' % response)
        return response


class SRv6VPNManager(srv6_vpn_pb2_grpc.SRv6VPNServicer):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 southbound_interface=DEFAULT_SB_INTERFACE,
                 srv6_controller_state=None, verbose=DEFAULT_VERBOSE):
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # Southbound interface
        self.southbound_interface = southbound_interface
        # VPN dict
        self.vpn_dict = srv6_controller_state.vpns
        # Create SRv6 Manager
        self.srv6_manager = SRv6Manager()
        # Initialize controller state
        self.srv6_controller_state = srv6_controller_state

    
    # Install a VPN on a specified router
    #
    # Three steps are required to install a VPN
    # 1. Create a rule for local SIDs processing
    # 2. Add a route to enforce packet decapsulation
    #    and lookup in the VPN table
    # 3. Create a VRF and assign it to the VPN
    def _install_vpn_on_router(self, routerid, vpn_name):
        logger.debug(
            'Attempting to install the VPN %s on the router %s'
            % (vpn_name, routerid)
        )
        # Get the router address
        router = self.srv6_controller_state.get_router_address(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return 'Cannot get the router address'
        # If the VPN is already installed on the router,
        # we don't need to create it
        installed = self.srv6_controller_state.is_vpn_installed_on_router(
            vpn_name, routerid
        )
        if installed:
            logger.debug(
                'The VPN is already installed on the router %s'
                % routerid
            )
            return 'OK'
        # First step: create a rule for local SIDs processing
        # This step is just required for the first VPN
        installed_vpns = (self.srv6_controller_state
                          .get_num_vpn_installed_on_router(routerid))
        if installed_vpns == 0:
            # We are installing the first VPN in the router
            #
            # Get SID family for this router
            sid_family = self.srv6_controller_state.get_sid_family(
                routerid
            )
            if sid_family is None:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot get SID family for routerid %s' % routerid
                )
                return 'Cannot get SID family for routerid %s' % routerid
            # Add the rule to steer the SIDs through the local SID table
            response = self.srv6_manager.create_iprule(
                router, self.grpc_client_port, family=AF_INET6,
                table=utils.LOCAL_SID_TABLE, destination=sid_family
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                logger.warning(
                    'Cannot create the IP rule for destination %s: %s'
                    % (sid_family, response)
                )
                # If the operation has failed, return an error message
                return 'Cannot create the rule for destination %s: %s' \
                    % (sid_family, response)
            # Add a blackhole route to drop all unknown active segments
            response = self.srv6_manager.create_iproute(
                router, self.grpc_client_port, family=AF_INET6,
                type='blackhole', table=utils.LOCAL_SID_TABLE
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                logger.warning(
                    'Cannot create the blackhole route: %s' % response
                )
                # If the operation has failed, return an error message
                return 'Cannot create the blackhole route: %s' % response
        # Second step is the creation of the decapsulation and lookup route
        tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
        if tableid is None:
            logger.warning('Cannot retrieve VPN table ID')
            return 'Cannot retrieve VPN table ID'
        vpn_type = self.srv6_controller_state.get_vpn_type(vpn_name)
        if vpn_type is None:
            logger.warning('Cannot retrieve VPN type')
            return 'Cannot retrieve VPN type'
        if vpn_type == utils.VPNType.IPv6VPN:
            # For IPv6 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT6 SRv6 action
            action = 'End.DT6'
        elif vpn_type == utils.VPNType.IPv4VPN:
            # For IPv4 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT4 SRv6 action
            action = 'End.DT4'
        else:
            logger.warning('Error: Unsupported VPN type: %s' % vpn_type)
            return 'Error: Unsupported VPN type %s' % vpn_type
        # Get an non-loopback interface
        # We use the management interface (which is the first interface)
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = self.srv6_controller_state.get_first_interface(routerid)
        if dev is None:
            # Cannot get non-loopback interface
            logger.warning('Cannot get non-loopback interface')
            return 'Cannot get non-loopback interface'
        # Get the SID
        logger.debug('Attempting to get a SID for the router')
        sid = self.srv6_controller_state.get_sid(routerid, tableid)
        logger.debug('Received SID %s' % sid)
        # Add the End.DT4 / End.DT6 route
        response = self.srv6_manager.create_srv6_local_processing_function(
            router, self.grpc_client_port, segment=sid, action=action,
            device=dev, localsid_table=utils.LOCAL_SID_TABLE, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            logger.warning(
                'Cannot create the SRv6 Local Processing function: %s'
                % response
            )
            # The operation has failed, return an error message
            return 'Cannot create the SRv6 Local Processing function: %s' \
                % response
        # Third step is the creation of the VRF assigned to the VPN
        response = self.srv6_manager.create_vrf_device(
            router, self.grpc_client_port, name=vpn_name, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            logger.warning(
                'Cannot create the VRF %s: %s' % (vpn_name, response)
            )
            # If the operation has failed, return an error message
            return 'Cannot create the VRF %s: %s' % (vpn_name, response)
        # Add all the remote destinations to the VPN
        interfaces = self.srv6_controller_state.get_vpn_interfaces(
            vpn_name
        )
        if interfaces is not None:
            for intf in interfaces:
                if intf.routerid == routerid:
                    print('Bug in _assign_interface_to_vpn(): attempt to add a'
                          ' local interface to a not-already-in-router VPN')
                    exit(-1)
                # Get the SID
                sid = self.srv6_controller_state.get_sid(
                    intf.routerid, tableid
                )
                # Add remote interfacace to the VPN
                response = self._assign_remote_interface_to_vpn(
                    routerid, intf.vpn_prefix, tableid, sid
                )
                if response != 'OK':
                    logger.warning(
                        'Cannot add remote interface to the VPN: %s'
                        % (response)
                    )
                    # If the operation has failed, return an error message
                    return response
        # The VPN has been installed on the router
        #
        # Update data structures
        logger.debug('Updating controller state')
        succ = self.srv6_controller_state.add_router_to_vpn(routerid, vpn_name)
        if not succ:
            logger.warning('Cannot add the router to the VPN')
            return 'Cannot add the router to the VPN'
        # Success
        logger.debug('The VPN has been successfully installed on the router')
        return 'OK'

    # Remove a router from a VPN
    #
    # Three steps are required to install a VPN
    # 1. Remove the decap and lookup route
    # 2. Remove the VRF associated to the VPN
    # 3. Remove the IPv6/IPv4 routes associated to the VPN
    # 4. If there are no more VPNs installed on the router,
    #    we can safely remove the local SIDs processing rule
    def _remove_vpn_from_router(self, routerid, vpn_name, sid, tableid):
        # Get the router address
        router = self.srv6_controller_state.get_router_address(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return 'Cannot get the router address'
        # If the VPN is not installed on the router we don't need to remove it
        installed = self.srv6_controller_state.is_vpn_installed_on_router(
            vpn_name, routerid
        )
        if not installed:
            logger.debug(
                'The VPN is not installed on the router %s' % routerid
            )
            return 'OK'
        # Remove the decap and lookup function (i.e. the End.DT4 or End.DT6
        # route)
        response = self.srv6_manager.remove_srv6_local_processing_function(
            router, self.grpc_client_port, segment=sid,
            localsid_table=utils.LOCAL_SID_TABLE
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove seg6local route: %s' % response)
            return 'Cannot remove seg6local route: %s' % response
        # Delete the VRF assigned to the VPN
        response = self.srv6_manager.remove_vrf_device(
            router, self.grpc_client_port, vpn_name
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the VRF %s from the router %s: %s'
                % (vpn_name, router, response)
            )
            return 'Cannot remove the VRF %s from the router %s' \
                % (vpn_name, router)
        # Delete all remaining IPv6 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            router, self.grpc_client_port, family=AF_INET6, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the IPv6 route: %s' % response)
            return 'Cannot remove the IPv6 route: %s' % response
        # Delete all remaining IPv4 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            router, self.grpc_client_port, family=AF_INET, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove IPv4 routes: %s' % response)
            return 'Cannot remove IPv4 routes: %s' % response
        # Remove the VPN from the controller state
        if not self.srv6_controller_state.remove_vpn_from_router(vpn_name, routerid):
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the VPN from the controller state')
            return 'Cannot remove the VPN from the controller state'
        # If no more VPNs are installed on the router,
        # we can delete the rule for local SIDs
        if self.srv6_controller_state.get_num_vpn_installed_on_router(routerid) == 0:
            # Get SID family for this router
            sid_family = self.srv6_controller_state.get_sid_family(routerid)
            if sid_family is None:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot get SID family for routerid %s' % routerid
                )
                return 'Cannot get SID family for routerid %s' % routerid
            # Remove rule for SIDs
            response = self.srv6_manager.remove_iprule(
                router, self.grpc_client_port, family=AF_INET6, table=utils.LOCAL_SID_TABLE,
                destination=sid_family
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the localSID rule: %s' % response
                )
                return 'Cannot remove the localSID rule: %s' % response
            # Remove blackhole route
            response = self.srv6_manager.remove_iproute(
                router, self.grpc_client_port, family=AF_INET6, type='blackhole',
                table=utils.LOCAL_SID_TABLE
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the blackhole rule: %s' % response
                )
                return 'Cannot remove the blackhole rule: %s' % response
        # Success
        logger.debug('Successfully removed the VPN from the router')
        return 'OK'

    # Associate a router interface to a VPN
    #
    # 1. Take the router owning the interface; if the VPN is not yet installed
    #    on it, we need to install the VPN and assign to it all the interface
    #    already belonging to the VPN before we can add the new interfac
    # 2. Iterate on the routers on which the VPN is installed and add the new
    #    interface to the VPN
    def _assign_interface_to_vpn(self, vpn_name, interface):
        logger.debug(
            'Attempting to associate the interface %s to the '
            'VPN %s' % (interface.interface_name, vpn_name)
        )
        # Get table ID
        tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
        if tableid is None:
            logger.warning('Cannot get table ID for the VPN %s' % vpn_name)
            return('Cannot get table ID for the VPN %s' % vpn_name)
        # Get the SID
        logger.debug('Attempting to get a SID for the router')
        sid = self.srv6_controller_state.get_sid(interface.routerid, tableid)
        logger.debug('Received SID %s' % sid)
        # Extract params from the VPN
        vpn_type = self.srv6_controller_state.get_vpn_type(vpn_name)
        if vpn_type is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get VPN type for the VPN %s' % vpn_name)
            return 'Cannot get VPN type the VPN %s' % vpn_name
        # Extract params from the interface
        routerid = interface.routerid
        interface_name = interface.interface_name
        interface_ip = interface.interface_ip
        vpn_prefix = interface.vpn_prefix
        # Set the address family depending on the VPN type
        if vpn_type == utils.VPNType.IPv6VPN:
            family = AF_INET6
        elif vpn_type == utils.VPNType.IPv4VPN:
            family = AF_INET
        else:
            logger.warning('Unsupported VPN type: %s' % vpn_type)
            return 'Unsupported VPN type: %s' % vpn_type
        # Iterate on the routers on which the VPN is already installed
        # and assign the interface to the VPN
        # The interface can be local or remote
        for r in self.srv6_controller_state.get_routers_in_vpn(vpn_name):
            # Assign the interface to the VPN
            if r == routerid:
                # The interface is local to the router
                logger.debug(
                    'Attempting to add the local interface %s to the VPN %s'
                    % (interface_name, vpn_name)
                )
                response = self._assign_local_interface_to_vpn(
                    r, vpn_name, interface_name, interface_ip,
                    vpn_prefix, family
                )
                if response != 'OK':
                    logger.warning(
                        'Cannot add the local interface to the VPN: %s'
                        % response
                    )
                    # The operation has failed, return an error message
                    return response
            else:
                logger.debug(
                    'Attempting to add the remote interface %s to the VPN %s'
                    % (interface_name, vpn_name)
                )
                # The interface is remote to the router
                response = self._assign_remote_interface_to_vpn(
                    r, vpn_prefix, tableid, sid
                )
                if response != 'OK':
                    logger.warning(
                        'Cannot add the remote interface to the VPN: %s'
                        % response
                    )
                    # The operation has failed, return an error message
                    return response
        # Add the new interface to the controller state
        logger.debug('Add interface to controller state')
        self.srv6_controller_state.add_interface_to_vpn(
            vpn_name, routerid, interface_name, interface_ip, vpn_prefix
        )
        # Success
        logger.debug('Interface assigned to the VPN successfully')
        return 'OK'

    # Remove an interface from a VPN
    #
    # 1. Iterate on the routers on which the VPN is installed and remove the
    #    interface from the VPN
    # 2. If the router owning the interface has no more interfaces on the VPN,
    #    remove the VPN from the router
    def _remove_interface_from_vpn(self, routerid, interface_name, vpn_name):
        logger.debug(
            'Attempting to remove interface %s from the VPN %s'
            % (interface_name, vpn_name)
        )
        # Extract params from the VPN
        tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
        if tableid is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get table ID for the VPN %s' % vpn_name)
            return 'Cannot get table ID for the VPN %s' % vpn_name
        # Extract VPN prefix
        vpn_prefix = self.srv6_controller_state.get_vpn_prefix(
            vpn_name, routerid, interface_name
        )
        if vpn_prefix is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get VPN prefix for the VPN %s' % vpn_name)
            return 'Cannot get VPN prefix the VPN %s' % vpn_name
        # Iterate on the routers on which the VPN is installed
        # and remove the interfaces from the VPN
        interfaces = self.srv6_controller_state.get_vpn_interfaces(vpn_name)
        if interfaces is None:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot get the interfaces associated to the '
                'VPN %s' % vpn_name
            )
            return 'Cannot get the interfaces associated to the VPN %s' \
                % vpn_name
        routers = self.srv6_controller_state.get_routers_in_vpn(vpn_name)
        for r in routers:
            # Remove the interface from the VPN
            if r == routerid:
                # The interface is local to the router
                response = self._remove_local_interface_from_vpn(
                    r, vpn_name, interface_name
                )
                if response != 'OK':
                    # If the operation has failed, return an error message
                    logger.warning(
                        'Cannot remove the local interface %s from '
                        'the VPN %s' % (interface_name, vpn_name)
                    )
                    return response
            else:
                # The interface is remote to the router
                response = self._remove_remote_interface_from_vpn(
                    r, vpn_prefix, tableid
                )
                if response != 'OK':
                    # If the operation has failed, return an error message
                    logger.warning(
                        'Cannot remove the remote interface %s from the VPN '
                        '%s' % (vpn_prefix, vpn_name)
                    )
                    return response
        # Remove the interface from the VPNs dictionary
        response = self.srv6_controller_state.remove_interface_from_vpn(
            routerid, interface_name, vpn_name
        )
        if not response:
            return 'Interface not found %s on router %s' \
                                    % (interface_name, routerid)
        if self.srv6_controller_state.get_number_of_interfaces(vpn_name, routerid) == 0:
            # No more interfaces belonging to the VPN in the router,
            # remove remote interfaces from the VPN
            interfaces = self.srv6_controller_state.get_vpn_interfaces(
                vpn_name
            )
            for i in interfaces:    
                print(i.routerid)
                print(i.interface_name)
                print(i.interface_ip)
                print(i.vpn_prefix)
            for intf in interfaces:
                if intf.routerid == routerid:
                    # Skip local destinations
                    logger.critical('Bug in _remove_interface_from_vpn()')
                    exit(-1)
                # Remove the remote interface
                response = self._remove_remote_interface_from_vpn(
                    routerid, intf.vpn_prefix, tableid
                )
                if response != 'OK':
                    # If the operation has failed, return an error message
                    logger.warning(
                        'Cannot remove the remote interface %s from the router'
                        ' %s' % (intf.vpn_prefix, routerid)
                    )
                    return response
            # Get the SID
            sid = self.srv6_controller_state.get_sid(routerid, tableid)
            if sid is None:
                # If the operation has failed, return an error message
                logger.warning('Cannot get SID for routerid %s' % routerid)
                return 'Cannot get SID for routerid %s' % routerid
            # Remove the VPN from the router
            response = self._remove_vpn_from_router(
                routerid, vpn_name, sid, tableid
            )
            if response != 'OK':
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the VPN %s from the router %s'
                    % (vpn_name, routerid)
                )
                return response
        # Success
        logger.debug('Interface removed successfully from the VPN')
        return 'OK'

    # Assign a local interface to a VPN
    def _assign_local_interface_to_vpn(self, routerid, vpn_name,
                                       interface_name, interface_ip,
                                       vpn_prefix, family):
        logger.debug(
            'Attempting to assign local interface %s to the VPN %s'
            % (interface_name, vpn_name)
        )
        # Get router address
        router = self.srv6_controller_state.get_router_address(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return 'Cannot get the router address'
        # Remove all IPv4 and IPv6 addresses
        addrs = self.srv6_controller_state.get_interface_ips(
            routerid, interface_name
        )
        if addrs is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get interface addresses')
            return 'Cannot get interface addresses'
        nets = []
        for addr in addrs:
            nets.append(str(IPv6Interface(addr).network))
        response = self.srv6_manager.remove_many_ipaddr(
            router, self.grpc_client_port, addrs=addrs, nets=nets,
            device=interface_name, family=AF_UNSPEC
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot remove the public addresses from the interface'
            )
            return 'Cannot remove the public addresses from the interface'
        # Don't advertise the private customer network
        response = self.srv6_manager.update_interface(
            router, self.grpc_client_port, name=interface_name, ospf_adv=False
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot disable OSPF advertisements')
            return 'Cannot disable OSPF advertisements'
        # Add IP address to the interface
        response = self.srv6_manager.create_ipaddr(
            router, self.grpc_client_port, ip_addr=interface_ip,
            device=interface_name, net=vpn_prefix, family=family
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot assign the private VPN IP address to the interface'
            )
            return 'Cannot assign the private VPN IP address to the interface'
        # Get the interfaces assigned to the VPN
        interfaces_in_vpn = self.srv6_controller_state.get_vpn_interface_names(
            vpn_name, routerid
        )
        if interfaces_in_vpn is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get VPN interfaces')
            return 'Cannot get VPN interfaces'
        interfaces_in_vpn.add(interface_name)
        # Add the interface to the VRF
        response = self.srv6_manager.update_vrf_device(
            router, self.grpc_client_port, name=vpn_name,
            interfaces=interfaces_in_vpn
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot assign the interface to the VRF: %s' % response
            )
            return 'Cannot assign the interface to the VRF: %s' % response
        # Success
        logger.debug('Local interface assigned to VPN successfully')
        return 'OK'

    # Assign an local interface to a VPN
    def _assign_remote_interface_to_vpn(self, routerid, vpn_prefix, tableid,
                                        sid):
        logger.debug(
            'Attempting to assign remote interface %s to the VPN'
            % vpn_prefix
        )
        # Get router address
        router = self.srv6_controller_state.get_router_address(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return 'Cannot get the router address'
        # Any non-loopback device
        # We use the management interface (which is the first interface)
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = self.srv6_controller_state.get_first_interface(routerid)
        if dev is None:
            # Cannot get non-loopback interface
            logger.warning('Cannot get non-loopback interface')
            return 'Cannot get non-loopback interface'
        # Create the SRv6 route
        response = self.srv6_manager.create_srv6_explicit_path(
            router, self.grpc_client_port, destination=vpn_prefix,
            table=tableid, device=dev, segments=[sid], encapmode='encap'
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot create SRv6 Explicit Path: %s' % response)
            return 'Cannot create SRv6 Explicit Path: %s' % response
        # Success
        logger.debug('Remote interface assigned to VPN successfully')
        return 'OK'

    # Remove a local interface from a VPN
    def _remove_local_interface_from_vpn(self, routerid, vpn_name,
                                         interface_name):
        logger.debug(
            'Attempting to remove local interface %s from the VPN %s'
            % (interface_name, vpn_name)
        )
        # Get router address
        router = self.srv6_controller_state.get_router_address(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return 'Cannot get the router address'
        # Remove all the IPv4 and IPv6 addresses
        addr = self.srv6_controller_state.get_vpn_interface_ip(
            vpn_name, routerid, interface_name
        )
        if addr is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get interface address')
            return 'Cannot get interface address'
        net = str(IPv6Interface(addr).network)
        response = self.srv6_manager.remove_ipaddr(
            router, self.grpc_client_port, ip_addr=addr, net=net,
            device=interface_name, family=AF_UNSPEC
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove address from the interface: %s' % response
            )
            return 'Cannot remove address from the interface: %s' % response
        # Enable advertisements the private customer network
        response = self.srv6_manager.update_interface(
            router, self.grpc_client_port, name=interface_name, ospf_adv=True
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot enable OSPF advertisements: %s' % response)
            return 'Cannot enable OSPF advertisements: %s' % response
        # Get the interfaces assigned to the VPN
        interfaces_in_vpn = self.srv6_controller_state.get_vpn_interface_names(
            vpn_name, routerid
        )
        if interfaces_in_vpn is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get VPN interfaces')
            return 'Cannot get VPN interfaces'
        interfaces_in_vpn.remove(interface_name)
        # Remove the interface from the VRF
        response = self.srv6_manager.update_vrf_device(
            router, self.grpc_client_port, name=vpn_name,
            interfaces=interfaces_in_vpn
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the VRF device: %s' % response)
            return 'Cannot remove the VRF device: %s' % response
        # Success
        logger.debug('Local interface removed successfully')
        return 'OK'

    # Remove a remote interface from a VPN
    def _remove_remote_interface_from_vpn(self, routerid, vpn_prefix, tableid):
        logger.debug(
            'Attempting to remove remote interface %s from the VPN'
            % vpn_prefix
        )
        # Get router address
        router = self.srv6_controller_state.get_router_address(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return 'Cannot get the router address'
        # Remove the SRv6 route
        response = self.srv6_manager.remove_srv6_explicit_path(
            router, self.grpc_client_port, destination=vpn_prefix,
            table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove SRv6 Explicit Path: %s' % response)
            return 'Cannot remove SRv6 Explicit Path: %s' % response
        # Success
        logger.debug('Remote inteface removed successfully')
        return 'OK'
    

    """gRPC Server"""

    """Create a VPN from an intent received through the northbound interface"""
    def CreateVPN(self, request, context):
        logger.info('CreateVPN request received:\n%s', request)
        # Get the updated topology
        if not self.srv6_controller_state.load_topology_from_json_dump():
            logger.warning('Cannot import the topology')
            # Error while retrieving the updated topology
            return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_TOPO_NOTFOUND)
        # Extract the intents from the request message
        for intent in request.intents:
            logger.info('Processing the intent:\n%s' % intent)
            # Extract the VPN tenant ID from the intent
            tenantid = int(intent.tenantid)
            # Validate the tenant ID
            logger.debug('Validating the tenant ID:\n%s' % tenantid)
            if not utils.validate_tenantid(tenantid):
                logger.warning('Invalid tenant ID: %s' % tenantid)
                # If tenant ID is invalid, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_TENANTID)
            # Extract the VPN type from the intent
            vpn_type = int(intent.vpn_type)
            # Validate the VPN type
            logger.debug('Validating the VPN type:\n%s' % vpn_type)
            if not utils.validate_vpn_type(vpn_type):
                logger.warning('Invalid VPN type: %s' % vpn_type)
                # If the VPN type is invalid, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_TYPE)
            # Extract the VPN name from the intent
            vpn_name = intent.vpn_name
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Let's check if the VPN does not exist
            logger.debug('Validating the VPN name:\n%s' % vpn_name)
            if self.srv6_controller_state.vpn_exists(vpn_name):
                logger.warning('VPN name %s is already in use' % vpn_name)
                # If the VPN already exists, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_NAME_UNAVAILABLE)
            # Validate the VPN interfaces included in the intent
            for interface in intent.interfaces:
                logger.debug('Validating the interface:\n%s' % interface)
                # An interface is a tuple
                # (routerid, interface_name, interface_ip, vpn_prefix)
                #
                # Extract the router ID
                routerid = interface.routerid
                # Let's check if the router exists
                if not self.srv6_controller_state.router_exists(routerid):
                    logger.warning(
                        'The topology does not contain the router %s'
                        % routerid
                    )
                    # If the router does not exist, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_ROUTER_NOTFOUND)
                # Extract the interface name
                interface_name = interface.interface_name
                # Let's check if the interface exists
                if not self.srv6_controller_state.interface_exists(
                        interface_name, routerid):
                    logger.warning('The interface does not exist')
                    # If the interface does not exists, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTF_NOTFOUND)
                # Extract interface IP address
                interface_ip = interface.interface_ip
                # Extract VPN prefix
                vpn_prefix = interface.vpn_prefix
                # Validate interface IP address
                if vpn_type == utils.VPNType.IPv4VPN:
                    is_ip_valid = utils.validate_ipv4_address(interface_ip)
                    is_prefix_valid = utils.validate_ipv4_address(vpn_prefix)
                elif vpn_type == utils.VPNType.IPv6VPN:
                    is_ip_valid = utils.validate_ipv6_address(interface_ip)
                    is_prefix_valid = utils.validate_ipv6_address(vpn_prefix)
                else:
                    logger.warning('Invalid VPN type: %s' % vpn_type)
                    # If the VPN type is invalid, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_TYPE)
                if not is_ip_valid:
                    logger.warning('Invalid IP address: %s' % interface_ip)
                    # If the IP address is invalid, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_IP)
                if not is_prefix_valid:
                    logger.warning('Invalid VPN prefix: %s' % vpn_prefix)
                    # If the IP address is invalid, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_PREFIX)
                # Extract tunnel type
                tunnel_type = intent.tunnel
            logger.info('All checks passed')
            # All checks passed, we are ready to create VPN
            #
            # Get a new table ID for the VPN
            logger.debug('Attempting to get a new table ID for the VPN')
            tableid = self.srv6_controller_state.get_new_tableid(
                vpn_name, tenantid
            )
            logger.debug('New table ID assigned to the VPN:%s', tableid)
            logger.debug('Validating the table ID:\n%s' % tableid)
            # Validate the table ID
            if not utils.validate_table_id(tableid):
                logger.warning('Invalid table ID: %s' % tableid)
                # If the table ID is not valid, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            # Update data structures
            logger.debug('Updating controller state')
            self.srv6_controller_state.add_vpn(
                vpn_name, vpn_type, tenantid, tableid
            )
            # Iterate on the routers and install the VPN
            routers = set()
            for interface in intent.interfaces:
                routers.add(interface.routerid)
            for r in routers:
                response = self._install_vpn_on_router(r, vpn_name)
                if response != 'OK':
                    # The operation has failed, return an error message
                    logger.warning(
                        'Cannot install the VPN on the router: %s' % response
                    )
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            # Iterate on the interfaces and assign them to the VPN
            for interface in intent.interfaces:
                # Get the routerid
                routerid = interface.routerid
                # Get the interface name
                interface_name = interface.interface_name
                # Add the interface to the VPN
                response = self._assign_interface_to_vpn(vpn_name, interface)
                if response != 'OK':
                    logger.warning(
                        'Cannot associate the interface %s to the VPN %s'
                        % (interface.interface_name, vpn_name)
                    )
                    # If the operation has failed, report the error
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            logger.info('The VPN has been created successfully')
            # Save the VPNs dump to file
            if self.vpn_dump is not None:
                logger.info('Saving the VPN dump')
                self.srv6_controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_SUCCESS)

    """Remove a VPN"""
    def RemoveVPN(self, request, context):
        logger.info('RemoveVPN request received:\n%s', request)
        # Get the updated topology
        if not self.srv6_controller_state.load_topology_from_json_dump():
            logger.warning('Cannot import the topology')
            # Error while retrieving the updated topology
            return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_TOPO_NOTFOUND)
        # Extract the intents from the request message
        for intent in request.intents:
            # Extract the VPN tenant ID from the intent
            tenantid = intent.tenantid
            # Extract the VPN name from the intent
            vpn_name = str(intent.vpn_name)
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Let's check if the VPN exists
            logger.debug('Checking the VPN:\n%s' % vpn_name)
            if not self.srv6_controller_state.vpn_exists(vpn_name):
                logger.warning('The VPN %s does not exist' % vpn_name)
                # If the VPN already exists, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_NOTFOUND)
            logger.debug('Check passed')
            # Remove all the interfaces from the VPN
            for interface in (self
                              .srv6_controller_state.get_vpn_interfaces(vpn_name)):
                # Remove the interface from the VPN
                logger.debug(
                    'Attempting to remove the interface:\n%s\n' % interface
                )
                response = self._remove_interface_from_vpn(
                    interface.routerid, interface.interface_name, vpn_name
                )
                if response != 'OK':
                    logger.warning('Cannot remove the interface')
                    # If the operation has failed, report the error
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            # Remove the VPN
            if not self.srv6_controller_state.remove_vpn(vpn_name):
                logger.warning(
                    'Cannot remove the VPN from the controller state'
                )
                # If the operation fails, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            # Release the table ID
            if self.srv6_controller_state.release_tableid(vpn_name) == -1:
                logger.warning(
                    'Cannot release the table ID'
                )
                # If the operation fails, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            logger.info('The VPN has been removed successfully')
            # Save the VPNs dump to file
            if self.vpn_dump is not None:
                logger.info('Saving the VPN dump')
                self.srv6_controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_SUCCESS)

    """Assign an interface to a VPN"""
    def AssignInterfaceToVPN(self, request, context):
        logger.info('AssignInterfaceToVPN request received:\n%s' % request)
        # Get the updated topology
        if not self.srv6_controller_state.load_topology_from_json_dump():
            # Error while retrieving the updated topology
            logger.warning('Cannot import the topology')
            return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_TOPO_NOTFOUND)
        # Extract the intents from the request message
        for intent in request.intents:
            # Extract the VPN tenant ID from the intent
            tenantid = intent.tenantid
            # Extract the VPN name from the intent
            vpn_name = str(intent.vpn_name)
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Let's check if the VPN exists
            logger.debug('Checking the VPN:\n%s' % vpn_name)
            if not self.srv6_controller_state.vpn_exists(vpn_name):
                # If the VPN already exists, return an error message
                logger.warning('The VPN %s does not exist' % vpn_name)
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_NOTFOUND)
            # Iterate on the interfaces and extract the interfaces to be assigned
            # to the VPN and validate them
            for interface in intent.interfaces:
                logger.debug('Validating the interface:\n%s' % interface)
                # Get router ID
                routerid = interface.routerid
                # Let's check if the router ID exists
                if not self.srv6_controller_state.router_exists(routerid):
                    # If the router ID does not exist, return an error message
                    logger.warning(
                        'The topology does not contain the router %s' % routerid
                    )
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_ROUTER_NOTFOUND)
                # Get interface name
                interface_name = interface.interface_name
                # Let's check if the interface exists
                if not self.srv6_controller_state.interface_exists(interface_name,
                                                                   routerid):
                    # If the interface does not exist, return an error message
                    logger.warning('The interface does not exist')
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTF_NOTFOUND)
                # Get interface IP address assigned to the interface
                interface_ip = interface.interface_ip
                # Get VPN prefix assigned to the interface
                vpn_prefix = interface.vpn_prefix
                # Validate interface IP address
                vpn_type = self.srv6_controller_state.get_vpn_type(vpn_name)
                if vpn_type == utils.VPNType.IPv4VPN:
                    is_ip_valid = utils.validate_ipv4_address(interface_ip)
                    is_prefix_valid = utils.validate_ipv4_address(vpn_prefix)
                elif vpn_type == utils.VPNType.IPv6VPN:
                    is_ip_valid = utils.validate_ipv6_address(interface_ip)
                    is_prefix_valid = utils.validate_ipv6_address(vpn_prefix)
                else:
                    logger.warning('Invalid VPN type: %s' % vpn_type)
                    # If the VPN type is invalid, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_TYPE)
                if not is_ip_valid:
                    logger.warning('Invalid IP address: %s' % interface_ip)
                    # If the IP address is invalid, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_IP)
                if not is_prefix_valid:
                    logger.warning('Invalid VPN prefix: %s' % vpn_prefix)
                    # If the IP address is invalid, return an error message
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_INVALID_PREFIX)
                # Let's make sure that the interface is not assigned to another VPN
                if self.srv6_controller_state.interface_in_any_vpn(routerid,
                                                                   interface_name):
                    # If the interface is already assigned to a VPN, return an
                    # error message
                    logger.warning(
                        'The interface %s is already assigned to a VPN'
                        % interface_name
                    )
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTF_ALREADY_ASSIGNED)
            # Assign the interfaces to the VPN
            #
            # Get table ID and router ID, used to generate the SID required to
            # assign the interface to the VPN
            logger.debug('Attempting to get the table ID of the VPN')
            tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
            logger.debug('Received table ID: %s' % tableid)
            # Get the SID
            logger.debug('Attempting to get a SID for the router')
            sid = self.srv6_controller_state.get_sid(routerid, tableid)
            logger.debug('Received SID %s' % sid)
            # Assign the interface to the VPN
            for interface in intent.interfaces:
                logger.debug(
                    'Attempting to assign the interface %s to the VPN %s'
                    % (interface.interface_name, vpn_name)
                )
                # Check if the VPN is already installed on the router
                already_installed = self.srv6_controller_state \
                        .is_vpn_installed_on_router(vpn_name, interface.routerid)
                if already_installed:
                    logger.debug(
                        'The VPN %s is already installed on the router %s'
                        % (vpn_name, routerid)
                    )
                else:
                    # If not, install the VPN on the router
                    logger.debug(
                        'The VPN %s is not installed on the router %s'
                        % (vpn_name, routerid)
                    )
                    logger.debug(
                        'Attempting to install the VPN %s on the router %s'
                        % (vpn_name, routerid)
                    )
                    response = self._install_vpn_on_router(routerid, vpn_name)
                    if response != 'OK':
                        # The operation has failed, return an error message
                        logger.warning(
                            'Cannot install the VPN on the router: %s' % response
                        )
                        return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
                response = self._assign_interface_to_vpn(vpn_name, interface)
                if response != 'OK':
                    logger.warning(
                        'Cannot associate the interface %s to the VPN %s'
                        % (interface.interface_name, vpn_name)
                    )
                    # If the operation has failed, report the error
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTERNAL_ERROR)
            logger.info('The VPN has been changed successfully')
            # Save the VPNs dump to file
            if self.vpn_dump is not None:
                logger.info('Saving the VPN dump')
                self.srv6_controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_SUCCESS)

    """Remove an interface from a VPN"""
    def RemoveInterfaceFromVPN(self, request, context):
        logger.info('RemoveInterfaceFromVPN request received:\n%s' % request)
        # Get the updated topology
        if not self.srv6_controller_state.load_topology_from_json_dump():
            # Error while retrieving the updated topology
            logger.warning('Error while retrieving the updated topology')
            return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_TOPO_NOTFOUND)
        # Extract the intents from the request message
        for intent in request.intents:
            # Extract the VPN tenant ID from the intent
            tenantid = intent.tenantid
            # Extract the VPN name from the intent
            vpn_name = str(intent.vpn_name)
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Let's check if the VPN exists
            if not self.srv6_controller_state.vpn_exists(vpn_name):
                logger.warning('The VPN %s does not exist' % vpn_name)
                # If the VPN already exists, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_VPN_NOTFOUND)
            # Iterate on the interfaces and extract the interfaces to be removed
            # from the VPN
            for interface in intent.interfaces:
                logger.debug('Validating the interface:\n%s' % interface)
                # Get the router ID
                routerid = interface.routerid
                # Let's check if the router ID exists
                if not self.srv6_controller_state.router_exists(routerid):
                    # If the router ID does not exist, return an error message
                    logger.warning(
                        'The topology does not contain the router %s' % routerid
                    )
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_ROUTER_NOTFOUND)
                # Get the interface name
                interface_name = interface.interface_name
                # Let's check if the interface exists
                if not self.srv6_controller_state.interface_exists(interface_name,
                                                                   routerid):
                    # The interface does not exist, return an error message
                    logger.warning('The interface does not exist')
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTF_NOTFOUND)
                # Let's check if the interface is assigned to the given VPN
                if not self.srv6_controller_state.interface_in_vpn(routerid,
                                                                   interface_name,
                                                                   vpn_name):
                    # The interface is not assigned to the VPN, return an error
                    # message
                    logger.warning(
                        'The interface is not assigned to the VPN %s' % vpn_name
                    )
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTF_NOTASSIGNED)
            # Iterate on interfaces to be removed from the VPN
            for interface in intent.interfaces:
                # Remove the interface
                logger.debug(
                    'Attempting to remove the interface %s from the VPN %s'
                    % (interface.interface_name, vpn_name)
                )
                response = self._remove_interface_from_vpn(
                    interface.routerid, interface.interface_name, vpn_name
                )
                if response != 'OK':
                    # If the operation has failed, report the error
                    logger.warning('The interface does not exist: %s' % response)
                    return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_INTF_NOTFOUND)
            logger.info('The VPN has been changed successfully')
            # Save the VPNs dump to file
            if self.vpn_dump is not None:
                logger.info('Saving the VPN dump')
                self.srv6_controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_SUCCESS)

    # Get VPNs from the controller inventory
    def GetVPNs(self, request, context):
        logger.debug('GetVPNs request received')
        # Create the response
        response = srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_SUCCESS)
        # Build the VPNs list
        for _vpn in self.srv6_controller_state.get_vpns():
            # Add a new VPN to the VPNs list
            vpn = response.vpns.add()
            # Set name
            vpn.vpn_name = _vpn.vpn_name
            # Set table ID
            vpn.tableid = _vpn.tableid
            # Set interfaces
            # Iterate on all interfaces
            for interfaces in _vpn.interfaces.values():
                for interface in interfaces.values():
                    # Add a new interface to the VPN
                    _interface = vpn.interfaces.add()
                    # Add router ID
                    _interface.routerid = interface.routerid
                    # Add interface name
                    _interface.interface_name = interface.interface_name
                    # Add interface IP
                    _interface.interface_ip = interface.interface_ip
                    # Add VPN prefix
                    _interface.vpn_prefix = interface.vpn_prefix
        # Return the VPNs list
        logger.debug('Sending response:\n%s' % response)
        return response


# Start gRPC server
def start_server(grpc_server_ip=DEFAULT_GRPC_SERVER_IP,
                 grpc_server_port=DEFAULT_GRPC_SERVER_PORT,
                 grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 secure=DEFAULT_SECURE, key=DEFAULT_KEY,
                 certificate=DEFAULT_CERTIFICATE,
                 southbound_interface=DEFAULT_SB_INTERFACE,
                 topo_graph=None, vpn_dict=None,
                 devices=None,
                 vpn_file=DEFAULT_VPN_DUMP,
                 use_mgmt_ip=DEFAULT_USE_MGMT_IP,
                 verbose=DEFAULT_VERBOSE):
    # Initialize controller state
    srv6_controller_state = utils.SRv6ControllerState(
        topo_graph, vpn_dict, vpn_file, use_mgmt_ip
    )
    # Setup gRPC server
    #
    # Create the server and add the handler
    grpc_server = grpc.server(futures.ThreadPoolExecutor())
    srv6_vpn_pb2_grpc.add_SRv6VPNServicer_to_server(
        SRv6VPNManager(
            grpc_client_port, southbound_interface, srv6_controller_state, verbose
        ), grpc_server
    )
    inventory_service_pb2_grpc.add_InventoryServiceServicer_to_server(
        InventoryService(
            grpc_client_port, topo_graph, vpn_dict, devices, verbose
        ), grpc_server
    )
    # If secure mode is enabled, we need to create a secure endpoint
    if secure:
        # Read key and certificate
        with open(key) as f:
            key = f.read()
        with open(certificate) as f:
            certificate = f.read()
        # Create server SSL credentials
        grpc_server_credentials = grpc.ssl_server_credentials(
            ((key, certificate,),)
        )
        # Create a secure endpoint
        grpc_server.add_secure_port(
            '[%s]:%s' % (grpc_server_ip, grpc_server_port),
            grpc_server_credentials
        )
    else:
        # Create an insecure endpoint
        grpc_server.add_insecure_port(
            '[%s]:%s' % (grpc_server_ip, grpc_server_port)
        )
    # Start the loop for gRPC
    logger.info('Listening gRPC')
    grpc_server.start()
    while True:
        time.sleep(5)


# Parse arguments
def parse_arguments():
    # Get parser
    parser = ArgumentParser(
        description='gRPC-based Northbound APIs for SRv6 Controller'
    )
    # Debug logs
    parser.add_argument(
        '-d', '--debug', action='store_true', help='Activate debug logs'
    )
    # gRPC secure mode
    parser.add_argument(
        '-s', '--secure', action='store_true',
        default=DEFAULT_SECURE, help='Activate secure mode'
    )
    # Verbose mode
    parser.add_argument(
        '-v', '--verbose', action='store_true', dest='verbose',
        default=DEFAULT_VERBOSE, help='Enable verbose mode'
    )
    # Path of intput topology file
    parser.add_argument(
        '-t', '--topo-file', dest='topo_file', action='store',
        required=True, default=DEFAULT_TOPOLOGY_FILE,
        help='Filename of the exported topology'
    )
    # Path of output VPN file
    parser.add_argument(
        '-f', '--vpn-file', dest='vpn_dump', action='store',
        default=None, help='Filename of the VPN dump'
    )
    # Server certificate file
    parser.add_argument(
        '-c', '--certificate', store='certificate', action='store',
        default=DEFAULT_CERTIFICATE, help='Server certificate file'
    )
    # Server key
    parser.add_argument(
        '-k', '--key', store='key', action='store',
        default=DEFAULT_KEY, help='Server key file'
    )
    # IP address of the gRPC server
    parser.add_argument(
        '-i', '--ip', store='grpc_server_ip', action='store',
        default=DEFAULT_GRPC_SERVER_IP, help='IP address of the gRPC server'
    )
    # Port of the gRPC server
    parser.add_argument(
        '-p', '--server-port', store='grpc_server_port', action='store',
        default=DEFAULT_GRPC_SERVER_PORT, help='Port of the gRPC server'
    )
    # Port of the gRPC client
    parser.add_argument(
        '-o', '--client-port', store='grpc_client_port', action='store',
        default=DEFAULT_GRPC_CLIENT_PORT, help='Port of the gRPC client'
    )
    # Southbound interface
    parser.add_argument(
        '-b', '--southbound', action='store',
        dest='southbound_interface', default=DEFAULT_SB_INTERFACE,
        help='Southbound interface\nSupported interfaces: [grpc]'
    )
    # Use management IPs instead of loopback IPs
    parser.add_argument(
        '-m', '--use-mgmt-ip', action='store_true',
        dest='use_mgmt_ip', default=DEFAULT_USE_MGMT_IP,
        help='Use management IPs instead of loopback IPs'
    )
    # Parse input parameters
    args = parser.parse_args()
    # Done, return
    return args


if __name__ == '__main__':
    # Parse options
    args = parse_arguments()
    # Setup properly the logger
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    # Debug settings
    SERVER_DEBUG = logger.getEffectiveLevel() == logging.DEBUG
    logger.info('SERVER_DEBUG:' + str(SERVER_DEBUG))
    # Input topology file
    topo_file = args.topo_file
    # Output VPN file
    vpn_dump = args.vpn_dump
    # Setup properly the secure mode
    if args.secure:
        secure = True
    else:
        secure = False
    # Server certificate file
    certificate = args.certificate
    # Server key
    key = args.key
    # IP of the gRPC server
    grpc_server_ip = args.grpc_server_ip
    # Port of the gRPC server
    grpc_server_port = args.grpc_server_port
    # Port of the gRPC client
    grpc_client_port = args.grpc_client_port
    # Southbound interface
    southbound_interface = args.southbound_interface
    # Use management IPs
    use_mgmt_ip = args.use_mgmt_ip
    # Setup properly the verbose mode
    if args.verbose:
        verbose = True
    else:
        verbose = False
    # Check southbound interface
    if southbound_interface not in SUPPORTED_SB_INTERFACES:
        # The southbound interface is invalid or not supported
        logger.warning(
            'Error: The %s interface is invalid or not yet supported\n'
            'Supported southbound interfaces: %s' % SUPPORTED_SB_INTERFACES
        )
        sys.exit(-2)
    # Wait until topology json file is ready
    while True:
        if os.path.isfile(topo_file):
            # The file is ready, we are ready to start server
            break
        # The file is not ready, wait for INTERVAL_CHECK_FILES seconds before
        # retrying
        print('Waiting for TOPOLOGY_FILE...')
        time.sleep(INTERVAL_CHECK_FILES)
    # Update the topology
    topo_graph = utils.load_topology_from_json_dump(topo_file)
    if topo_graph is not None:
        # Start server
        start_server(
            grpc_server_ip, grpc_server_port, grpc_client_port, secure, key,
            certificate, southbound_interface, topo_graph, None, vpn_dump,
            use_mgmt_ip, verbose
        )
        while True:
            time.sleep(5)
    else:
        print('Invalid topology')
