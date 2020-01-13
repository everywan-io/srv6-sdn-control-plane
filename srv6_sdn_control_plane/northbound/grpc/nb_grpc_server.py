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


# General imports
from __future__ import absolute_import, division, print_function
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
import itertools
# ipaddress dependencies
from ipaddress import IPv6Interface
# SRv6 dependencies
from srv6_sdn_proto import srv6_vpn_pb2_grpc
from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import inventory_service_pb2_grpc
from srv6_sdn_proto import inventory_service_pb2
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils
from srv6_sdn_control_plane.northbound.grpc import tunnel_utils
from srv6_sdn_control_plane.southbound.grpc import sb_grpc_client
from srv6_sdn_proto import status_codes_pb2

# Topology file
DEFAULT_TOPOLOGY_FILE = '/tmp/topology.json'
# VPN file
DEFAULT_VPN_DUMP = '/tmp/vpn.json'
# Use management IPs instead of loopback IPs
DEFAULT_USE_MGMT_IP = False


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
# Validate topology
VALIDATE_TOPO = False

# Status codes
STATUS_INTF_NOTASSIGNED = status_codes_pb2.STATUS_INTF_NOTASSIGNED
STATUS_INTF_NOTFOUND = status_codes_pb2.STATUS_INTF_NOTFOUND
STATUS_ROUTER_NOTFOUND = status_codes_pb2.STATUS_ROUTER_NOTFOUND
STATUS_SUCCESS = status_codes_pb2.STATUS_SUCCESS
STATUS_VPN_INVALID_IP = status_codes_pb2.STATUS_VPN_INVALID_IP
STATUS_VPN_INVALID_TYPE = status_codes_pb2.STATUS_VPN_INVALID_TYPE
STATUS_VPN_NAME_UNAVAILABLE = status_codes_pb2.STATUS_VPN_NAME_UNAVAILABLE
STATUS_VPN_INVALID_PREFIX = status_codes_pb2.STATUS_VPN_INVALID_PREFIX
STATUS_VPN_NOTFOUND = status_codes_pb2.STATUS_VPN_NOTFOUND
STATUS_VPN_INVALID_TENANTID = status_codes_pb2.STATUS_VPN_INVALID_TENANTID


class InventoryService(inventory_service_pb2_grpc.InventoryServiceServicer):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 srv6_manager=None,
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
        # SRv6 Manager
        self.srv6_manager = srv6_manager

    def ConfigureDevice(self, request, context):
        logger.debug('ConfigureDevice request received: %s' % request)
        logger.info('CreateVPN request received:\n%s', request)
        # Extract the configurations from the request message
        for device in request.configuration.devices:
            logger.info('Processing the configuration:\n%s' % device)
            # Parameters extraction
            #
            # Extract the device ID from the configuration
            device_id = device.id
            # Extract the device name from the configuration
            device_name = device.name
            # Extract the device description from the configuration
            device_description = device.description
            # Extract the device interfaces from the configuration
            interfaces = self.devices[device_id]['interfaces']
            for interface in device.interfaces:
                if interface.type != '':
                    interfaces[interface.name]['type'] = interface.type
                if interface.type == nb_grpc_utils.InterfaceType.WAN:
                    if len(interface.ipv4_addrs) > 0 or \
                            len(interface.ipv6_addrs) > 0:
                        logger.warning(
                            'Cannot set IP addrs for a WAN interface')
                    if len(interface.ipv4_subnets) > 0 or \
                            len(interface.ipv6_subnets) > 0:
                        logger.warning(
                            'Cannot set subnets for a WAN interface')
                else:
                    if len(interface.ipv4_addrs) > 0:
                        addrs = list()
                        nets = list()
                        for addr in interfaces[interface.name]['ipv4_addrs']:
                            addr = '%s/%s' % (addr['addr'], addr['netmask'])
                            addrs.append(addr)
                        response = self.srv6_manager.remove_many_ipaddr(
                            self.devices[device_id]['mgmtip'],
                            self.grpc_client_port, addrs=addrs,
                            device=interface.name, family=AF_UNSPEC
                        )
                        if response != STATUS_SUCCESS:
                            # If the operation has failed,
                            # report an error message
                            logger.warning(
                                'Cannot remove the public addresses '
                                'from the interface'
                            )
                            return status_codes_pb2.STATUS_INTERNAL_ERROR
                        interfaces[interface.name]['ipv4_addrs'] = list()
                        # Add IP address to the interface
                        for ipv4_addr in interface.ipv4_addrs:
                            ip_addr = '%s/%s' % (ipv4_addr.addr,
                                                 ipv4_addr.netmask)
                            response = self.srv6_manager.create_ipaddr(
                                self.devices[device_id]['mgmtip'],
                                self.grpc_client_port, ip_addr=ip_addr,
                                device=interface.name, family=AF_INET
                            )
                            if response != STATUS_SUCCESS:
                                # If the operation has failed,
                                # report an error message
                                logger.warning(
                                    'Cannot assign the private VPN IP address '
                                    'to the interface'
                                )
                                return status_codes_pb2.STATUS_INTERNAL_ERROR
                        interfaces[interface.name]['ipv4_addrs'].append({
                            'addr': ipv4_addr.addr,
                            'netmask': ipv4_addr.netmask,
                            'broadcast': ''
                        })
                    if len(interface.ipv6_addrs) > 0:
                        addrs = list()
                        nets = list()
                        for addr in interfaces[interface.name]['ipv6_addrs']:
                            addr = '%s/%s' % (addr['addr'], addr['netmask'])
                            addrs.append(addr)
                            nets.append(str(IPv6Interface(addr).network))
                        response = self.srv6_manager.remove_many_ipaddr(
                            self.devices[device_id]['mgmtip'],
                            self.grpc_client_port, addrs=addrs,
                            nets=nets, device=interface.name, family=AF_UNSPEC
                        )
                        if response != STATUS_SUCCESS:
                            # If the operation has failed,
                            # report an error message
                            logger.warning(
                                'Cannot remove the public addresses '
                                'from the interface'
                            )
                            return status_codes_pb2.STATUS_INTERNAL_ERROR
                        interfaces[interface.name]['ipv6_addrs'] = list()
                        # Add IP address to the interface
                        for ipv6_addr in interface.ipv6_addrs:
                            ip_addr = '%s/%s' % (ipv6_addr.addr,
                                                 ipv6_addr.netmask)
                            net = IPv6Interface(ip_addr).network.__str__()
                            response = self.srv6_manager.create_ipaddr(
                                self.devices[device_id]['mgmtip'],
                                self.grpc_client_port, ip_addr=ip_addr,
                                device=interface.name, net=net, family=AF_INET6
                            )
                            if response != STATUS_SUCCESS:
                                # If the operation has failed,
                                # report an error message
                                logger.warning(
                                    'Cannot assign the private VPN IP address '
                                    'to the interface'
                                )
                                return status_codes_pb2.STATUS_INTERNAL_ERROR
                            interfaces[interface.name]['ipv6_addrs'].append({
                                'addr': ipv6_addr.addr,
                                'netmask': ipv6_addr.netmask,
                                'broadcast': ''
                            })
                    for subnet in interface.ipv4_subnets:
                        interfaces[interface.name]['ipv4_subnets'].append(
                            subnet)
                    for subnet in interface.ipv6_subnets:
                        interfaces[interface.name]['ipv6_subnets'].append(
                            subnet)
            if device_name != '':
                self.devices[device_id]['name'] = device_name
            if device_description != '':
                self.devices[device_id]['description'] = device_description
            self.devices[device_id]['status'] = \
                nb_grpc_utils.DeviceStatus.RUNNING
        logger.info('The device configuration has been saved\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)

    def GetDeviceInformation(self, request, context):
        logger.debug('GetDeviceInformation request received')
        # Extract the device ids from the request
        ids = list()
        for id in request.ids:
            ids.append(id)
        # Create the response
        response = (inventory_service_pb2
                    .InventoryServiceReply(status=STATUS_SUCCESS))
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
                interface.ipv4_subnets.extend(ifinfo['ipv4_subnets'])
                interface.ipv6_subnets.extend(ifinfo['ipv6_subnets'])
                interface.type = ifinfo['type']
            mgmtip = device_info.get('mgmtip')
            status = device_info.get('status')
            name = device_info.get('name')
            description = device_info.get('description')
            if mgmtip is not None:
                device.mgmtip = mgmtip
            if status is not None:
                device.status = status
            if name is not None:
                device.name = name
            if description is not None:
                device.description = description
        # Return the response
        logger.debug('Sending response:\n%s' % response)
        return response

    def GetTopologyInformation(self, request, context):
        logger.debug('GetTopologyInformation request received')
        # Create the response
        response = (inventory_service_pb2
                    .InventoryServiceReply(status=STATUS_SUCCESS))
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
        # Create the response
        response = (inventory_service_pb2
                    .InventoryServiceReply(status=STATUS_SUCCESS))
        # Build the tunnels list
        for _tunnel in self.tunnels_dict.values():
            # Add a new tunnel to the tunnels list
            tunnel = response.tunnel_information.tunnels.add()
            # Set tunnel ID
            tunnel.id = _tunnel.id
            # Set name
            tunnel.name = _tunnel.vpn_name
            # Set type
            if _tunnel.vpn_type == nb_grpc_utils.VPNType.IPv4VPN:
                tunnel.type = 'IPv4VPN'
            elif _tunnel.vpn_type == nb_grpc_utils.VPNType.IPv6VPN:
                tunnel.type = 'IPv6VPN'
            else:
                print('Unrecognized type')
                exit(-1)
            tunnel.mode = _tunnel.tunnel_mode.name
            tunnel.tenantid = int(_tunnel.tenantid)
            for interface in _tunnel.interfaces:
                # Add a new interface to the VPN
                _interface = tunnel.interfaces.add()
                # Add router ID
                _interface.routerid = interface.routerid
                # Add interface name
                _interface.interface_name = interface.interface_name
        # Return the tunnels list
        logger.debug('Sending response:\n%s' % response)
        return response


class SRv6VPNManager(srv6_vpn_pb2_grpc.SRv6VPNServicer):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 srv6_manager=None,
                 southbound_interface=DEFAULT_SB_INTERFACE,
                 controller_state=None, verbose=DEFAULT_VERBOSE):
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # Southbound interface
        self.southbound_interface = southbound_interface
        # VPN dict
        self.vpn_dict = controller_state.vpns
        # SRv6 Manager
        self.srv6_manager = srv6_manager
        # Initialize controller state
        self.controller_state = controller_state
        # Initialize tunnel state
        self.tunnel_modes = tunnel_utils.TunnelState(grpc_client_port,
                                                     controller_state,
                                                     verbose).tunnel_modes
        for tunnel_mode in self.tunnel_modes:
            self.controller_state.add_tunnel_mode(tunnel_mode)

    """gRPC Server"""

    """Create a VPN from an intent received through the northbound interface"""

    def CreateVPN(self, request, context):
        logger.info('CreateVPN request received:\n%s', request)
        # Extract the intents from the request message
        for intent in request.intents:
            logger.info('Processing the intent:\n%s' % intent)
            # Parameters extraction
            #
            # Extract the VPN tenant ID from the intent
            tenantid = int(intent.tenantid)
            # Extract the VPN type from the intent
            vpn_type = int(intent.vpn_type)
            # Extract the VPN name from the intent
            vpn_name = intent.vpn_name
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Tunnel ID
            tunnel_id = vpn_name
            # Extract the interfaces
            interfaces = list()
            for interface in intent.interfaces:
                interfaces.append(nb_grpc_utils.Interface(
                    interface.routerid,
                    interface.interface_name
                ))
            # Extract tunnel type
            tunnel_mode = self.tunnel_modes[intent.tunnel]
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Parameters validation
            #
            # Validate the tenant ID
            logger.debug('Validating the tenant ID:\n%s' % tenantid)
            if not nb_grpc_utils.validate_tenantid(tenantid):
                logger.warning('Invalid tenant ID: %s' % tenantid)
                # If tenant ID is invalid, return an error message
                return (srv6_vpn_pb2
                        .SRv6VPNReply(status=STATUS_VPN_INVALID_TENANTID))
            # Validate the VPN type
            logger.debug('Validating the VPN type:\n%s' % vpn_type)
            if not nb_grpc_utils.validate_vpn_type(vpn_type):
                logger.warning('Invalid VPN type: %s' % vpn_type)
                # If the VPN type is invalid, return an error message
                return (srv6_vpn_pb2
                        .SRv6VPNReply(status=STATUS_VPN_INVALID_TYPE))
            # Let's check if the VPN does not exist
            logger.debug('Validating the VPN name:\n%s' % vpn_name)
            if self.controller_state.vpn_exists(vpn_name):
                logger.warning('VPN name %s is already in use' % vpn_name)
                # If the VPN already exists, return an error message
                return (srv6_vpn_pb2
                        .SRv6VPNReply(status=STATUS_VPN_NAME_UNAVAILABLE))
            # Validate the VPN interfaces included in the intent
            for interface in interfaces:
                logger.debug('Validating the interface:\n%s' % interface)
                # An interface is a tuple (routerid, interface_name)
                #
                # Extract the router ID
                routerid = interface.routerid
                # Extract the interface name
                interface_name = interface.interface_name
                # Topology validation
                if VALIDATE_TOPO:
                    # Let's check if the router exists
                    if not self.controller_state.router_exists(routerid):
                        logger.warning(
                            'The topology does not contain the router %s'
                            % routerid
                        )
                        # If the router does not exist, return an error message
                        return (srv6_vpn_pb2
                                .SRv6VPNReply(status=STATUS_ROUTER_NOTFOUND))
                    # Let's check if the interface exists
                    if not self.controller_state.interface_exists(
                            interface_name, routerid):
                        logger.warning('The interface does not exist')
                        # If the interface does not exists, return an error
                        # message
                        return (srv6_vpn_pb2
                                .SRv6VPNReply(status=STATUS_INTF_NOTFOUND))
            logger.info('All checks passed')
            # All checks passed
            #
            # Let's create the VPN
            # Create overlay daata structure
            tunnel_mode.init_overlay_data(vpn_name, tenantid, tunnel_info)
            for interface in interfaces:
                routerid = interface.routerid
                interface_name = interface.interface_name
                tunnel_name = tunnel_mode.name
                # Init tunnel mode on the devices
                if not (self.controller_state
                        .is_tunnel_mode_initiated_on_device(tunnel_name,
                                                            routerid)):
                    tunnel_mode.init_tunnel_mode(routerid, tunnel_info)
                    (self.controller_state
                     .init_tunnel_mode_on_device(tunnel_name, routerid))
                # Init overlay on the devices
                if not self.controller_state.is_overlay_initiated_on_device(
                        tunnel_name, routerid, vpn_name):
                    tunnel_mode.init_overlay(vpn_name, vpn_type,
                                             routerid, tunnel_info)
                    (self.controller_state
                     .init_overlay_on_device(tunnel_name,
                                             routerid,
                                             vpn_name))
                # Add the interface to the overlay
                (tunnel_mode
                 .add_slice_to_overlay(vpn_name, routerid,
                                       interface_name, tunnel_info))
                self.controller_state.add_interface_to_overlay(tunnel_name,
                                                               routerid,
                                                               vpn_name,
                                                               interface_name)
            # Create the tunnel between all the pairs of interfaces
            for site1, site2 in itertools.combinations(interfaces, 2):
                if site1.routerid != site2.routerid:
                    tunnel_mode.create_tunnel(vpn_name, vpn_type, site1,
                                              site2, tenantid, tunnel_info)
            # Add the VPN to the VPNs set
            self.controller_state.add_vpn(tunnel_id, vpn_name, vpn_type,
                                          interfaces, tenantid, tunnel_mode)
        # Save the VPNs dump to file
        if self.controller_state.vpn_file is not None:
            logger.info('Saving the VPN dump')
            self.controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)

    """Remove a VPN"""

    def RemoveVPN(self, request, context):
        logger.info('RemoveVPN request received:\n%s', request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the VPN tenant ID from the intent
            tenantid = intent.tenantid
            # Extract the VPN name from the intent
            vpn_name = str(intent.vpn_name)
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Parameters validation
            #
            # Let's check if the VPN exists
            logger.debug('Checking the VPN:\n%s' % vpn_name)
            if not self.controller_state.vpn_exists(vpn_name):
                logger.warning('The VPN %s does not exist' % vpn_name)
                # If the VPN already exists, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_VPN_NOTFOUND)
            logger.debug('Check passed')
            # All checks passed
            #
            # Get the overlay type
            vpn_type = self.controller_state.get_vpn_type(vpn_name)
            # Get the tunnel mode
            tunnel_mode = self.controller_state.vpns[vpn_name].tunnel_mode
            # Get the interfaces belonging to the VPN
            interfaces = self.controller_state.vpns[vpn_name].interfaces
            # Let's remove the VPN
            # Remove the tunnel between all the pairs of interfaces
            for site1, site2 in itertools.combinations(interfaces, 2):
                if site1.routerid != site2.routerid:
                    tunnel_mode.remove_tunnel(
                        vpn_name, vpn_type, site1,
                        site2, tenantid, tunnel_info)
            for interface in interfaces:
                routerid = interface.routerid
                interface_name = interface.interface_name
                tunnel_name = tunnel_mode.name
                # Remove the interface from the overlay
                tunnel_mode.remove_slice_from_overlay(vpn_name,
                                                      routerid,
                                                      interface_name,
                                                      tunnel_info)
                (self.controller_state
                 .remove_interface_from_overlay(tunnel_name,
                                                routerid,
                                                vpn_name,
                                                interface_name))
                # Destroy overlay on the devices
                if not (self.controller_state
                        .is_overlay_initiated_on_device(tunnel_name,
                                                        routerid,
                                                        vpn_name)):
                    tunnel_mode.destroy_overlay(vpn_name,
                                                vpn_type,
                                                routerid,
                                                tunnel_info)
                    (self.controller_state
                     .destroy_overlay_on_device(tunnel_name,
                                                routerid,
                                                vpn_name))
                # Destroy tunnel mode on the devices
                if not (self.controller_state
                        .is_tunnel_mode_initiated_on_device(tunnel_name,
                                                            routerid)):
                    tunnel_mode.destroy_tunnel_mode(routerid, tunnel_info)
                    (self.controller_state
                     .destroy_tunnel_mode_on_device(tunnel_name, routerid))
            # Destroy overlay data structure
            tunnel_mode.destroy_overlay_data(vpn_name, tenantid, tunnel_info)
        # Delete the VPN
        self.controller_state.remove_vpn(vpn_name)
        # Save the VPNs dump to file
        if self.controller_state.vpn_file is not None:
            logger.info('Saving the VPN dump')
            self.controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)

    """Assign an interface to a VPN"""

    def AssignInterfaceToVPN(self, request, context):
        logger.info('AssignInterfaceToVPN request received:\n%s' % request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the VPN tenant ID from the intent
            tenantid = int(intent.tenantid)
            # Extract the VPN name from the intent
            vpn_name = intent.vpn_name
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Extract the interfaces
            interfaces = list()
            for interface in intent.interfaces:
                interfaces.append(nb_grpc_utils.Interface(
                    interface.routerid,
                    interface.interface_name
                ))
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Parameters validation
            #
            # Let's check if the VPN exists
            logger.debug('Checking the VPN:\n%s' % vpn_name)
            # Iterate on the interfaces and extract the
            # interfaces to be assigned
            # to the VPN and validate them
            for interface in interfaces:
                logger.debug('Validating the interface:\n%s' % interface)
                # Get router ID
                routerid = interface.routerid
                # Get interface name
                interface_name = interface.interface_name
                # Topology validation
                if VALIDATE_TOPO:
                    # Let's check if the router ID exists
                    if not self.controller_state.router_exists(routerid):
                        # If the router ID does not exist,
                        # return an error message
                        logger.warning(
                            'The topology does not contain the router %s'
                            % routerid
                        )
                        return (srv6_vpn_pb2
                                .SRv6VPNReply(status=STATUS_ROUTER_NOTFOUND))
                    # Let's check if the interface exists
                    if not (self.controller_state
                            .interface_exists(interface_name, routerid)):
                        # If the interface does not exist, return an error
                        # message
                        logger.warning('The interface does not exist')
                        return (srv6_vpn_pb2
                                .SRv6VPNReply(status=STATUS_INTF_NOTFOUND))
                # Let's make sure that the interface is not assigned to another
                # VPN
                if (self.controller_state
                        .interface_in_any_vpn(routerid, interface_name)):
                    # If the interface is already assigned to a VPN, return an
                    # error message
                    logger.warning(
                        'The interface %s is already assigned to a VPN'
                        % interface_name
                    )
                    return srv6_vpn_pb2.SRv6VPNReply(
                        status=status_codes_pb2.STATUS_INTF_ALREADY_ASSIGNED)
            logger.info('All checks passed')
            # All checks passed
            #
            # TODO fix id
            tunnel_id = vpn_name
            # Get the overlay type
            vpn_type = self.controller_state.get_vpn_type(vpn_name)
            # Get the tunnel mode
            tunnel_mode = self.controller_state.vpns[vpn_name].tunnel_mode
            # Let's assign the interface to the VPN
            for interface in interfaces:
                routerid = interface.routerid
                interface_name = interface.interface_name
                tunnel_name = tunnel_mode.name
                # Init tunnel mode on the devices
                if not (self.controller_state
                        .is_tunnel_mode_initiated_on_device(tunnel_name,
                                                            routerid)):
                    tunnel_mode.init_tunnel_mode(routerid, tunnel_info)
                    self.controller_state.init_tunnel_mode_on_device(
                        tunnel_name, routerid)
                # Init overlay on the devices
                if not self.controller_state.is_overlay_initiated_on_device(
                        tunnel_name, routerid, vpn_name):
                    tunnel_mode.init_overlay(
                        vpn_name, vpn_type, routerid, tunnel_info)
                    self.controller_state.init_overlay_on_device(
                        tunnel_name, routerid, vpn_name)
                # Add the interface to the overlay
                tunnel_mode.add_slice_to_overlay(
                    vpn_name, routerid, interface_name, tunnel_info)
                self.controller_state.add_interface_to_overlay(
                    tunnel_name, routerid, vpn_name, interface_name)
            # Create the tunnel between all the pairs of interfaces
            for site1 in interfaces:
                for site2 in self.controller_state.get_interfaces_in_vpn(
                        vpn_name):
                    if site1.routerid != site2.routerid:
                        tunnel_mode.create_tunnel(
                            vpn_name, vpn_type, site1,
                            site2, tenantid, tunnel_info)
            # Add the interfaces to the VPN
            for interface in interfaces:
                self.controller_state.add_interface_to_vpn(
                    tunnel_id, vpn_name, interface)
            # Save the VPNs dump to file
            if self.controller_state.vpn_file is not None:
                logger.info('Saving the VPN dump')
                self.controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)

    """Remove an interface from a VPN"""

    def RemoveInterfaceFromVPN(self, request, context):
        logger.info('RemoveInterfaceFromVPN request received:\n%s' % request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the VPN tenant ID from the intent
            tenantid = intent.tenantid
            # Extract the VPN name from the intent
            vpn_name = str(intent.vpn_name)
            # Get the VPN full name (i.e. tenantid-vpn_name)
            vpn_name = '%s-%s' % (tenantid, vpn_name)
            # Extract the interfaces
            interfaces = list()
            for interface in intent.interfaces:
                interfaces.append(nb_grpc_utils.Interface(
                    interface.routerid,
                    interface.interface_name
                ))
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Parameters validation
            #
            # Let's check if the VPN exists
            if not self.controller_state.vpn_exists(vpn_name):
                logger.warning('The VPN %s does not exist' % vpn_name)
                # If the VPN already exists, return an error message
                return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_VPN_NOTFOUND)
            # Iterate on the interfaces
            # and extract the interfaces to be removed from the VPN
            for interface in intent.interfaces:
                logger.debug('Validating the interface:\n%s' % interface)
                # Get the router ID
                routerid = interface.routerid
                # Get the interface name
                interface_name = interface.interface_name
                # Topology validation
                if VALIDATE_TOPO:
                    # Let's check if the router ID exists
                    if not self.controller_state.router_exists(routerid):
                        # If the router ID does not exist,
                        # return an error message
                        logger.warning(
                            'The topology does not contain the router %s'
                            % routerid
                        )
                        return (srv6_vpn_pb2
                                .SRv6VPNReply(status=STATUS_ROUTER_NOTFOUND))
                    # Let's check if the interface exists
                    if not self.controller_state.interface_exists(
                            interface_name, routerid):
                        # The interface does not exist, return an error message
                        logger.warning('The interface does not exist')
                        return srv6_vpn_pb2.SRv6VPNReply(
                            status=STATUS_INTF_NOTFOUND)
                # Let's check if the interface is assigned to the given VPN
                if not self.controller_state.interface_in_vpn(routerid,
                                                              interface_name,
                                                              vpn_name):
                    # The interface is not assigned to the VPN, return an error
                    # message
                    logger.warning(
                        'The interface is not assigned to the VPN %s' %
                        vpn_name)
                    return srv6_vpn_pb2.SRv6VPNReply(
                        status=STATUS_INTF_NOTASSIGNED)
            # All checks passed
            #
            # Get the overlay type
            vpn_type = self.controller_state.get_vpn_type(vpn_name)
            # Get the tunnel mode
            tunnel_mode = self.controller_state.vpns[vpn_name].tunnel_mode
            # Get the interfaces belonging to the VPN
            interfaces = self.controller_state.vpns[vpn_name].interfaces
            # Let's remove the interface from the VPN
            # Remove the tunnel between all the pairs of interfaces
            for site1 in interfaces:
                for site2 in self.controller_state.get_interfaces_in_vpn(
                        vpn_name):
                    if site1.routerid != site2.routerid:
                        tunnel_mode.remove_tunnel(
                            vpn_name, vpn_type, site1,
                            site2, tenantid, tunnel_info)
            for interface in interfaces:
                routerid = interface.routerid
                interface_name = interface.interface_name
                tunnel_name = tunnel_mode.name
                # Remove the interface from the overlay
                tunnel_mode.remove_slice_from_overlay(
                    vpn_name, routerid, interface_name, tunnel_info)
                self.controller_state.remove_interface_from_overlay(
                    tunnel_name, routerid, vpn_name, interface_name)
                # Destroy overlay on the devices
                if not self.controller_state.is_overlay_initiated_on_device(
                        tunnel_name, routerid, vpn_name):
                    tunnel_mode.destroy_overlay(
                        vpn_name, vpn_type, routerid, tunnel_info)
                    self.controller_state.destroy_overlay_on_device(
                        tunnel_name, routerid, vpn_name)
                # Destroy tunnel mode on the devices
                if not (
                    self.controller_state .is_tunnel_mode_initiated_on_device(
                        tunnel_name,
                        routerid)):
                    tunnel_mode.destroy_tunnel_mode(routerid, tunnel_info)
                    (self.controller_state
                     .destroy_tunnel_mode_on_device(tunnel_name, routerid))
        # Delete the VPN
        for interface in interfaces:
            self.controller_state.remove_interface_from_vpn(
                vpn_name, interface)
        # Save the VPNs dump to file
        if self.controller_state.vpn_file is not None:
            logger.info('Saving the VPN dump')
            self.controller_state.save_vpns_dump()
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)

    # Get VPNs from the controller inventory
    def GetVPNs(self, request, context):
        logger.debug('GetVPNs request received')
        # Create the response
        response = srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)
        # Build the VPNs list
        for _vpn in self.controller_state.get_vpns():
            # Add a new VPN to the VPNs list
            vpn = response.vpns.add()
            # Set name
            vpn.vpn_name = _vpn.vpn_name
            # Set interfaces
            # Iterate on all interfaces
            for interface in _vpn.interfaces:
                # Add a new interface to the VPN
                _interface = vpn.interfaces.add()
                # Add router ID
                _interface.routerid = interface.routerid
                # Add interface name
                _interface.interface_name = interface.interface_name
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
                 verbose=DEFAULT_VERBOSE):
    # Initialize controller state
    controller_state = nb_grpc_utils.ControllerState(
        topology=topo_graph,
        devices=devices,
        vpn_dict=vpn_dict,
        vpn_file=vpn_file
    )
    # Create SRv6 Manager
    srv6_manager = sb_grpc_client.SRv6Manager()
    # Setup gRPC server
    #
    # Create the server and add the handler
    grpc_server = grpc.server(futures.ThreadPoolExecutor())
    srv6_vpn_pb2_grpc.add_SRv6VPNServicer_to_server(
        SRv6VPNManager(
            grpc_client_port, srv6_manager,
            southbound_interface, controller_state, verbose
        ), grpc_server
    )
    inventory_service_pb2_grpc.add_InventoryServiceServicer_to_server(
        InventoryService(
            grpc_client_port, srv6_manager,
            topo_graph, vpn_dict, devices, verbose
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
    topo_graph = nb_grpc_utils.load_topology_from_json_dump(topo_file)
    if topo_graph is not None:
        # Start server
        start_server(
            grpc_server_ip, grpc_server_port, grpc_client_port, secure, key,
            certificate, southbound_interface, topo_graph, None, vpn_dump,
            verbose
        )
        while True:
            time.sleep(5)
    else:
        print('Invalid topology')
