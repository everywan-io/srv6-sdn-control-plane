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
import logging
from socket import AF_INET
from socket import AF_INET6
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

# Status codes
STATUS_SUCCESS = status_codes_pb2.STATUS_SUCCESS
STATUS_INTERNAL_ERROR = status_codes_pb2.STATUS_INTERNAL_ERROR
STATUS_UNREACHABLE_OSPF6D = status_codes_pb2.STATUS_UNREACHABLE_OSPF6D


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
        self.controller_state_srv6 = \
            srv6_tunnel_utils.ControllerStateSRv6(controller_state)

    def _create_tunnel_uni(self, overlay_name, overlay_type,
                           l_slice, r_slice, tenantid, overlay_info):
        logger.debug('Attempting to create unidirectional tunnel '
                     'from %s to %s' % (l_slice.interface_name,
                                        r_slice.interface_name))
        # Check if the unidirectional tunnel
        # between the two slices already exists
        if self.controller_state_srv6.num_tunnels.get((l_slice.routerid,
                                                       r_slice)) is None:
            self.controller_state_srv6.num_tunnels[(
                l_slice.routerid, r_slice)] = 0
        # Increase the number of tunnels
        self.controller_state_srv6.num_tunnels[(
            l_slice.routerid, r_slice)] += 1
        # If the uni tunnel already exists, we have done
        if self.controller_state_srv6.num_tunnels[(l_slice.routerid,
                                                   r_slice)] > 1:
            logger.debug('Skip tunnel %s %s' %
                         (l_slice.interface_name, r_slice.interface_name))
            return STATUS_SUCCESS
        # Configure the tunnel
        #
        # Get router address
        l_deviceip = (self.controller_state
                      .get_router_mgmtip(l_slice.routerid))
        if l_deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Any non-loopback device
        # We use the WAN interface
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = (self.controller_state
               .get_wan_interface(l_slice.routerid))
        if dev is None:
            # Cannot get wan interface
            logger.warning('Cannot get WAN interface')
            return STATUS_INTERNAL_ERROR
        # Get the table ID
        tableid = self.controller_state_srv6.get_tableid(overlay_name, tenantid)
        if tableid == -1:
            logger.warning('Cannot retrieve VPN table ID')
            return STATUS_INTERNAL_ERROR
        # Get the SID
        sid = self.controller_state_srv6.get_sid(
            r_slice.routerid, tableid
        )
        # Get the subnets
        if overlay_type == nb_grpc_utils.VPNType.IPv6VPN:
            subnets = self.controller_state.get_ipv6_subnets_on_interface(
                r_slice.routerid, r_slice.interface_name)
        elif overlay_type == nb_grpc_utils.VPNType.IPv4VPN:
            subnets = self.controller_state.get_ipv4_subnets_on_interface(
                r_slice.routerid, r_slice.interface_name)
        else:
            logger.warning('Error: Unsupported VPN type: %s' % overlay_type)
            return STATUS_INTERNAL_ERROR
        # Create the SRv6 route
        for subnet in subnets:
            response = self.srv6_manager.create_srv6_explicit_path(
                l_deviceip, self.grpc_client_port, destination=subnet,
                table=tableid, device=dev, segments=[sid], encapmode='encap'
            )
            if response != STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot create SRv6 Explicit Path: %s'
                               % response)
                return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Remote interface assigned to VPN successfully')
        return STATUS_SUCCESS

    def _remove_tunnel_uni(self, overlay_name, overlay_type,
                           l_slice, r_slice, tenantid, overlay_info):
        # Decrease the number of tunnels
        self.controller_state_srv6.num_tunnels[(
            l_slice.routerid, r_slice)] -= 1
        # Check if there are other unidirectional tunnels
        # between the two slices
        # If the uni tunnel already exists, we have done
        if self.controller_state_srv6.num_tunnels.get(
                (l_slice.routerid, r_slice)) > 0:
            return STATUS_SUCCESS
        del self.controller_state_srv6.num_tunnels[(l_slice.routerid, r_slice)]
        # Remove the tunnel
        #
        # Get router address
        l_deviceip = self.controller_state.get_router_mgmtip(l_slice.routerid)
        if l_deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Get the table ID
        tableid = self.controller_state_srv6.get_tableid(overlay_name, tenantid)
        if tableid == -1:
            logger.warning('Cannot retrieve VPN table ID')
            return STATUS_INTERNAL_ERROR
        # Get the subnets
        if overlay_type == nb_grpc_utils.VPNType.IPv6VPN:
            subnets = self.controller_state.get_ipv6_subnets_on_interface(
                r_slice.routerid, r_slice.interface_name)
        elif overlay_type == nb_grpc_utils.VPNType.IPv4VPN:
            subnets = self.controller_state.get_ipv4_subnets_on_interface(
                r_slice.routerid, r_slice.interface_name)
        else:
            logger.warning('Error: Unsupported VPN type: %s' % overlay_type)
            return STATUS_INTERNAL_ERROR
        # Remove the SRv6 route
        for subnet in subnets:
            response = self.srv6_manager.remove_srv6_explicit_path(
                l_deviceip, self.grpc_client_port, destination=subnet,
                table=tableid
            )
            if response != STATUS_SUCCESS:
                # If the operation has failed, return an error message
                logger.warning('Cannot remove SRv6 Explicit Path: %s'
                               % response)
                return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Remove unidirectional tunnel completed')
        return STATUS_SUCCESS

    def init_overlay_data(self, overlay_name, tenantid, overlay_info):
        logger.debug('Initiating overlay data for the overlay %s'
                     % overlay_name)
        # Initialize the overlay data structure
        #
        # Get a new table ID for the overlay
        logger.debug('Attempting to get a new table ID for the VPN')
        tableid = self.controller_state_srv6.get_new_tableid(
            overlay_name, tenantid
        )
        logger.debug('New table ID assigned to the VPN:%s', tableid)
        logger.debug('Validating the table ID:\n%s' % tableid)
        # Validate the table ID
        if not nb_grpc_utils.validate_table_id(tableid):
            logger.warning('Invalid table ID: %s' % tableid)
            # If the table ID is not valid, return an error message
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Init overlay data completed for the overlay %s'
                     % overlay_name)
        return STATUS_SUCCESS

    def init_tunnel_mode(self, deviceid, overlay_info):
        logger.debug('Initiating tunnel mode on router %s'
                     % deviceid)
        # Initialize the tunnel mode on the router
        #
        # Get the router address
        deviceip = self.controller_state.get_router_mgmtip(deviceid)
        if deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # First step: create a rule for local SIDs processing
        # This step is just required for the first VPN
        #
        # Get SID family for this router
        sid_family = self.controller_state_srv6.get_sid_family(
            deviceid
        )
        if sid_family is None:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot get SID family for routerid %s' % deviceid
            )
            return STATUS_INTERNAL_ERROR
        # Add the rule to steer the SIDs through the local SID table
        response = self.srv6_manager.create_iprule(
            deviceip, self.grpc_client_port, family=AF_INET6,
            table=nb_grpc_utils.LOCAL_SID_TABLE, destination=sid_family
        )
        if response != STATUS_SUCCESS:
            logger.warning(
                'Cannot create the IP rule for destination %s: %s'
                % (sid_family, response)
            )
            # If the operation has failed, return an error message
            return STATUS_INTERNAL_ERROR
        # Add a blackhole route to drop all unknown active segments
        response = self.srv6_manager.create_iproute(
            deviceip, self.grpc_client_port, family=AF_INET6,
            type='blackhole', table=nb_grpc_utils.LOCAL_SID_TABLE
        )
        if response != STATUS_SUCCESS:
            logger.warning(
                'Cannot create the blackhole route: %s' % response
            )
            # If the operation has failed, return an error message
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Init tunnel mode on device %s completed'
                     % deviceid)
        return STATUS_SUCCESS

    def init_overlay(self, overlay_name, overlay_type, tenantid, deviceid, overlay_info):
        logger.debug('Initiating overlay %s on the device %s'
                     % (overlay_name, deviceid))
        # Get the router address
        deviceip = self.controller_state.get_router_mgmtip(deviceid)
        if deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Second step is the creation of the decapsulation and lookup route
        if overlay_type == nb_grpc_utils.VPNType.IPv6VPN:
            # For IPv6 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT6 SRv6 action
            action = 'End.DT6'
        elif overlay_type == nb_grpc_utils.VPNType.IPv4VPN:
            # For IPv4 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT4 SRv6 action
            action = 'End.DT4'
        else:
            logger.warning('Error: Unsupported VPN type: %s' % overlay_type)
            return STATUS_INTERNAL_ERROR
        # Get the table ID for the VPN
        logger.debug('Attempting to retrieve the table ID assigned to the VPN')
        tableid = self.controller_state_srv6.get_tableid(
            overlay_name, tenantid
        )
        if tableid == -1:
            # Table ID not yet assigned
            logger.debug('Cannot get table ID')
            return STATUS_INTERNAL_ERROR
        logger.debug('Received table ID:%s', tableid)
        # Get a WAN interface
        # We use the WAN interface
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = self.controller_state.get_wan_interface(deviceid)
        if dev is None:
            # Cannot get non-loopback interface
            logger.warning('Cannot get non-loopback interface')
            return STATUS_INTERNAL_ERROR
        # Get the SID
        logger.debug('Attempting to get a SID for the router')
        sid = self.controller_state_srv6.get_sid(deviceid, tableid)
        logger.debug('Received SID %s' % sid)
        # Add the End.DT4 / End.DT6 route
        response = self.srv6_manager.create_srv6_local_processing_function(
            deviceip, self.grpc_client_port, segment=sid,
            action=action, device=dev,
            localsid_table=nb_grpc_utils.LOCAL_SID_TABLE, table=tableid
        )
        if response != STATUS_SUCCESS:
            logger.warning(
                'Cannot create the SRv6 Local Processing function: %s'
                % response
            )
            # The operation has failed, return an error message
            return STATUS_INTERNAL_ERROR
        # Third step is the creation of the VRF assigned to the VPN
        response = self.srv6_manager.create_vrf_device(
            deviceip, self.grpc_client_port, name=overlay_name, table=tableid
        )
        if response != STATUS_SUCCESS:
            logger.warning(
                'Cannot create the VRF %s: %s' % (overlay_name, response)
            )
            # If the operation has failed, return an error message
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Init overlay completed for the overlay %s and the '
                     'deviceid %s' % (overlay_name, deviceid))
        return STATUS_SUCCESS

    def add_slice_to_overlay(self, overlay_name,
                             deviceid, interface_name, overlay_info):
        logger.debug('Attempting to add the slice %s from the router %s '
                     'to the overlay %s'
                     % (interface_name, deviceid, overlay_name))
        # Get router address
        deviceip = self.controller_state.get_router_mgmtip(deviceid)
        if deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Don't advertise the private customer network
        response = self.srv6_manager.update_interface(
            deviceip, self.grpc_client_port,
            name=interface_name, ospf_adv=False
        )
        if response == STATUS_UNREACHABLE_OSPF6D:
            # If the operation has failed, report an error message
            logger.warning('Cannot disable OSPF advertisements: '
                           'ospf6d not running')
        elif response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot disable OSPF advertisements')
            return STATUS_INTERNAL_ERROR
        # Add the interface to the VRF
        response = self.srv6_manager.update_vrf_device(
            deviceip, self.grpc_client_port, name=overlay_name,
            interfaces=[interface_name],
            op='add_interfaces'
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning(
                'Cannot assign the interface to the VRF: %s' % response
            )
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Add slice to overlay completed')
        return STATUS_SUCCESS

    def create_tunnel(self, overlay_name, overlay_type,
                      l_slice, r_slice, tenantid, overlay_info):
        logger.debug(
            'Attempting to create a tunnel %s between the interfaces %s and %s'
            % (overlay_name, l_slice.interface_name, r_slice.interface_name)
        )
        # Tunnel from l_slice to r_slice
        res = self._create_tunnel_uni(overlay_name,
                                      overlay_type,
                                      l_slice,
                                      r_slice,
                                      tenantid,
                                      overlay_info)
        if res != STATUS_SUCCESS:
            return res
        # Tunnel from r_slice to l_slice
        res = self._create_tunnel_uni(overlay_name,
                                      overlay_type,
                                      r_slice, l_slice,
                                      tenantid,
                                      overlay_info)
        if res != STATUS_SUCCESS:
            return res
        # Success
        logger.debug('Tunnel creation completed')
        return STATUS_SUCCESS

    def destroy_overlay_data(self, overlay_name,
                             overlay_type, tenantid, overlay_info):
        logger.debug('Trying to destroy the overlay data structure')
        # Release the table ID
        res = self.controller_state.release_tableid(overlay_name, tenantid)
        if res == -1:
            logger.debug('Cannot release the table ID')
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Destroy overlay data completed')
        return STATUS_SUCCESS

    def destroy_tunnel_mode(self, deviceid, overlay_info):
        logger.debug('Trying to destroy the tunnel mode on the '
                     'router %s' % deviceid)
        # Get router address
        deviceip = self.controller_state.get_router_mgmtip(deviceid)
        if deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Get SID family for this router
        sid_family = self.controller_state_srv6.get_sid_family(deviceid)
        if sid_family is None:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot get SID family for deviceid %s' % deviceid
            )
            return STATUS_INTERNAL_ERROR
        # Remove rule for SIDs
        response = self.srv6_manager.remove_iprule(
            deviceip, self.grpc_client_port, family=AF_INET6,
            table=nb_grpc_utils.LOCAL_SID_TABLE,
            destination=sid_family
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the localSID rule: %s' % response
            )
            return STATUS_INTERNAL_ERROR
        # Remove blackhole route
        response = self.srv6_manager.remove_iproute(
            deviceip, self.grpc_client_port, family=AF_INET6, type='blackhole',
            table=nb_grpc_utils.LOCAL_SID_TABLE
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the blackhole rule: %s' % response
            )
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Destroy tunnel mode completed')
        return STATUS_SUCCESS

    def destroy_overlay(self, overlay_name, tenantid, deviceid, overlay_info):
        logger.debug('Tryingto destroy the overlay %s on device %s'
                     % (overlay_name, deviceid))
        # Get the router address
        deviceip = self.controller_state.get_router_mgmtip(deviceid)
        if deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Extract params from the VPN
        tableid = self.controller_state_srv6.get_tableid(overlay_name, tenantid)
        if tableid == -1:
            # If the operation has failed, return an error message
            logger.warning('Cannot get table ID for the VPN %s' % overlay_name)
            return STATUS_INTERNAL_ERROR
        # Get the SID
        sid = self.controller_state_srv6.get_sid(deviceid, tableid)
        if sid is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get SID for deviceid %s' % deviceid)
            return STATUS_INTERNAL_ERROR
        # Remove the decap and lookup function (i.e. the End.DT4 or End.DT6
        # route)
        response = self.srv6_manager.remove_srv6_local_processing_function(
            deviceip, self.grpc_client_port, segment=sid,
            localsid_table=nb_grpc_utils.LOCAL_SID_TABLE
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove seg6local route: %s' % response)
            return STATUS_INTERNAL_ERROR
        # Delete the VRF assigned to the VPN
        response = self.srv6_manager.remove_vrf_device(
            deviceip, self.grpc_client_port, overlay_name
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the VRF %s from the router %s: %s'
                % (overlay_name, deviceid, response)
            )
            return STATUS_INTERNAL_ERROR
        # Delete all remaining IPv6 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            deviceip, self.grpc_client_port, family=AF_INET6, table=tableid
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the IPv6 route: %s' % response)
            return STATUS_INTERNAL_ERROR
        # Delete all remaining IPv4 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            deviceip, self.grpc_client_port, family=AF_INET, table=tableid
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove IPv4 routes: %s' % response)
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Destroy overlay completed')
        return STATUS_SUCCESS

    def remove_slice_from_overlay(self, overlay_name,
                                  deviceid, interface_name, overlay_info):
        logger.debug('Trying to remove the slice %s on device %s '
                     'from the overlay %s'
                     % (interface_name, deviceid, overlay_name))
        # Get router address
        deviceip = self.controller_state.get_router_mgmtip(deviceid)
        if deviceip is None:
            # Cannot get the router address
            logger.warning('Cannot get the router address')
            return STATUS_INTERNAL_ERROR
        # Enable advertisements the private customer network
        response = self.srv6_manager.update_interface(
            deviceip, self.grpc_client_port,
            name=interface_name, ospf_adv=True
        )
        if response == STATUS_UNREACHABLE_OSPF6D:
            # If the operation has failed, report an error message
            logger.warning('Cannot disable OSPF advertisements: '
                           'ospf6d not running')
        elif response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot enable OSPF advertisements: %s' % response)
            return STATUS_INTERNAL_ERROR
        # Remove the interface from the VRF
        response = self.srv6_manager.update_vrf_device(
            deviceip, self.grpc_client_port, name=overlay_name,
            interfaces=[interface_name],
            op='del_interfaces'
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning('Cannot remove the VRF device: %s' % response)
            return STATUS_INTERNAL_ERROR
        # Success
        logger.debug('Remove slice from overlay completed')
        return STATUS_SUCCESS

    def remove_tunnel(self, overlay_name, overlay_type,
                      l_slice, r_slice, tenantid, overlay_info):
        logger.debug(
            'Attempting to remove the tunnel %s between the interfaces '
            '%s and %s' % (overlay_name,
                           l_slice.interface_name, r_slice.interface_name)
        )
        # Tunnel from l_slice to r_slice
        res = self._remove_tunnel_uni(overlay_name,
                                      overlay_type,
                                      l_slice,
                                      r_slice,
                                      tenantid,
                                      overlay_info)
        if res != STATUS_SUCCESS:
            return res
        # Tunnel from r_slice to l_slice
        res = self._remove_tunnel_uni(overlay_name,
                                      overlay_type,
                                      r_slice,
                                      l_slice,
                                      tenantid,
                                      overlay_info)
        if res != STATUS_SUCCESS:
            return res
        # Success
        logger.debug('Remove tunnel completed')
        return STATUS_SUCCESS

    def get_overlays(self):
        # Create the response
        response = srv6_vpn_pb2.SRv6VPNReply(status=STATUS_SUCCESS)
        # Build the VPNs list
        for _vpn in self.controller_state_srv6.controller_state.get_vpns():
            # Add a new VPN to the VPNs list
            vpn = response.vpns.add()
            # Set name
            vpn.overlay_name = _vpn.overlay_name
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
                    _interface.subnets = interface.subnets
        # Return the VPNs list
        logger.debug('Sending response:\n%s' % response)
        return response
