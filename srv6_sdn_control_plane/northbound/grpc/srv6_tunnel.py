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
from ipaddress import IPv6Interface, IPv4Interface
# SRv6 dependencies
from srv6_sdn_control_plane.northbound.grpc import tunnel_mode
from srv6_sdn_control_plane.northbound.grpc import srv6_tunnel_utils
from srv6_sdn_control_plane.southbound.grpc import sb_grpc_client
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils
from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import status_codes_pb2


# Global variables definition

# Default gRPC client port
DEFAULT_GRPC_CLIENT_PORT = 12345
# Verbose mode
DEFAULT_VERBOSE = False
# Logger reference
logger = logging.getLogger(__name__)


class SRv6Tunnel(tunnel_mode.TunnelMode):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 controller_state=None, verbose=DEFAULT_VERBOSE):
        # Name of the tunnel mode
        self.name = 'SRv6'
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # VPN dict
        self.vpn_dict = controller_state.vpns
        # Create SRv6 Manager
        self.srv6_manager = sb_grpc_client.SRv6Manager()
        # Initialize controller state
        self.controller_state = controller_state
        # Initialize controller state
        self.controller_state_srv6 = srv6_tunnel_utils.ControllerStateSRv6(controller_state)

    def init_tunnel(self, routerid, tunnel_name, tunnel_type, tenantid, is_first_tunnel, tunnel_info):
        # Initialize the tunnel
        #
        # Get a new table ID for the VPN
        tableid = self.controller_state_srv6.get_tableid(
            tunnel_name
        )
        if tableid == -1:
            # Table ID not yet assigned
            logger.debug('Attempting to get a new table ID for the VPN')
            tableid = self.controller_state_srv6.get_new_tableid(
                tunnel_name, tenantid
            )
        logger.debug('New table ID assigned to the VPN:%s', tableid)
        logger.debug('Validating the table ID:\n%s' % tableid)
        # Validate the table ID
        if not nb_grpc_utils.validate_table_id(tableid):
            logger.warning('Invalid table ID: %s' % tableid)
            # If the table ID is not valid, return an error message
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the router address
        router = self.controller_state.get_router_mgmtip(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # First step: create a rule for local SIDs processing
        # This step is just required for the first VPN
        if is_first_tunnel:
            # We are installing the first VPN in the router
            #
            # Get SID family for this router
            sid_family = self.controller_state_srv6.get_sid_family(
                routerid
            )
            if sid_family is None:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot get SID family for routerid %s' % routerid
                )
                return status_codes_pb2.STATUS_INTERNAL_ERROR
            # Add the rule to steer the SIDs through the local SID table
            response = self.srv6_manager.create_iprule(
                router, self.grpc_client_port, family=AF_INET6,
                table=nb_grpc_utils.LOCAL_SID_TABLE, destination=sid_family
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                logger.warning(
                    'Cannot create the IP rule for destination %s: %s'
                    % (sid_family, response)
                )
                # If the operation has failed, return an error message
                return status_codes_pb2.STATUS_INTERNAL_ERROR
            # Add a blackhole route to drop all unknown active segments
            response = self.srv6_manager.create_iproute(
                router, self.grpc_client_port, family=AF_INET6,
                type='blackhole', table=nb_grpc_utils.LOCAL_SID_TABLE
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                logger.warning(
                    'Cannot create the blackhole route: %s' % response
                )
                # If the operation has failed, return an error message
                return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Second step is the creation of the decapsulation and lookup route
        if tunnel_type == nb_grpc_utils.VPNType.IPv6VPN:
            # For IPv6 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT6 SRv6 action
            action = 'End.DT6'
        elif tunnel_type == nb_grpc_utils.VPNType.IPv4VPN:
            # For IPv4 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT4 SRv6 action
            action = 'End.DT4'
        else:
            logger.warning('Error: Unsupported VPN type: %s' % tunnel_type)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get an non-loopback interface
        # We use the management interface (which is the first interface)
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = self.controller_state.get_non_loopback_interface(routerid)
        if dev is None:
            # Cannot get non-loopback interface
            logger.warning('Cannot get non-loopback interface')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the SID
        logger.debug('Attempting to get a SID for the router')
        sid = self.controller_state_srv6.get_sid(routerid, tableid)
        logger.debug('Received SID %s' % sid)
        # Add the End.DT4 / End.DT6 route
        response = self.srv6_manager.create_srv6_local_processing_function(
            router, self.grpc_client_port, segment=sid, action=action,
            device=dev, localsid_table=nb_grpc_utils.LOCAL_SID_TABLE, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            logger.warning(
                'Cannot create the SRv6 Local Processing function: %s'
                % response
            )
            # The operation has failed, return an error message
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Third step is the creation of the VRF assigned to the VPN
        response = self.srv6_manager.create_vrf_device(
            router, self.grpc_client_port, name=tunnel_name, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            logger.warning(
                'Cannot create the VRF %s: %s' % (tunnel_name, response)
            )
            # If the operation has failed, return an error message
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        if tunnel_name not in self.controller_state_srv6.interfaces_in_vpn:
            self.controller_state_srv6.interfaces_in_vpn[tunnel_name] = set()
        if tunnel_name not in self.controller_state_srv6.sites_in_vpn:
            self.controller_state_srv6.sites_in_vpn[tunnel_name] = set()
        # Success
        logger.debug('The VPN has been successfully installed on the router')
        return status_codes_pb2.STATUS_SUCCESS

    def destroy_tunnel(self, routerid, tunnel_name, tunnel_type, tenantid, is_last_tunnel, tunnel_info):
        # Get the router address
        router = self.controller_state.get_router_mgmtip(routerid)
        if router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Extract params from the VPN
        #tableid = self.controller_state_srv6.get_vpn_tableid(tunnel_name)
        #if tableid is None:
        tableid = self.controller_state_srv6.get_tableid(tunnel_name)
        if tableid == -1:
            # If the operation has failed, return an error message
            logger.warning('Cannot get table ID for the VPN %s' % tunnel_name)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the SID
        sid = self.controller_state_srv6.get_sid(routerid, tableid)
        if sid is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get SID for routerid %s' % routerid)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Remove the decap and lookup function (i.e. the End.DT4 or End.DT6
        # route)
        response = self.srv6_manager.remove_srv6_local_processing_function(
            router, self.grpc_client_port, segment=sid,
            localsid_table=nb_grpc_utils.LOCAL_SID_TABLE
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove seg6local route: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Delete the VRF assigned to the VPN
        response = self.srv6_manager.remove_vrf_device(
            router, self.grpc_client_port, tunnel_name
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the VRF %s from the router %s: %s'
                % (tunnel_name, router, response)
            )
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Delete all remaining IPv6 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            router, self.grpc_client_port, family=AF_INET6, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the IPv6 route: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Delete all remaining IPv4 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            router, self.grpc_client_port, family=AF_INET, table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove IPv4 routes: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # If no more VPNs are installed on the router,
        # we can delete the rule for local SIDs
        if is_last_tunnel:
            # Get SID family for this router
            sid_family = self.controller_state_srv6.get_sid_family(routerid)
            if sid_family is None:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot get SID family for routerid %s' % routerid
                )
                return status_codes_pb2.STATUS_INTERNAL_ERROR
            # Remove rule for SIDs
            response = self.srv6_manager.remove_iprule(
                router, self.grpc_client_port, family=AF_INET6, table=nb_grpc_utils.LOCAL_SID_TABLE,
                destination=sid_family
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the localSID rule: %s' % response
                )
                return status_codes_pb2.STATUS_INTERNAL_ERROR
            # Remove blackhole route
            response = self.srv6_manager.remove_iproute(
                router, self.grpc_client_port, family=AF_INET6, type='blackhole',
                table=nb_grpc_utils.LOCAL_SID_TABLE
            )
            if response != status_codes_pb2.STATUS_SUCCESS:
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the blackhole rule: %s' % response
                )
                return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Successfully removed the VPN from the router')
        return status_codes_pb2.STATUS_SUCCESS

    def assign_src_interface_to_vrf(self, tunnel_name, tunnel_type, src_interface, tenantid, tunnel_info):
        # Configure the source interface
        #
        # Get router address
        src_router = self.controller_state.get_router_mgmtip(src_interface.routerid)
        if src_router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Set the address family depending on the VPN type
        if tunnel_type == nb_grpc_utils.VPNType.IPv6VPN:
            family = AF_INET6
        elif tunnel_type == nb_grpc_utils.VPNType.IPv4VPN:
            family = AF_INET
        else:
            logger.warning('Unsupported VPN type: %s' % tunnel_type)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Remove all IPv4 and IPv6 addresses
        ipv4_addrs = self.controller_state.get_interface_ipv4(
            src_interface.routerid, src_interface.interface_name
        )
        if ipv4_addrs is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get interface addresses')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        ipv6_addrs = self.controller_state.get_interface_ipv6(
            src_interface.routerid, src_interface.interface_name
        )
        if ipv6_addrs is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get interface addresses')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        addrs = list()
        nets = list()
        for addr in ipv4_addrs:
            addrs.append(addr)
            nets.append(str(IPv4Interface(addr).network))
        for addr in ipv6_addrs:
            addrs.append(addr)
            nets.append(str(IPv6Interface(addr).network))
        print('ADDRS', addrs, nets)
        response = self.srv6_manager.remove_many_ipaddr(
            src_router, self.grpc_client_port, addrs=addrs, nets=nets,
            device=src_interface.interface_name, family=AF_UNSPEC
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot remove the public addresses from the interface'
            )
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Don't advertise the private customer network
        response = self.srv6_manager.update_interface(
            src_router, self.grpc_client_port, name=src_interface.interface_name, ospf_adv=False
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot disable OSPF advertisements')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Add IP address to the interface
        response = self.srv6_manager.create_ipaddr(
            src_router, self.grpc_client_port, ip_addr=src_interface.interface_ip,
            device=src_interface.interface_name, net=src_interface.vpn_prefix, family=family
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot assign the private VPN IP address to the interface'
            )
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the interfaces assigned to the VPN
        interfaces_in_vpn = self.controller_state_srv6.controller_state.get_vpn_interface_names(
            tunnel_name, src_interface.routerid
        )
        if interfaces_in_vpn is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get VPN interfaces')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        interfaces_in_vpn.add(src_interface.interface_name)
        # Add the interface to the VRF
        print('Update VRF',src_router, interfaces_in_vpn)
        response = self.srv6_manager.update_vrf_device(
            src_router, self.grpc_client_port, name=tunnel_name,
            interfaces=interfaces_in_vpn
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot assign the interface to the VRF: %s' % response
            )
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Done
        return status_codes_pb2.STATUS_SUCCESS

    def remove_src_interface_from_vrf(self, tunnel_name, tunnel_type, src_interface, tenantid, tunnel_info):
        # Configure the source interface
        #
        # Get router address
        src_router = self.controller_state.get_router_mgmtip(src_interface.routerid)
        if src_router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Remove all the IPv4 and IPv6 addresses
        addr = self.controller_state.get_vpn_interface_ip(
            tunnel_name, src_interface.routerid, src_interface.interface_name
        )
        if addr is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get interface address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        net = str(IPv6Interface(addr).network)
        response = self.srv6_manager.remove_ipaddr(
            src_router, self.grpc_client_port, ip_addr=addr, net=net,
            device=src_interface.interface_name, family=AF_UNSPEC
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove address from the interface: %s' % response
            )
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Enable advertisements the private customer network
        response = self.srv6_manager.update_interface(
            src_router, self.grpc_client_port, name=src_interface.interface_name, ospf_adv=True
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot enable OSPF advertisements: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the interfaces assigned to the VPN
        interfaces_in_vpn = self.controller_state_srv6.controller_state.get_vpn_interface_names(
            tunnel_name, src_interface.routerid
        )
        if interfaces_in_vpn is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get VPN interfaces')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        interfaces_in_vpn.remove(src_interface.interface_name)
        # Remove the interface from the VRF
        response = self.srv6_manager.update_vrf_device(
            src_router, self.grpc_client_port, name=tunnel_name,
            interfaces=interfaces_in_vpn
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the VRF device: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Local interface removed successfully')
        # Done
        return status_codes_pb2.STATUS_SUCCESS

    def add_route_to_dst_interface(self, tunnel_name, tunnel_type,
                                    src_interface, dst_interface, tenantid, tunnel_info):
        # Configure the destination interface
        #
        # Get router address
        src_router = self.controller_state.get_router_mgmtip(src_interface.routerid)
        if src_router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Any non-loopback device
        # We use the management interface (which is the first interface)
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = self.controller_state.get_non_loopback_interface(src_interface.routerid)
        if dev is None:
            # Cannot get non-loopback interface
            logger.warning('Cannot get non-loopback interface')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the table ID
        #tableid = self.controller_state_srv6.get_vpn_tableid(tunnel_name)
        #if tableid is None:
        tableid = self.controller_state_srv6.get_tableid(tunnel_name)
        if tableid == -1:
            logger.warning('Cannot retrieve VPN table ID')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the SID
        sid = self.controller_state_srv6.get_sid(
            dst_interface.routerid, tableid
        )
        # Create the SRv6 route
        print('srv6 expl path', src_router, dst_interface.vpn_prefix, tableid, dev, sid)
        response = self.srv6_manager.create_srv6_explicit_path(
            src_router, self.grpc_client_port, destination=dst_interface.vpn_prefix,
            table=tableid, device=dev, segments=[sid], encapmode='encap'
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot create SRv6 Explicit Path: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Remote interface assigned to VPN successfully')
        # Done
        return status_codes_pb2.STATUS_SUCCESS

    def remove_route_to_dst_interface(self, tunnel_name, tunnel_type,
                                       src_interface, dst_interface, tenantid, tunnel_info):
        # Configure the destination interface
        #
        # Get router address
        src_router = self.controller_state.get_router_mgmtip(src_interface.routerid)
        if src_router is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Get the table ID
        #tableid = self.controller_state_srv6.get_vpn_tableid(tunnel_name)
        #if tableid is None:
        tableid = self.controller_state_srv6.get_tableid(tunnel_name)
        if tableid == -1:
            logger.warning('Cannot retrieve VPN table ID')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Remove the SRv6 route
        response = self.srv6_manager.remove_srv6_explicit_path(
            src_router, self.grpc_client_port, destination=dst_interface.vpn_prefix,
            table=tableid
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove SRv6 Explicit Path: %s' % response)
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Remote interface removed successfully')
        # Done
        return status_codes_pb2.STATUS_SUCCESS

    def create_tunnel(self, tunnel_name, tunnel_type,
                      l_interface, r_interface, tenantid, tunnel_info):
        logger.debug(
            'Attempting to create a tunnel %s between the interfaces %s and %s'
            % (tunnel_name, l_interface.interface_name, r_interface.interface_name)
        )
        # Tunnel from l_interface to r_interface
        #
        # Configure source tunnel interface
        if l_interface not in self.controller_state_srv6.interfaces_in_vpn[tunnel_name]:
            res = self.assign_src_interface_to_vrf(tunnel_name, tunnel_type,
                                                      l_interface, tenantid, tunnel_info)
            if res != status_codes_pb2.STATUS_SUCCESS:
                return res
            self.controller_state_srv6.interfaces_in_vpn[tunnel_name].add(l_interface)
        # Configure destination tunnel interface
        # If the interfaces are on the same router, we don't need the SRv6 encapsulation
        if r_interface not in self.controller_state_srv6.sites_in_vpn[tunnel_name]:
            if l_interface.routerid != r_interface.routerid:
                res = self.add_route_to_dst_interface(tunnel_name, tunnel_type, l_interface,
                                                      r_interface, tenantid, tunnel_info)
                if res != status_codes_pb2.STATUS_SUCCESS:
                    return res
                self.controller_state_srv6.sites_in_vpn[tunnel_name].add(r_interface)
        # Tunnel from r_interface to l_interface
        #
        # Configure source tunnel interface
        if r_interface not in self.controller_state_srv6.interfaces_in_vpn[tunnel_name]:
            res = self.assign_src_interface_to_vrf(tunnel_name, tunnel_type,
                                                      r_interface, tenantid, tunnel_info)
            if res != status_codes_pb2.STATUS_SUCCESS:
                print('test', 0)
                return res
            self.controller_state_srv6.interfaces_in_vpn[tunnel_name].add(r_interface)
        # Configure destination tunnel interface
        # If the interfaces are on the same router, we don't need the SRv6 encapsulation
        print('test', 1)
        if l_interface not in self.controller_state_srv6.sites_in_vpn[tunnel_name]:
            print('test', 2)
            if l_interface.routerid != r_interface.routerid:
                print('test', 3)
                self.add_route_to_dst_interface(tunnel_name, tunnel_type, r_interface,
                                                 l_interface, tenantid, tunnel_info)
                print('test', 4)
                if res != status_codes_pb2.STATUS_SUCCESS:
                    print('test', 5)
                    return res
                self.controller_state_srv6.sites_in_vpn[tunnel_name].add(l_interface)

    def remove_tunnel(self, tunnel_name, tunnel_type,
                      l_interface, r_interface, tenantid, tunnel_info):
        logger.debug(
            'Attempting to create a tunnel %s between the interfaces %s and %s'
            % (tunnel_name, l_interface.interface_name, r_interface.interface_name)
        )
        # Tunnel from l_interface to r_interface
        #
        # Configure source tunnel interface
        res = self.remove_src_interface_from_vrf(tunnel_name, tunnel_type,
                                                    l_interface, tenantid, tunnel_info)
        if res != status_codes_pb2.STATUS_SUCCESS:
            return res
        self.controller_state_srv6.interfaces_in_vpn[tunnel_name].remove(l_interface)
        # Configure destination tunnel interface
        # If the interfaces are on the same router, we don't need the SRv6 encapsulation
        if l_interface.routerid != r_interface.routerid:
            res = self.remove_route_to_dst_interface(tunnel_name, tunnel_type, l_interface,
                                                        r_interface, tenantid, tunnel_info)
            if res != status_codes_pb2.STATUS_SUCCESS:
                return res
            self.controller_state_srv6.sites_in_vpn[tunnel_name].remove(r_interface)
        # Tunnel from r_interface to l_interface
        #
        # Configure source tunnel interface
        res = self.remove_src_interface_from_vrf(tunnel_name, tunnel_type,
                                                    r_interface, tenantid, tunnel_info)
        if res != status_codes_pb2.STATUS_SUCCESS:
            return res
        self.controller_state_srv6.interfaces_in_vpn[tunnel_name].remove(r_interface)
        # Configure destination tunnel interface
        # If the interfaces are on the same router, we don't need the SRv6 encapsulation
        if l_interface.routerid != r_interface.routerid:
            res = self.remove_route_to_dst_interface(tunnel_name, tunnel_type, r_interface,
                                                        l_interface, tenantid, tunnel_info)
            if res != status_codes_pb2.STATUS_SUCCESS:
                return res
            self.controller_state_srv6.sites_in_vpn[tunnel_name].remove(l_interface)

    def get_tunnels(self):
        # Create the response
        response = srv6_vpn_pb2.SRv6VPNReply(status=status_codes_pb2.STATUS_SUCCESS)
        # Build the VPNs list
        for _vpn in self.controller_state_srv6.controller_state.get_vpns():
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
