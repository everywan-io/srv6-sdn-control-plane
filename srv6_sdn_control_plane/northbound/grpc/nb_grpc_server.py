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
from srv6_sdn_control_plane import srv6_controller_utils
from srv6_sdn_control_plane import srv6_controller_utils
from srv6_sdn_control_plane.northbound.grpc import tunnel_utils
from srv6_sdn_control_plane.southbound.grpc import sb_grpc_client
from srv6_sdn_proto import status_codes_pb2
from srv6_sdn_controller_state import srv6_sdn_controller_state

from pymerang.pymerang_server import PymerangController
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
STATUS_ROUTER_NOTRUNNING = status_codes_pb2.STATUS_ROUTER_NOTRUNNING
STATUS_SUCCESS = status_codes_pb2.STATUS_SUCCESS
STATUS_VPN_INVALID_IP = status_codes_pb2.STATUS_VPN_INVALID_IP
STATUS_VPN_INVALID_TYPE = status_codes_pb2.STATUS_VPN_INVALID_TYPE
STATUS_VPN_NAME_UNAVAILABLE = status_codes_pb2.STATUS_VPN_NAME_UNAVAILABLE
STATUS_VPN_INVALID_PREFIX = status_codes_pb2.STATUS_VPN_INVALID_PREFIX
STATUS_VPN_NOTFOUND = status_codes_pb2.STATUS_VPN_NOTFOUND
STATUS_VPN_INVALID_TENANTID = status_codes_pb2.STATUS_VPN_INVALID_TENANTID
STATUS_INVALID_ACTION = status_codes_pb2.STATUS_INVALID_ACTION
STATUS_INTERNAL_ERROR = status_codes_pb2.STATUS_INTERNAL_ERROR


class NorthboundInterface(srv6_vpn_pb2_grpc.NorthboundInterfaceServicer):
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

    """ Configure a tenant """

    def ConfigureTenant(self, request, context):
        logger.debug('Configure tenant request received: %s' % request)
        # Extract parmeters from the request m essage
        port = request.port
        info = request.info
        # Generate token
        token = srv6_controller_utils.generate_token()
        # Get a tenant ID for the token
        tenantid = self.controller_state.get_new_tenantid(token)
        # Set dictionary
        self.controller_state.tenant_info[tenantid] = dict()
        # Save tenant info
        self.controller_state.tenant_info[tenantid]['port'] = port
        self.controller_state.tenant_info[tenantid]['info'] = info
        # Response
        return srv6_vpn_pb2.TenantReply(status=STATUS_SUCCESS, token=token, tenantid=tenantid)

    """ Remove a tenant """

    def RemoveTenant(self, request, context):
        logger.debug('Remove tenant request received: %s' % request)
        # Extract token
        token = request.token
        # Get tenant ID
        tenantid = self.controller_state.get_tenantid(token)

        # Check if the passed token has an associeted tenant ID
        if tenantid == -1:
            return srv6_vpn_pb2.InventoryServiceReply(status=STATUS_INVALID_ACTION)

        # Get all the overlays associated of the tenant ID
        tenant_overlays = self.controller_state.tenantid_to_overlays.get(
            tenantid)
        # Remove all overlays
        if tenant_overlays != None:
            while tenant_overlays:
                vpn_name = list(tenant_overlays)[0]
                self.controller_state.vpn_manager._RemoveOverlay(
                    tenantid, vpn_name, tunnel_info=None)

        # Get all the registered device of the tenant ID
        tenant_devices = self.controller_state.tenantid_to_devices.get(
            tenantid)
        # Unregister all devices
        if tenant_devices != None:
            while tenant_devices:
                device_id = list(tenant_devices)[0]
                self.controller_state.registration_server.unregister_device(
                    device_id, tunnel_info=None)

        # Release tenantid
        if tenantid in self.controller_state.tenant_info:
            self.controller_state.release_tenantid(token)
            # Remove tenant info
            del self.controller_state.tenant_info[tenantid]

        return srv6_vpn_pb2.InventoryServiceReply(status=STATUS_SUCCESS)

    """ Configure a device and change its status to 'RUNNING' """

    def ConfigureDevice(self, request, context):
        logger.debug('ConfigureDevice request received: %s' % request)
        # Get the devices
        devices = [device.id for device in request.configuration.devices]
        devices = srv6_sdn_controller_state.get_devices(
            devices, return_dict=True)
        # Extract the configurations from the request message
        new_devices = list()
        for device in request.configuration.devices:
            logger.info('Processing the configuration:\n%s' % device)
            # Parameters extraction
            #
            # Extract the device ID from the configuration
            deviceid = device.id
            # Extract the device name from the configuration
            device_name = device.name
            # Extract the device description from the configuration
            device_description = device.description
            # Extract the device interfaces from the configuration
            interfaces = devices[deviceid]['interfaces']
            for interface in device.interfaces:
                err = STATUS_SUCCESS
                interfaces[interface.name]['name'] = interface.name
                if interface.type != '':
                    interfaces[interface.name]['type'] = interface.type
                if interface.type == srv6_controller_utils.InterfaceType.WAN:
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
                            addrs.append(addr)
                        response = self.srv6_manager.remove_many_ipaddr(
                            devices[deviceid]['mgmtip'],
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
                            err = status_codes_pb2.STATUS_INTERNAL_ERROR
                        interfaces[interface.name]['ipv4_addrs'] = list()
                        # Add IP address to the interface
                        for ipv4_addr in interface.ipv4_addrs:
                            response = self.srv6_manager.create_ipaddr(
                                devices[deviceid]['mgmtip'],
                                self.grpc_client_port, ip_addr=ipv4_addr,
                                device=interface.name, family=AF_INET
                            )
                            if response != STATUS_SUCCESS:
                                # If the operation has failed,
                                # report an error message
                                logger.warning(
                                    'Cannot assign the private VPN IP address '
                                    'to the interface'
                                )
                                err = status_codes_pb2.STATUS_INTERNAL_ERROR
                            interfaces[interface.name]['ipv4_addrs'].append(
                                ipv4_addr)
                    if len(interface.ipv6_addrs) > 0:
                        addrs = list()
                        nets = list()
                        for addr in interfaces[interface.name]['ipv6_addrs']:
                            addrs.append(addr)
                            nets.append(str(IPv6Interface(addr).network))
                        response = self.srv6_manager.remove_many_ipaddr(
                            devices[deviceid]['mgmtip'],
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
                            err = status_codes_pb2.STATUS_INTERNAL_ERROR
                        interfaces[interface.name]['ipv6_addrs'] = list()
                        # Add IP address to the interface
                        for ipv6_addr in interface.ipv6_addrs:
                            net = IPv6Interface(ipv6_addr).network.__str__()
                            response = self.srv6_manager.create_ipaddr(
                                devices[deviceid]['mgmtip'],
                                self.grpc_client_port, ip_addr=ipv6_addr,
                                device=interface.name, net=net, family=AF_INET6
                            )
                            if response != STATUS_SUCCESS:
                                # If the operation has failed,
                                # report an error message
                                logger.warning(
                                    'Cannot assign the private VPN IP address '
                                    'to the interface'
                                )
                                err = status_codes_pb2.STATUS_INTERNAL_ERROR
                            interfaces[interface.name]['ipv6_addrs'].append(
                                ipv6_addr)
                    for subnet in interface.ipv4_subnets:
                        interfaces[interface.name]['ipv4_subnets'].append(
                            subnet)
                    for subnet in interface.ipv6_subnets:
                        interfaces[interface.name]['ipv6_subnets'].append(
                            subnet)
            # Push the new configuration
            if err == STATUS_SUCCESS:
                logger.debug(
                    'The device %s has been configured successfully' % deviceid
                )
                new_devices.append({
                    'deviceid': deviceid,
                    'name': device_name,
                    'description': device_description,
                    'interfaces': interfaces,
                    'status': srv6_controller_utils.DeviceStatus.RUNNING
                })
            else:
                logger.warning(
                    'The device %s rejected the configuration' % deviceid)
        srv6_sdn_controller_state.configure_devices(new_devices)
        logger.info('The device configuration has been saved\n\n')
        # Create the response
        return srv6_vpn_pb2.OverlayServiceReply(status=STATUS_SUCCESS)

    """ Get the registered devices """

    def GetDevices(self, request, context):
        logger.debug('GetDeviceInformation request received')
        # Extract the device IDs from the request
        deviceids = list(request.deviceids)
        deviceids = deviceids if len(deviceids) > 0 else None
        # Extract the tenant ID from the request
        tenantid = int(request.tenantid)
        tenantid = tenantid if tenantid != -1 else None
        # Create the response
        response = (srv6_vpn_pb2
                    .InventoryServiceReply(status=STATUS_SUCCESS))
        # Iterate on devices and fill the response message
        for _device in srv6_sdn_controller_state.get_devices(deviceids=deviceids,
                                                             tenantid=tenantid,
                                                             return_dict=True):
            device = response.device_information.devices.add()
            device.id = text_type(_device['deviceid'])
            _interfaces = _device.get('interfaces', [])
            for ifname, ifinfo in _interfaces.items():
                interface = device.interfaces.add()
                interface.name = ifname
                interface.mac_addr = ifinfo['mac_addr']
                interface.ipv4_addrs.extend(ifinfo['ipv4_addrs'])
                interface.ipv6_addrs.extend(ifinfo['ipv6_addrs'])
                interface.ext_ipv4_addrs.extend(ifinfo['ext_ipv4_addrs'])
                interface.ext_ipv6_addrs.extend(ifinfo['ext_ipv6_addrs'])
                interface.ipv4_subnets.extend(ifinfo['ipv4_subnets'])
                interface.ipv6_subnets.extend(ifinfo['ipv6_subnets'])
                interface.type = ifinfo['type']
            mgmtip = _device.get('mgmtip')
            status = _device.get('status')
            name = _device.get('name')
            description = _device.get('description')
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

    """ Get the topology information """

    def GetTopologyInformation(self, request, context):
        logger.debug('GetTopologyInformation request received')
        # Create the response
        response = (srv6_vpn_pb2
                    .InventoryServiceReply(status=STATUS_SUCCESS))
        # Build the topology
        topology = srv6_sdn_controller_state.get_topology()
        nodes = topology['nodes']
        links = topology['links']
        devices = set()
        # Iterate on nodes
        for node in nodes:
            if node['type'] != 'router':
                # Skip stub networks
                continue
            devices.add(node['id'])
            response.topology_information.devices.append(node['id'])
        # Iterate on links
        for _link in links:
            if _link[0] in devices and _link[1] in devices:
                link = response.topology_information.links.add()
                link.l_device = _link[0]
                link.r_device = _link[1]
        # Return the response
        logger.debug('Sending response:\n%s' % response)
        return response

    """Create a VPN from an intent received through the northbound interface"""

    def CreateOverlay(self, request, context):
        logger.info('CreateOverlay request received:\n%s', request)
        # Extract the intents from the request message
        for intent in request.intents:
            logger.info('Processing the intent:\n%s' % intent)
            # Parameters extraction
            #
            # Extract the overlay tenant ID from the intent
            tenantid = int(intent.tenantid)
            # Extract the overlay type from the intent
            overlay_type = int(intent.overlay_type)
            # Extract the overlay name from the intent
            overlay_name = intent.overlay_name
            # Get the overlay full name (i.e. tenantid-overlay_name)
            overlay_fullname = '%s-%s' % (tenantid, overlay_name)
            # Extract the interfaces
            slices = list()
            devices = set()
            for _slice in intent.slices:
                deviceid = _slice.deviceid
                interface_name = _slice.interface_name
                # Add the slice to the slices set
                slices.append((deviceid, interface_name))
                # Add the device to the devices set
                devices.add(deviceid)
            # Extract tunnel type
            tunnel_name = intent.tunnel
            tunnel_mode = self.tunnel_modes[tunnel_name]
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Parameters validation
            #
            # Validate the tenant ID
            logger.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                logger.warning('Invalid tenant ID: %s' % tenantid)
                # If tenant ID is invalid, return an error message
                return (srv6_vpn_pb2
                        .OverlayServiceReply(status=STATUS_VPN_INVALID_TENANTID))
            # Validate the overlay type
            logger.debug('Validating the overlay type:\n%s' % overlay_type)
            if not srv6_controller_utils.validate_vpn_type(overlay_type):
                logger.warning('Invalid overlay type: %s' % overlay_type)
                # If the overlay type is invalid, return an error message
                return (srv6_vpn_pb2
                        .OverlayServiceReply(status=STATUS_VPN_INVALID_TYPE))
            # Let's check if the overlay does not exist
            logger.debug('Validating the overlay name: %s' % overlay_name)
            if srv6_sdn_controller_state.overlay_exists(overlay_name, tenantid):
                logger.warning('Overlay name %s is already in use for tenant %s' % (
                    overlay_name, tenantid))
                # If the overlay already exists, return an error message
                return (srv6_vpn_pb2
                        .OverlayServiceReply(status=STATUS_VPN_NAME_UNAVAILABLE))
            # Get the devices
            devices = srv6_sdn_controller_state.get_devices(devices, return_dict=True)
            # Validate the slices included in the intent
            for _slice in slices:
                logger.debug('Validating the slice: %s-%s' % _slice)
                # A slice is a tuple (deviceid, interface_name)
                #
                # Extract the device ID
                deviceid = _slice[0]
                # Extract the interface name
                interface_name = _slice[1]
                # Let's check if the router exists
                if deviceid not in devices:
                    logger.warning(
                        'Device not found %s' % deviceid
                    )
                    # If the device does not exist, return an error message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_ROUTER_NOTFOUND))
                # Check if the device is running
                if not devices[deviceid]['status'] == srv6_sdn_controller_state.utils.DeviceStatus.RUNNING:
                    logger.warning(
                        'The device %s is not running' % deviceid
                    )
                    # If the device is not running, return an error message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_ROUTER_NOTRUNNING))
                # Let's check if the interface exists
                if interface_name not in devices[deviceid]['interfaces']:
                    logger.warning('The interface does not exist')
                    # If the interface does not exists, return an error
                    # message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_INTF_NOTFOUND))
            # All the devices must belong to the same tenant
            for device in devices.values():
                if device['tenantid'] != tenantid:
                    logger.warning('Error while processing the intent: '
                                   'All the devices must belong to the '
                                   'same tenant %s' % tenantid)
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_INTERNAL_ERROR))
            logger.info('All checks passed')
            # All checks passed
            #
            # Let's create the overlay
            # Create overlay data structure
            tunnel_mode.init_overlay_data(
                overlay_fullname, tenantid, tunnel_info)
            # Iterate on slices and add to the overlay
            configured_slices = set()
            for site1 in slices:
                deviceid = site1[0]
                interface_name = site1[1]
                # Init tunnel mode on the devices
                if srv6_sdn_controller_state.inc_tunnel_mode_refcount(tunnel_name, deviceid) == 0:
                    tunnel_mode.init_tunnel_mode(
                        deviceid, tenantid, tunnel_info)
                # Check if we have already configured the overlay on the device
                if deviceid in devices:
                    # Init overlay on the devices
                    tunnel_mode.init_overlay(
                        overlay_fullname, overlay_type, tenantid, deviceid, tunnel_info)
                    # Remove device from the to-be-configured devices set
                    devices.remove(deviceid)
                # Add the interface to the overlay
                (tunnel_mode
                 .add_slice_to_overlay(overlay_fullname, deviceid,
                                       interface_name, tenantid, tunnel_info))
                # Create the tunnel between all the pairs of interfaces
                for site2 in configured_slices:
                    if site1[0] != site2[0]:
                        tunnel_mode.create_tunnel(overlay_fullname, overlay_type, site1,
                                                  site2, tenantid, tunnel_info)
                # Add the slice to the configured set
                configured_slices.add(site1)
            # Save the overlay to the state
            srv6_sdn_controller_state.create_overlay(
                overlay_name, overlay_type, slices, tenantid, tunnel_name)
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.OverlayServiceReply(status=STATUS_SUCCESS)

    """Remove a VPN"""

    def RemoveOverlay(self, request, context):
        logger.info('RemoveOverlay request received:\n%s', request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the overlay ID from the intent
            overlayid = intent.overlayid
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Remove VPN
            response = self._RemoveOverlay(overlayid, tunnel_info)
            if response != STATUS_SUCCESS:
                return srv6_vpn_pb2.OverlayServiceReply(status=response)
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.OverlayServiceReply(status=STATUS_SUCCESS)

    def _RemoveOverlay(self, overlayid, tunnel_info):
        # Parameters validation
        #
        # Let's check if the overlay exists
        logger.debug('Checking the overlay: %s' % overlayid)
        overlay = srv6_sdn_controller_state.get_overlay(overlayid)
        if overlay is None:
            logger.warning('The overlay %s does not exist' % overlayid)
            # If the overlay does not exist, return an error message
            return STATUS_VPN_NOTFOUND
        # Get the tenant ID
        tenantid = overlay['tenantid']
        # Get the overlay name
        overlay_name = overlay['name']
        # Get the overlay full name (i.e. tenantid-overlay_name)
        overlay_fullname = '%s-%s' % (tenantid, overlay_name)
        # Get the overlay type
        overlay_type = overlay['type']
        # Get the tunnel mode
        tunnel_name = overlay['tunnel_mode']
        tunnel_mode = self.tunnel_modes[tunnel_name]
        # Get the slices belonging to the overlay
        slices = overlay['slices']
        # All checks passed
        logger.debug('Check passed')
        # Let's remove the VPN
        devices = set()
        configured_slices = slices.copy()
        for site1 in slices:
            deviceid = site1[0]
            interface_name = site1[1]
            # Remove the tunnel between all the pairs of interfaces
            for site2 in configured_slices:
                if site1[0] != site2[0]:
                    tunnel_mode.remove_tunnel(
                        overlay_fullname, overlay_type, site1,
                        site2, tenantid, tunnel_info)
            # Mark the site1 as unconfigured
            configured_slices.remove(site1)
            # Remove the interface from the overlay
            tunnel_mode.remove_slice_from_overlay(overlay_fullname,
                                                  deviceid,
                                                  interface_name,
                                                  tenantid,
                                                  tunnel_info)
            # Check if the overlay and the tunnel mode
            # has already been deleted on the device
            if deviceid not in devices:
                # Destroy overlay on the devices
                tunnel_mode.destroy_overlay(overlay_fullname,
                                            overlay_type,
                                            tenantid,
                                            deviceid,
                                            tunnel_info)
                devices.add(deviceid)
            # Destroy tunnel mode on the devices
            if srv6_sdn_controller_state.dec_tunnel_mode_refcount(tunnel_name, deviceid) == 0:
                tunnel_mode.destroy_tunnel_mode(
                    deviceid, tenantid, tunnel_info)
        # Destroy overlay data structure
        tunnel_mode.destroy_overlay_data(
            overlay_fullname, tenantid, tunnel_info)
        # Delete the overlay
        srv6_sdn_controller_state.remove_overlay(overlayid)
        # Create the response
        return STATUS_SUCCESS

    """Assign an interface to a VPN"""

    def AssignSliceToOverlay(self, request, context):
        logger.info('AssignSliceToOverlay request received:\n%s' % request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the overlay ID from the intent
            overlayid = intent.overlayid
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Get the overlay
            overlay = srv6_sdn_controller_state.get_overlay(overlayid)
            if overlay is None:
                logger.warning('The overlay %s does not exist' % overlayid)
                # If the overlay does not exist, return an error message
                return STATUS_VPN_NOTFOUND
            # Get the overlay tenant ID
            tenantid = overlay['tenantid']
            # Get the overlay name
            overlay_name = overlay['name']
            # Get the overlay full name (i.e. tenantid-overlay_name)
            overlay_fullname = '%s-%s' % (tenantid, overlay_name)
            # Get the overlay type
            overlay_type = overlay['type']
            # Get the tunnel mode
            tunnel_name = overlay['tunnel_mode']
            tunnel_mode = self.tunnel_modes[tunnel_name]
            # Get the slices belonging to the overlay
            slices = overlay['slices']
            # Get the devices on which the overlay has been configured
            devices = [_slice[0] for _slice in slices]
            # Extract the interfaces
            incoming_slices = list()
            incoming_devices = set()
            for _slice in intent.slices:
                deviceid = _slice[0]
                interface_name = _slice[1]
                # Add the slice to the incoming slices set
                incoming_slices.append(_slice)
                # Add the device to the incoming devices set
                # if the overlay has not been initiated on it
                if deviceid not in devices:
                    incoming_devices.add(deviceid)
            # Parameters validation
            #
            # Let's check if the overlay exists
            logger.debug('Checking the VPN: %s' % overlay_name)
            # Iterate on the interfaces and extract the
            # interfaces to be assigned
            # to the overlay and validate them
            for _slice in incoming_slices:
                logger.debug('Validating the slice: %s-%s' % _slice)
                # A slice is a tuple (deviceid, interface_name)
                #
                # Extract the device ID
                deviceid = _slice[0]
                # Extract the interface name
                interface_name = _slice[1]
                # Let's check if the router exists
                if deviceid not in devices:
                    logger.warning(
                        'Device not found %s' % deviceid
                    )
                    # If the device does not exist, return an error message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_ROUTER_NOTFOUND))
                # Check if the device is running
                if not devices[deviceid]['status'] == srv6_sdn_controller_state.utils.DeviceStatus.RUNNING:
                    logger.warning(
                        'The device %s is not running' % deviceid
                    )
                    # If the device is not running, return an error message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_ROUTER_NOTRUNNING))
                # Let's check if the interface exists
                if interface_name not in devices[deviceid]['interfaces']:
                    logger.warning('The interface does not exist')
                    # If the interface does not exists, return an error
                    # message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_INTF_NOTFOUND))

                # TODO
                '''
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
                    return srv6_vpn_pb2.OverlayServiceReply(
                        status=status_codes_pb2.STATUS_INTF_ALREADY_ASSIGNED)
                '''

            # All the devices must belong to the same tenant
            for device in devices:
                if device['tenantid'] != tenantid:
                    logger.warning('Error while processing the intent: '
                                   'All the devices must belong to the '
                                   'same tenant %s' % tenantid)
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_INTERNAL_ERROR))
            logger.info('All checks passed')
            # All checks passed
            #
            # Let's assign the interface to the overlay
            configured_slices = slices
            for site1 in incoming_slices:
                deviceid = site1.routerid
                interface_name = site1.interface_name
                # Init tunnel mode on the devices
                if srv6_sdn_controller_state.inc_tunnel_mode_refcount(tunnel_name, deviceid) == 0:
                    tunnel_mode.init_tunnel_mode(
                        deviceid, tenantid, tunnel_info)
                # Check if we have already configured the overlay on the device
                if deviceid in incoming_devices:
                    # Init tunnel mode on the devices
                    if srv6_sdn_controller_state.inc_tunnel_mode_refcount(tunnel_name, deviceid) == 0:
                        tunnel_mode.init_tunnel_mode(
                            deviceid, tenantid, tunnel_info)
                    # Init overlay on the devices
                    tunnel_mode.init_overlay(
                        overlay_fullname, overlay_type, tenantid, deviceid, tunnel_info)
                    # Remove device from the to-be-configured devices set
                    incoming_devices.remove(deviceid)
                # Add the interface to the overlay
                tunnel_mode.add_slice_to_overlay(
                    overlay_fullname, deviceid, interface_name, tenantid, tunnel_info)
                # Create the tunnel between all the pairs of interfaces
                for site2 in configured_slices:
                    if site1[0] != site2[0]:
                        tunnel_mode.create_tunnel(overlay_fullname, overlay_type, site1,
                                                  site2, tenantid, tunnel_info)
                # Add the slice to the configured set
                configured_slices.add(site1)
            # Save the overlay to the state
            srv6_sdn_controller_state.add_many_slices_to_overlay(
                overlayid, incoming_slices)
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.OverlayServiceReply(status=STATUS_SUCCESS)

    """Remove an interface from a VPN"""

    def RemoveSliceFromOverlay(self, request, context):
        logger.info('RemoveSliceFromOverlay request received:\n%s' % request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the overlay ID from the intent
            overlayid = intent.overlayid
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Let's check if the overlay exists
            logger.debug('Checking the overlay: %s' % overlayid)
            overlay = srv6_sdn_controller_state.get_overlay(overlayid)
            if overlay is None:
                logger.warning('The overlay %s does not exist' % overlayid)
                # If the overlay does not exist, return an error message
                return STATUS_VPN_NOTFOUND
            # Get the tenant ID
            tenantid = overlay['tenantid']
            # Get the overlay name
            overlay_name = overlay['name']
            # Get the overlay full name (i.e. tenantid-overlay_name)
            overlay_fullname = '%s-%s' % (tenantid, overlay_name)
            # Get the overlay type
            overlay_type = overlay['type']
            # Get the tunnel mode
            tunnel_name = overlay['tunnel_mode']
            tunnel_mode = self.tunnel_modes[tunnel_name]
            # Get the slices belonging to the overlay
            slices = overlay['slices']
            # Extract the interfaces
            incoming_slices = list()
            incoming_devices = set()
            for _slice in intent.slices:
                deviceid = _slice[0]
                interface_name = _slice[1]
                # Add the slice to the incoming slices set
                incoming_slices.append(_slice)
                # Add the device to the incoming devices set
                # if the overlay has not been initiated on it
                if deviceid not in devices:
                    incoming_devices.add(deviceid)
            # Parameters validation
            #
            # Iterate on the interfaces
            # and extract the interfaces to be removed from the VPN
            for _slice in incoming_slices:
                logger.debug('Validating the slice: %s-%s' % _slice)
                # A slice is a tuple (deviceid, interface_name)
                #
                # Extract the device ID
                deviceid = _slice[0]
                # Extract the interface name
                interface_name = _slice[1]
                # Let's check if the router exists
                if deviceid not in devices:
                    logger.warning(
                        'Device not found %s' % deviceid
                    )
                    # If the device does not exist, return an error message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_ROUTER_NOTFOUND))
                # Check if the device is running
                if not devices[deviceid]['status'] == srv6_sdn_controller_state.utils.DeviceStatus.RUNNING:
                    logger.warning(
                        'The device %s is not running' % deviceid
                    )
                    # If the device is not running, return an error message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_ROUTER_NOTRUNNING))
                # Let's check if the interface exists
                if interface_name not in devices[deviceid]['interfaces']:
                    logger.warning('The interface does not exist')
                    # If the interface does not exists, return an error
                    # message
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_INTF_NOTFOUND))
                # Let's check if the interface is assigned to the given overlay
                if _slice not in overlay['slices']:
                    # The interface is not assigned to the overlay, return an error
                    # message
                    logger.warning(
                        'The interface is not assigned to the overlay %s, '
                        '(name %s, tenantid %s)' % (overlayid, overlay_name, tenantid))
                    return srv6_vpn_pb2.OverlayServiceReply(
                        status=STATUS_INTF_NOTASSIGNED)
            # All the devices must belong to the same tenant
            for device in devices:
                if device['tenantid'] != tenantid:
                    logger.warning('Error while processing the intent: '
                                   'All the devices must belong to the '
                                   'same tenant %s' % tenantid)
                    return (srv6_vpn_pb2
                            .OverlayServiceReply(status=STATUS_INTERNAL_ERROR))
            logger.debug('All checks passed')
            # All checks passed
            #
            # Let's remove the interface from the VPN
            configured_slices = slices.copy()
            for site1 in slices:
                deviceid = site1[0]
                interface_name = site1[1]
                # Remove the tunnel between all the pairs of interfaces
                for site2 in configured_slices:
                    if site1[0] != site2[0]:
                        tunnel_mode.remove_tunnel(
                            overlay_fullname, overlay_type, site1,
                            site2, tenantid, tunnel_info)
                # Remove the interface from the overlay
                tunnel_mode.remove_slice_from_overlay(
                    overlay_fullname, deviceid, interface_name, tenantid, tunnel_info)
                # Check if the overlay and the tunnel mode
                # has already been deleted on the device
                if deviceid not in devices:
                    # Destroy overlay on the devices
                    tunnel_mode.destroy_overlay(overlay_fullname,
                                                overlay_type,
                                                tenantid,
                                                deviceid,
                                                tunnel_info)
                    devices.add(deviceid)
                # Destroy tunnel mode on the devices
                if srv6_sdn_controller_state.dec_tunnel_mode_refcount(tunnel_name, deviceid) == 0:
                    tunnel_mode.destroy_tunnel_mode(
                        deviceid, tenantid, tunnel_info)
            # Save the overlay to the state
            srv6_sdn_controller_state.remove_many_slices_to_overlay(
                overlayid, incoming_slices)
        logger.info('All the intents have been processed successfully\n\n')
        # Create the response
        return srv6_vpn_pb2.OverlayServiceReply(status=STATUS_SUCCESS)

    # Get VPNs from the controller inventory
    def GetOverlays(self, request, context):
        logger.debug('GetOverlays request received')
        # Extract the overlay IDs from the request
        overlayids = list(request.overlayids)
        overlayids = overlayids if len(overlayids) > 0 else None
        # Extract the tenant ID
        tenantid = int(request.tenantid)
        tenantid = tenantid if tenantid != -1 else None
        # Create the response
        response = srv6_vpn_pb2.OverlayServiceReply(status=STATUS_SUCCESS)
        # Build the overlays list
        for _overlay in srv6_sdn_controller_state.get_overlays(overlayids=overlayids,
                                                               tenantid=tenantid):
            # Add a new overlay to the overlays list
            overlay = response.overlays.add()
            # Set overlay ID
            overlay.overlayid = _overlay['_id']
            # Set overlay name
            overlay.overlay_name = _overlay['name']
            # Set overlaty type
            overlay.overlay_type = _overlay['type']
            # Set tenant ID
            overlay.tenantid = _overlay['tenantid']
            # Set tunnel mode
            overlay.tunnel_mode = _overlay['tunnel_mode']
            # Set slices
            # Iterate on all slices
            for _slice in _overlay['slices']:
                # Add a new slice to the overlay
                __slice = overlay.slices.add()
                # Add device ID
                __slice.deviceid = _slice[0]
                # Add interface name
                __slice.interface_name = _slice[1]
        # Return the overlays list
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
                 controller_state=None,
                 verbose=DEFAULT_VERBOSE):
    # Initialize controller state
    # controller_state = srv6_controller_utils.ControllerState(
    #    topology=topo_graph,
    #    devices=devices,
    #    vpn_dict=vpn_dict,
    #    vpn_file=vpn_file
    # )
    # Create SRv6 Manager
    srv6_manager = sb_grpc_client.SRv6Manager()
    # Setup gRPC server
    #
    # Create the server and add the handler
    grpc_server = grpc.server(futures.ThreadPoolExecutor())
    service = NorthboundInterface(
        grpc_client_port, srv6_manager,
        southbound_interface, controller_state, verbose
    )
    srv6_vpn_pb2_grpc.add_NorthboundInterfaceServicer_to_server(
        service, grpc_server
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
    topo_graph = srv6_controller_utils.load_topology_from_json_dump(topo_file)
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
