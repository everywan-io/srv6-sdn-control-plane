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
from srv6_sdn_control_plane import srv6_controller_utils
from srv6_sdn_control_plane.srv6_controller_utils import OverlayType
from srv6_sdn_proto.status_codes_pb2 import NbStatusCode, SbStatusCode
from srv6_sdn_controller_state import srv6_sdn_controller_state

# Global variables definition

# Default gRPC client port
DEFAULT_GRPC_CLIENT_PORT = 12345
# Verbose mode
DEFAULT_VERBOSE = False
# Logger reference
logger = logging.getLogger(__name__)


class SRv6Tunnel(tunnel_mode.TunnelMode):
    """gRPC request handler"""

    def __init__(self, srv6_manager,
                 grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 controller_state=None, verbose=DEFAULT_VERBOSE):
        # Name of the tunnel mode
        self.name = 'SRv6'
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # VPN dict
        self.vpn_dict = None
        # Create SRv6 Manager
        self.srv6_manager = srv6_manager
        # Initialize controller state
        self.controller_state_srv6 = \
            srv6_tunnel_utils.ControllerStateSRv6(controller_state)

    def _create_tunnel_uni(self, overlayid, overlay_name, overlay_type,
                           l_slice, r_slice, tenantid, overlay_info):
        logging.debug('Attempting to create unidirectional tunnel '
                      'from %s to %s' % (l_slice['interface_name'],
                                         r_slice['interface_name']))
        # Check if the unidirectional tunnel
        # between the two slices already exists
        #
        # Increase the number of tunnels
        num_tunnels = srv6_sdn_controller_state.inc_and_get_tunnels_counter(
            overlayid, tenantid, l_slice['deviceid'], r_slice)
        # If the uni tunnel already exists, we have done
        if num_tunnels > 1:
            logging.debug('Skip tunnel %s %s' %
                          (l_slice['interface_name'],
                           r_slice['interface_name']))
            return NbStatusCode.STATUS_OK
        # Configure the tunnel
        #
        # Get router address
        l_deviceip = (srv6_sdn_controller_state
                      .get_device_address(l_slice['deviceid'], tenantid))
        if l_deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Any non-loopback device
        # We use the WAN interface
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = (srv6_sdn_controller_state
               .get_wan_interfaces(l_slice['deviceid'], tenantid))
        if dev is None:
            # Cannot get wan interface
            logging.warning('Cannot get WAN interface')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        if len(dev) == 0:
            # Cannot get wan interface
            logging.warning('Cannot get WAN interface. No WAN interfaces')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        dev = dev[0]
        # Get the table ID
        tableid = srv6_sdn_controller_state.get_tableid(
            overlayid, tenantid)
        if tableid is None:
            logging.warning('Cannot retrieve VPN table ID')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the SID
        sid = self.controller_state_srv6.get_sid(
            r_slice['deviceid'], tenantid, tableid
        )
        # Get the subnets
        if overlay_type == OverlayType.IPv6Overlay:
            subnets = srv6_sdn_controller_state.get_ipv6_subnets(
                r_slice['deviceid'], tenantid, r_slice['interface_name'])
        elif overlay_type == OverlayType.IPv4Overlay:
            subnets = srv6_sdn_controller_state.get_ipv4_subnets(
                r_slice['deviceid'], tenantid, r_slice['interface_name'])
        else:
            logging.warning('Error: Unsupported VPN type: %s' % overlay_type)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get a WAN interface from the destination device
        wan_intf = (srv6_sdn_controller_state
                    .get_wan_interfaces(r_slice['deviceid'], tenantid))[0]
        # Get IP address of the WAN interface
        wan_ip_addrs = srv6_sdn_controller_state.get_ext_ipv6_addresses(
            r_slice['deviceid'], tenantid, wan_intf)
        if wan_ip_addrs is None:
            logging.error('Cannot get external IP address of the '
                          'WAN interface')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Build SID list used for the outgoing packets
        wan_ip_addr = wan_ip_addrs[0]
        sid_list = [sid, wan_ip_addr]
        # Get SEG6 encap mode
        if overlay_type == srv6_controller_utils.OverlayType.L2Overlay:
            # L2 encapsulation
            encapmode = 'l2encap'
        elif overlay_type in [srv6_controller_utils.OverlayType.IPv4Overlay,
                              srv6_controller_utils.OverlayType.IPv6Overlay]:
            # L3 encapsulation
            encapmode = 'encap'
        else:
            logger.error('Unrecognized overlay type: %s' % overlay_type)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Create the SRv6 route
        for subnet in subnets:
            subnet = subnet['subnet']
            response = self.srv6_manager.create_srv6_explicit_path(
                l_deviceip, self.grpc_client_port,
                destination=subnet, table=tableid, device=dev,
                segments=sid_list, encapmode=encapmode
            )
            if response != SbStatusCode.STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logging.warning('Cannot create SRv6 Explicit Path: %s'
                                % response)
                return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Remote interface assigned to VPN successfully')
        return NbStatusCode.STATUS_OK

    def _remove_tunnel_uni(self, overlayid, overlay_name, overlay_type,
                           l_slice, r_slice, tenantid, overlay_info):
        # Decrease the number of tunnels
        num_tunnels = srv6_sdn_controller_state.dec_and_get_tunnels_counter(
            overlayid, tenantid, l_slice['deviceid'], r_slice)
        # Check if there are other unidirectional tunnels
        # between the two slices
        # If the uni tunnel already exists, we have done
        if num_tunnels > 0:
            return NbStatusCode.STATUS_OK
        # Remove the tunnel
        #
        # Get router address
        l_deviceip = srv6_sdn_controller_state.get_device_address(
            l_slice['deviceid'], tenantid)
        if l_deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the table ID
        tableid = srv6_sdn_controller_state.get_tableid(
            overlayid, tenantid)
        if tableid is None:
            logging.warning('Cannot retrieve VPN table ID')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the subnets
        if overlay_type == OverlayType.IPv6Overlay:
            subnets = srv6_sdn_controller_state.get_ipv6_subnets(
                r_slice['deviceid'], tenantid, r_slice['interface_name'])
        elif overlay_type == OverlayType.IPv4Overlay:
            subnets = srv6_sdn_controller_state.get_ipv4_subnets(
                r_slice['deviceid'], tenantid, r_slice['interface_name'])
        else:
            logging.warning('Error: Unsupported VPN type: %s' % overlay_type)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Remove the SRv6 route
        for subnet in subnets:
            subnet = subnet['subnet']
            response = self.srv6_manager.remove_srv6_explicit_path(
                l_deviceip, self.grpc_client_port, destination=subnet,
                table=tableid
            )
            if response != SbStatusCode.STATUS_SUCCESS:
                # If the operation has failed, return an error message
                logging.warning('Cannot remove SRv6 Explicit Path: %s'
                                % response)
                return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Remove unidirectional tunnel completed')
        return NbStatusCode.STATUS_OK

    def init_overlay_data(self, overlayid,
                          overlay_name, tenantid, overlay_info):
        logging.debug('Initiating overlay data for the overlay %s'
                      % overlay_name)
        # Initialize the overlay data structure
        #
        # Get a new table ID for the overlay
        logging.debug('Attempting to get a new table ID for the VPN')
        tableid = srv6_sdn_controller_state.get_new_tableid(
            overlayid, tenantid
        )
        logging.debug('New table ID assigned to the VPN: %s', tableid)
        logging.debug('Validating the table ID: %s' % tableid)
        # Validate the table ID
        if not srv6_controller_utils.validate_table_id(tableid):
            logging.warning('Invalid table ID: %s' % tableid)
            # If the table ID is not valid, return an error message
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Init overlay data completed for the overlay %s'
                      % overlay_name)
        return NbStatusCode.STATUS_OK

    def init_tunnel_mode(self, deviceid, tenantid, overlay_info):
        logging.debug('Initiating tunnel mode on router %s'
                      % deviceid)
        # Initialize the tunnel mode on the router
        #
        # Get the router address
        deviceip = srv6_sdn_controller_state.get_device_address(
            deviceid, tenantid)
        if deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # First step: create a rule for local SIDs processing
        # This step is just required for the first VPN
        #
        # Get SID family for this router
        sid_family = self.controller_state_srv6.get_sid_family(
            deviceid, tenantid
        )
        if sid_family is None:
            # If the operation has failed, return an error message
            logging.warning(
                'Cannot get SID family for deviceid %s' % deviceid
            )
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Add the rule to steer the SIDs through the local SID table
        response = self.srv6_manager.create_iprule(
            deviceip, self.grpc_client_port, family=AF_INET6,
            table=srv6_controller_utils.LOCAL_SID_TABLE, destination=sid_family
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            logging.warning(
                'Cannot create the IP rule for destination %s: %s'
                % (sid_family, response)
            )
            # If the operation has failed, return an error message
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Add a blackhole route to drop all unknown active segments
        response = self.srv6_manager.create_iproute(
            deviceip, self.grpc_client_port, family=AF_INET6,
            type='blackhole', table=srv6_controller_utils.LOCAL_SID_TABLE
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            logging.warning(
                'Cannot create the blackhole route: %s' % response
            )
            # If the operation has failed, return an error message
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Init tunnel mode on device %s completed'
                      % deviceid)
        return NbStatusCode.STATUS_OK

    def init_overlay(self, overlayid, overlay_name,
                     overlay_type, tenantid, deviceid, overlay_info):
        logging.debug('Initiating overlay %s on the device %s'
                      % (overlay_name, deviceid))
        # Get the router address
        deviceip = srv6_sdn_controller_state.get_device_address(
            deviceid, tenantid)
        if deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the table ID for the VPN
        logging.debug(
            'Attempting to retrieve the table ID assigned to the VPN')
        tableid = srv6_sdn_controller_state.get_tableid(
            overlayid, tenantid
        )
        if tableid is None:
            # Table ID not yet assigned
            logging.debug('Cannot get table ID')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        logging.debug('Received table ID:%s', tableid)
        # Second step is the creation of the decapsulation and lookup route
        oif = ''
        table = -1
        if overlay_type == OverlayType.L2Overlay:
            # For L2 VPN we have to perform decap and forward to the VPN bridge
            # This behavior is realized by End.DX2 SRv6 action
            action = 'End.DX2'
            oif = 'br-%s' % tableid
        if overlay_type == OverlayType.IPv6Overlay:
            # For IPv6 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT6 SRv6 action
            action = 'End.DT6'
            table = tableid
        elif overlay_type == OverlayType.IPv4Overlay:
            # For IPv4 VPN we have to perform decap and lookup in IPv6 routing
            # table. This behavior is realized by End.DT4 SRv6 action
            action = 'End.DT4'
            table = tableid
        else:
            logging.warning('Error: Unsupported VPN type: %s' % overlay_type)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get a WAN interface
        # We use the WAN interface
        # in order to solve an issue of routes getting deleted when the
        # interface is assigned to a VRF
        dev = srv6_sdn_controller_state.get_wan_interfaces(deviceid, tenantid)
        if dev is None:
            # Cannot get non-loopback interface
            logging.warning('Cannot get non-loopback interface')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        if len(dev) == 0:
            # Cannot get wan interface
            logging.warning('Cannot get non-loopback interface. '
                            'No WAN interfaces')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        dev = dev[0]
        # Get the SID
        logging.debug('Attempting to get a SID for the router')
        sid = self.controller_state_srv6.get_sid(deviceid, tenantid, tableid)
        logging.debug('Received SID %s' % sid)
        # Add the End.DT4 / End.DT6 route
        response = self.srv6_manager.create_srv6_local_processing_function(
            deviceip, self.grpc_client_port, segment=sid,
            action=action, device=dev, interface=oif, table=table,
            localsid_table=srv6_controller_utils.LOCAL_SID_TABLE
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            logging.warning(
                'Cannot create the SRv6 Local Processing function: %s'
                % response
            )
            # The operation has failed, return an error message
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # If this is a L2 Overlay, we need a bridge
        devices_in_vrf = []
        if overlay_type == srv6_controller_utils.OverlayType.L2Overlay:
            # get bridge name
            br_name = 'br-%s' % tableid
            # create bridge and add the VTEP interface
            response = self.srv6_manager.create_bridge_device(
                deviceip, self.grpc_client_port,
                name=br_name
            )
            if response != SbStatusCode.STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot create bridge %s in %s'
                               % (br_name, deviceip))
                return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
            # Enslave bridge in VRF
            devices_in_vrf = [br_name]
        # Third step is the creation of the VRF assigned to the VPN
        response = self.srv6_manager.create_vrf_device(
            deviceip, self.grpc_client_port, name=overlay_name,
            table=tableid, interfaces=devices_in_vrf
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            logging.warning(
                'Cannot create the VRF %s: %s' % (overlay_name, response)
            )
            # If the operation has failed, return an error message
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Init overlay completed for the overlay %s and the '
                      'deviceid %s' % (overlay_name, deviceid))
        return NbStatusCode.STATUS_OK

    def add_slice_to_overlay(self, overlayid, overlay_name, overlay_type,
                             deviceid, interface_name, tenantid, overlay_info):
        logging.debug('Attempting to add the slice %s from the router %s '
                      'to the overlay %s'
                      % (interface_name, deviceid, overlay_name))
        # Get router address
        deviceip = srv6_sdn_controller_state.get_device_address(
            deviceid, tenantid)
        if deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the table ID
        tableid = srv6_sdn_controller_state.get_tableid(
            overlayid, tenantid)
        if tableid is None:
            logging.warning('Cannot retrieve VPN table ID')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Don't advertise the private customer network
        response = self.srv6_manager.update_interface(
            deviceip, self.grpc_client_port,
            name=interface_name, ospf_adv=False
        )
        if response == SbStatusCode.STATUS_UNREACHABLE_OSPF6D:
            # If the operation has failed, report an error message
            logging.warning('Cannot disable OSPF advertisements: '
                            'ospf6d not running')
        elif response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logging.warning('Cannot disable OSPF advertisements')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        if overlay_type == srv6_controller_utils.OverlayType.L2Overlay:
            # get bridge name
            br_name = 'br-%s' % tableid
            # add slice to the VRF
            response = self.srv6_manager.update_bridge_device(
                deviceip, self.grpc_client_port,
                name=br_name,
                interfaces=[interface_name],
                op='add_interfaces'
            )
            if response != SbStatusCode.STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot add interface %s to the bridge %s in %s'
                               % (interface_name, br_name, deviceip))
                return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        elif overlay_type in [srv6_controller_utils.OverlayType.IPv4Overlay,
                              srv6_controller_utils.OverlayType.IPv6Overlay]:
            # Add the interface to the VRF
            response = self.srv6_manager.update_vrf_device(
                deviceip, self.grpc_client_port, name=overlay_name,
                interfaces=[interface_name],
                op='add_interfaces'
            )
            if response != SbStatusCode.STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logging.warning(
                    'Cannot assign the interface to the VRF: %s' % response
                )
                return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
            # Create the routes for the subnets
            subnets = srv6_sdn_controller_state.get_ip_subnets(
                deviceid, tenantid, interface_name)
            for subnet in subnets:
                gateway = subnet['gateway']
                subnet = subnet['subnet']
                if gateway is not None and gateway != '':
                    response = self.srv6_manager.create_iproute(
                        deviceip, self.grpc_client_port,
                        destination=subnet, gateway=gateway,
                        out_interface=interface_name,
                        table=tableid
                    )
                    if response != SbStatusCode.STATUS_SUCCESS:
                        # If the operation has failed, report an error message
                        logging.warning('Cannot set route for %s (gateway %s) '
                                        'in %s ' % (subnet, gateway, deviceip))
                        return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        else:
            logger.error('Unrecognized overlay type: %s' % overlay_type)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Add slice to overlay completed')
        return NbStatusCode.STATUS_OK

    def create_tunnel(self, overlayid, overlay_name, overlay_type,
                      l_slice, r_slice, tenantid, overlay_info):
        logging.debug(
            'Attempting to create a tunnel %s between the interfaces %s and %s'
            % (overlay_name, l_slice['interface_name'],
               r_slice['interface_name'])
        )
        # Tunnel from l_slice to r_slice
        res = self._create_tunnel_uni(
            overlayid,
            overlay_name,
            overlay_type,
            l_slice,
            r_slice,
            tenantid,
            overlay_info)
        if res != NbStatusCode.STATUS_OK:
            return res
        # Tunnel from r_slice to l_slice
        res = self._create_tunnel_uni(
            overlayid, overlay_name,
            overlay_type,
            r_slice, l_slice,
            tenantid,
            overlay_info)
        if res != NbStatusCode.STATUS_OK:
            return res
        # Success
        logging.debug('Tunnel creation completed')
        return NbStatusCode.STATUS_OK

    def destroy_overlay_data(self, overlayid, overlay_name,
                             overlay_type, tenantid, overlay_info):
        logging.debug('Trying to destroy the overlay data structure')
        # Release the table ID
        res = srv6_sdn_controller_state.release_tableid(overlayid, tenantid)
        if res == -1:
            logging.debug('Cannot release the table ID')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Destroy overlay data completed')
        return NbStatusCode.STATUS_OK

    def destroy_tunnel_mode(self, deviceid, tenantid, overlay_info):
        logging.debug('Trying to destroy the tunnel mode on the '
                      'router %s' % deviceid)
        # Get router address
        deviceip = srv6_sdn_controller_state.get_device_address(
            deviceid, tenantid)
        if deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get SID family for this router
        sid_family = self.controller_state_srv6.get_sid_family(
            deviceid, tenantid)
        if sid_family is None:
            # If the operation has failed, return an error message
            logging.warning(
                'Cannot get SID family for deviceid %s' % deviceid
            )
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Remove rule for SIDs
        response = self.srv6_manager.remove_iprule(
            deviceip, self.grpc_client_port, family=AF_INET6,
            table=srv6_controller_utils.LOCAL_SID_TABLE,
            destination=sid_family
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning(
                'Cannot remove the localSID rule: %s' % response
            )
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Remove blackhole route
        response = self.srv6_manager.remove_iproute(
            deviceip, self.grpc_client_port, family=AF_INET6, type='blackhole',
            table=srv6_controller_utils.LOCAL_SID_TABLE
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning(
                'Cannot remove the blackhole rule: %s' % response
            )
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Destroy tunnel mode completed')
        return NbStatusCode.STATUS_OK

    def destroy_overlay(self, overlayid, overlay_name,
                        overlay_type, tenantid, deviceid, overlay_info):
        logging.debug('Tryingto destroy the overlay %s on device %s'
                      % (overlay_name, deviceid))
        # Get the router address
        deviceip = srv6_sdn_controller_state.get_device_address(
            deviceid, tenantid)
        if deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Extract params from the VPN
        tableid = srv6_sdn_controller_state.get_tableid(
            overlayid, tenantid)
        if tableid is None:
            # If the operation has failed, return an error message
            logging.warning('Cannot get table ID for the VPN %s' %
                            overlay_name)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the SID
        sid = self.controller_state_srv6.get_sid(deviceid, tenantid, tableid)
        if sid is None:
            # If the operation has failed, return an error message
            logging.warning('Cannot get SID for deviceid %s' % deviceid)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Remove the decap and lookup function (i.e. the End.DT4 or End.DT6
        # route)
        response = self.srv6_manager.remove_srv6_local_processing_function(
            deviceip, self.grpc_client_port, segment=sid,
            localsid_table=srv6_controller_utils.LOCAL_SID_TABLE
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning('Cannot remove seg6local route: %s' % response)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Delete the VRF assigned to the VPN
        response = self.srv6_manager.remove_vrf_device(
            deviceip, self.grpc_client_port, overlay_name
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning(
                'Cannot remove the VRF %s from the router %s: %s'
                % (overlay_name, deviceid, response)
            )
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Delete all remaining IPv6 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            deviceip, self.grpc_client_port, family=AF_INET6, table=tableid
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning('Cannot remove the IPv6 route: %s' % response)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Delete all remaining IPv4 routes associated to the VPN
        response = self.srv6_manager.remove_iproute(
            deviceip, self.grpc_client_port, family=AF_INET, table=tableid
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning('Cannot remove IPv4 routes: %s' % response)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Destroy overlay completed')
        return NbStatusCode.STATUS_OK

    def remove_slice_from_overlay(self, overlayid, overlay_name,
                                  deviceid, interface_name,
                                  tenantid, overlay_info):
        logging.debug('Trying to remove the slice %s on device %s '
                      'from the overlay %s'
                      % (interface_name, deviceid, overlay_name))
        # Get router address
        deviceip = srv6_sdn_controller_state.get_device_address(
            deviceid, tenantid)
        if deviceip is None:
            # Cannot get the router address
            logging.warning('Cannot get the router address')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Get the table ID
        tableid = srv6_sdn_controller_state.get_tableid(
            overlayid, tenantid)
        if tableid is None:
            logging.warning('Cannot retrieve VPN table ID')
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Remove IP routes from the VRF
        # This step is optional, because the routes are
        # automatically removed when the interfaces is removed
        # from the VRF. We do it just for symmetry with respect
        # to the add_slice_to_overlay function
        subnets = srv6_sdn_controller_state.get_ip_subnets(
            deviceid, tenantid, interface_name)
        for subnet in subnets:
            gateway = subnet['gateway']
            subnet = subnet['subnet']
            if gateway is not None and gateway != '':
                response = self.srv6_manager.remove_iproute(
                    deviceip, self.grpc_client_port,
                    destination=subnet, gateway=gateway,
                    table=tableid
                )
                if response != SbStatusCode.STATUS_SUCCESS:
                    # If the operation has failed, report an error message
                    logging.warning('Cannot remove route for %s (gateway %s) '
                                    'in %s ' % (subnet, gateway, deviceip))
                    return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Enable advertisements the private customer network
        response = self.srv6_manager.update_interface(
            deviceip, self.grpc_client_port,
            name=interface_name, ospf_adv=True
        )
        if response == SbStatusCode.STATUS_UNREACHABLE_OSPF6D:
            # If the operation has failed, report an error message
            logging.warning('Cannot disable OSPF advertisements: '
                            'ospf6d not running')
        elif response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning('Cannot enable OSPF advertisements: %s' % response)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Remove the interface from the VRF
        response = self.srv6_manager.update_vrf_device(
            deviceip, self.grpc_client_port, name=overlay_name,
            interfaces=[interface_name],
            op='del_interfaces'
        )
        if response != SbStatusCode.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logging.warning('Cannot remove the VRF device: %s' % response)
            return NbStatusCode.STATUS_INTERNAL_SERVER_ERROR
        # Success
        logging.debug('Remove slice from overlay completed')
        return NbStatusCode.STATUS_OK

    def remove_tunnel(self, overlayid, overlay_name, overlay_type,
                      l_slice, r_slice, tenantid, overlay_info):
        logging.debug(
            'Attempting to remove the tunnel %s between the interfaces '
            '%s and %s' % (overlay_name,
                           l_slice['interface_name'],
                           r_slice['interface_name'])
        )
        # Tunnel from l_slice to r_slice
        res = self._remove_tunnel_uni(
            overlayid, overlay_name,
            overlay_type,
            l_slice,
            r_slice,
            tenantid,
            overlay_info)
        if res != NbStatusCode.STATUS_OK:
            return res
        # Tunnel from r_slice to l_slice
        res = self._remove_tunnel_uni(
            overlayid, overlay_name,
            overlay_type,
            r_slice,
            l_slice,
            tenantid,
            overlay_info)
        if res != NbStatusCode.STATUS_OK:
            return res
        # Success
        logging.debug('Remove tunnel completed')
        return NbStatusCode.STATUS_OK

    # def get_overlays(self):
    #     # Create the response
    #     response = srv6_vpn_pb2.SRv6VPNReply(
    #         status=SbStatusCode.STATUS_SUCCESS)
    #     # Build the VPNs list
    #     for _vpn in self.controller_state_srv6.controller_state.get_vpns():
    #         # Add a new VPN to the VPNs list
    #         vpn = response.vpns.add()
    #         # Set name
    #         vpn.overlay_name = _vpn.overlay_name
    #         # Set table ID
    #         vpn.tableid = _vpn.tableid
    #         # Set interfaces
    #         # Iterate on all interfaces
    #         for interfaces in _vpn.interfaces.values():
    #             for interface in interfaces.values():
    #                 # Add a new interface to the VPN
    #                 _interface = vpn.interfaces.add()
    #                 # Add router ID
    #                 _interface.routerid = interface.routerid
    #                 # Add interface name
    #                 _interface.interface_name = interface.interface_name
    #                 # Add interface IP
    #                 _interface.interface_ip = interface.interface_ip
    #                 # Add VPN prefix
    #                 _interface.subnets = interface.subnets
    #     # Return the VPNs list
    #     logging.debug('Sending response:\n%s' % response)
    #     return response
