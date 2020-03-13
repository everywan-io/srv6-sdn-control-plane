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
# ipaddress dependencies
from ipaddress import IPv6Interface
# SRv6 dependencies
from srv6_sdn_proto import srv6_vpn_pb2_grpc
from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_control_plane import srv6_controller_utils
from srv6_sdn_control_plane.northbound.grpc import tunnel_utils
from srv6_sdn_control_plane.southbound.grpc import sb_grpc_client
from srv6_sdn_proto import status_codes_pb2
from srv6_sdn_controller_state import srv6_sdn_controller_state
from srv6_sdn_proto.status_codes_pb2 import Status, NbStatusCode, SbStatusCode
from srv6_sdn_proto.srv6_vpn_pb2 import TenantReply, OverlayServiceReply
from srv6_sdn_proto.srv6_vpn_pb2 import InventoryServiceReply

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
# Validate topology
VALIDATE_TOPO = False
# Default VXLAN port
DEFAULT_VXLAN_PORT = 4789

# Status codes
STATUS_OK = NbStatusCode.STATUS_OK
STATUS_BAD_REQUEST = NbStatusCode.STATUS_BAD_REQUEST
STATUS_INTERNAL_SERVER_ERROR = NbStatusCode.STATUS_INTERNAL_SERVER_ERROR


class NorthboundInterface(srv6_vpn_pb2_grpc.NorthboundInterfaceServicer):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 srv6_manager=None,
                 southbound_interface=DEFAULT_SB_INTERFACE,
                 auth_controller=None,
                 verbose=DEFAULT_VERBOSE):
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # Southbound interface
        self.southbound_interface = southbound_interface
        # SRv6 Manager
        self.srv6_manager = srv6_manager
        # Authentication controller
        self.auth_controller = auth_controller
        # Initialize tunnel state
        self.tunnel_modes = tunnel_utils.TunnelState(
            srv6_manager=srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose
        ).tunnel_modes
        self.supported_tunnel_modes = [t_mode for t_mode in self.tunnel_modes]
        logging.info('*** Supported tunnel modes: %s'
                     % self.supported_tunnel_modes)

    """ Configure a tenant """

    def ConfigureTenant(self, request, context):
        logging.debug('Configure tenant request received: %s' % request)
        # Extract tenant ID
        tenantid = request.tenantid
        # Extract tenant info
        tenant_info = request.tenant_info
        tenant_info = tenant_info if tenant_info != '' else None
        # Extract VXLAN port
        vxlan_port = request.config.vxlan_port
        vxlan_port = vxlan_port if vxlan_port != -1 else None
        # Parmeters validation
        #
        # Validate tenant ID
        logging.debug('Validating the tenant ID: %s' % tenantid)
        if not srv6_controller_utils.validate_tenantid(tenantid):
            # If tenant ID is invalid, return an error message
            err = 'Invalid tenant ID: %s' % tenantid
            logging.warning(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Validate VXLAN port
        if not srv6_controller_utils.validate_port(vxlan_port):
            # If VXLAN port is invalid, return an error message
            err = ('Invalid VXLAN port for the tenant: %s'
                   % (vxlan_port, tenantid))
            logging.warning(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Check if the tenant is configured
        is_config = srv6_sdn_controller_state.is_tenant_configured(tenantid)
        if is_config and vxlan_port is not None:
            err = 'Cannot change the VXLAN port for a configured tenant'
            logging.error(err)
            return TenantReply(
                status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Configure the tenant
        vxlan_port = vxlan_port if vxlan_port is not None else DEFAULT_VXLAN_PORT
        srv6_sdn_controller_state.configure_tenant(
            tenantid, tenant_info, vxlan_port)
        # Response
        return TenantReply(status=Status(code=STATUS_OK, reason='OK'))

    """ Remove a tenant """

    def RemoveTenant(self, request, context):
        logging.debug('Remove tenant request received: %s' % request)
        # Extract tenant ID
        tenantid = request.tenantid
        # Parmeters validation
        #
        # Validate tenant ID
        logging.debug('Validating the tenant ID: %s' % tenantid)
        if not srv6_controller_utils.validate_tenantid(tenantid):
            # If tenant ID is invalid, return an error message
            err = 'Invalid tenant ID: %s' % tenantid
            logging.warning(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Remove the tenant
        #
        # Get all the overlays associated to the tenant ID
        overlays = srv6_sdn_controller_state.get_overlays(tenantid=tenantid)
        if overlays is None:
            err = 'Error getting overlays'
            logging.error(err)
            return InventoryServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR, reason=err))
        # Remove all overlays
        for overlay in overlays:
            overlayid = overlay['_id']
            self._RemoveOverlay(
                overlayid, tenantid, tunnel_info=None)
        # Get all the devices of the tenant ID
        devices = srv6_sdn_controller_state.get_devices(tenantid=tenantid)
        if devices is None:
            err = 'Error getting devices'
            logging.error(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR, reason=err))
        for device in devices:
            # Unregister all devices
            deviceid = device['deviceid']
            logging.debug('Unregistering device %s' % deviceid)
            self._unregister_device(deviceid, tenantid)
        # TODO remove tenant from keystone
        #
        # Success
        return InventoryServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    def enable_disable_device(self, deviceid, enabled):
        # Enable/Disable the device
        res = srv6_sdn_controller_state.set_device_enabled_flag(
            deviceid=deviceid, enabled=enabled)
        if res is None:
            err = ('Error while changing the enabled flag for the device %s: '
                   'Unable to update the controller state' % deviceid)
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        elif res is False:
            err = ('Error while changing the enabled flag for the device %s: '
                   % deviceid)
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        # Success
        return STATUS_OK, 'OK'

    """ Enable a device """

    def EnableDevice(self, request, context):
        logging.debug('EnableDevice request received: %s' % request)
        # Iterates on each device
        for device in request.devices:
            # Extract device ID
            deviceid = device.id
            # Extract tenant ID
            # tenantid = device.tenantid
            # Enable the device
            status_code, reason = self.enable_disable_device(deviceid=deviceid,
                                                             enabled=True)
            if status_code != STATUS_OK:
                # Error
                return OverlayServiceReply(
                    status=Status(code=status_code, reason=reason))
        # Success: create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    """ Enable a device """

    def DisableDevice(self, request, context):
        logging.debug('DisableDevice request received: %s' % request)
        # Iterates on each device
        for device in request.devices:
            # Extract device ID
            deviceid = device.id
            # Extract tenant ID
            tenantid = device.tenantid
            # Check tunnels stats
            # If the tenant has some overlays configured
            # it is not possible to unregister it
            num = srv6_sdn_controller_state.get_num_tunnels(deviceid)
            if num is None:
                err = ('Error getting tunnels stats. Device not found '
                       'or error during the connection to the db')
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif num != 0:
                err = ('Cannot unregister the device. '
                       'The device has %s (tenant %s) has tunnels registered'
                       % (deviceid, tenantid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Disable the device
            status_code, reason = self.enable_disable_device(deviceid=deviceid,
                                                             enabled=False)
            if status_code != STATUS_OK:
                # Error
                return OverlayServiceReply(
                    status=Status(code=status_code, reason=reason))
        # Success: create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    """ Configure a device and change its status to 'RUNNING' """

    def ConfigureDevice(self, request, context):
        logging.debug('ConfigureDevice request received: %s' % request)
        # Get the devices
        devices = [device.id for device in request.configuration.devices]
        devices = srv6_sdn_controller_state.get_devices(
            deviceids=devices, return_dict=True)
        if devices is None:
            logging.error('Error getting devices')
            return OverlayServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                              reason='Error getting devices'))
        # Convert interfaces list to a dict representation
        # This step simplifies future processing
        interfaces = dict()
        for deviceid in devices:
            for interface in devices[deviceid]['interfaces']:
                interfaces[interface['name']] = interface
            devices[deviceid]['interfaces'] = interfaces
        # Parameters validation
        for device in request.configuration.devices:
            # Parameters extraction
            #
            # Extract the device ID from the configuration
            deviceid = device.id
            # Extract the tenant ID
            tenantid = device.tenantid
            # Extract the interfaces
            interfaces = device.interfaces
            # Extract the device name
            device_name = device.name
            # Extract the device description
            device_description = device.description
            # If the device is partecipating to some overlay
            # we cannot configure it
            overlay = srv6_sdn_controller_state.get_overlay_containing_device(
                deviceid, tenantid)
            if overlay is not None:
                err = ('Cannot configure device %s: the device '
                       'is partecipating to the overlay %s'
                       % (deviceid, overlay['_id']))
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Name is mandatory
            if device_name is None or device_name == '':
                err = ('Invalid configuration for device %s\n'
                       'Invalid value for the mandatory parameter '
                       '"name": %s' % (deviceid, device_name))
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Description parameter is mandatory
            if device_description is None or device_description == '':
                err = ('Invalid configuration for device %s\n'
                       'Invalid value for the mandatory parameter '
                       '"description": %s' % (deviceid, device_description))
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Validate the device IDs
            logging.debug('Validating the device ID: %s' % deviceid)
            if not srv6_controller_utils.validate_deviceid(deviceid):
                # If device ID is invalid, return an error message
                err = ('Invalid configuration for device %s\n'
                       'Invalid device ID: %s' % (deviceid, deviceid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Validate the tenant ID
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = ('Invalid configuration for device %s\n'
                       'Invalid tenant ID: %s' % (deviceid, tenantid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Check if the devices exist
            if deviceid not in devices:
                err = ('Invalid configuration for device %s\n'
                       'Device not found: %s' % (deviceid, deviceid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Check if the device belongs to the tenant
            if tenantid != devices[deviceid]['tenantid']:
                err = ('Invalid configuration for device %s\n'
                       'The device %s does not belong to the tenant %s'
                       % (deviceid, deviceid, tenantid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Validate the interfaces
            wan_interfaces_counter = 0
            lan_interfaces_counter = 0
            for interface in interfaces:
                # Update counters
                if interface.type == srv6_controller_utils.InterfaceType.WAN:
                    wan_interfaces_counter += 1
                elif interface.type == srv6_controller_utils.InterfaceType.LAN:
                    lan_interfaces_counter += 1
                # Check if the interface exists
                if interface.name not in devices[deviceid]['interfaces']:
                    err = ('Invalid configuration for device %s\n'
                           'Interface %s not found on device %s'
                           % (deviceid, interface.name, deviceid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check interface type
                if not (srv6_controller_utils
                        .validate_interface_type(interface.type)):
                    err = ('Invalid configuration for device %s\n'
                           'Invalid type %s for the interface %s (%s)'
                           % (deviceid, interface.type, interface.name,
                              deviceid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Cannot set IP address and subnets for the WAN interfaces
                if interface.type == srv6_controller_utils.InterfaceType.WAN:
                    if len(interface.ipv4_addrs) > 0 or \
                            len(interface.ipv6_addrs) > 0:
                        err = ('Invalid configuration for device %s\n'
                               'WAN interfaces do not support IP addrs '
                               'assignment: %s' % (deviceid, interface.name))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=STATUS_BAD_REQUEST, reason=err))
                    if len(interface.ipv4_subnets) > 0 or \
                            len(interface.ipv6_subnets) > 0:
                        err = ('Invalid configuration for device %s\n'
                               'WAN interfaces do not support subnets '
                               'assignment: %s' % (deviceid, interface.name))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Validate IP addresses
                for ipaddr in interface.ipv4_addrs:
                    if not srv6_controller_utils.validate_ipv4_address(ipaddr):
                        err = ('Invalid configuration for device %s\n'
                               'Invalid IPv4 address %s for the interface %s'
                               % (deviceid, ipaddr, interface.name))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=STATUS_BAD_REQUEST, reason=err))
                for ipaddr in interface.ipv6_addrs:
                    if not srv6_controller_utils.validate_ipv6_address(ipaddr):
                        err = ('Invalid configuration for device %s\n'
                               'Invalid IPv6 address %s for the interface %s'
                               % (deviceid, ipaddr, interface.name))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Validate subnets
                for subnet in interface.ipv4_subnets:
                    gateway = subnet.gateway
                    subnet = subnet.subnet
                    if not srv6_controller_utils.validate_ipv4_address(subnet):
                        err = ('Invalid configuration for device %s\n'
                               'Invalid IPv4 subnet %s for the interface %s'
                               % (deviceid, subnet, interface.name))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=STATUS_BAD_REQUEST, reason=err))
                    if gateway is not None and gateway != '':
                        if (not srv6_controller_utils
                                .validate_ipv4_address(gateway)):
                            err = ('Invalid configuration for device %s\n'
                                   'Invalid IPv4 gateway %s for the subnet %s '
                                   'on the interface %s'
                                   % (deviceid, gateway, subnet, interface.name))
                            logging.warning(err)
                            return OverlayServiceReply(
                                status=Status(code=STATUS_BAD_REQUEST, reason=err))
                for subnet in interface.ipv6_subnets:
                    gateway = subnet.gateway
                    subnet = subnet.subnet
                    if not srv6_controller_utils.validate_ipv6_address(subnet):
                        err = ('Invalid configuration for device %s\n'
                               'Invalid IPv6 subnet %s for the interface %s'
                               % (deviceid, subnet, interface.name))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=STATUS_BAD_REQUEST, reason=err))
                    if gateway is not None and gateway != '':
                        if (not srv6_controller_utils
                                .validate_ipv6_address(gateway)):
                            err = ('Invalid configuration for device %s\n'
                                   'Invalid IPv6 gateway %s for the subnet %s '
                                   'on the interface %s'
                                   % (deviceid, gateway, subnet, interface.name))
                            logging.warning(err)
                            return OverlayServiceReply(
                                status=Status(
                                    code=STATUS_BAD_REQUEST, reason=err))
            # At least one WAN interface is required
            if wan_interfaces_counter == 0:
                err = ('Invalid configuration for device %s\n'
                       'The configuration must contain at least one WAN '
                       'interface (0 provided)' % deviceid)
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # At least one LAN interface is required
            if lan_interfaces_counter == 0:
                err = ('Invalid configuration for device %s\n'
                       'The configuration must contain at least one LAN '
                       'interface (0 provided)' % deviceid)
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # All checks passed
        #
        # Extract the configurations from the request message
        new_devices = list()
        for device in request.configuration.devices:
            logging.info('Processing the configuration:\n%s' % device)
            # Parameters extraction
            #
            # Extract the device ID from the configuration
            deviceid = device.id
            # Extract the device name from the configuration
            device_name = device.name
            # Extract the device description from the configuration
            device_description = device.description
            # Extract the tenant ID
            tenantid = device.tenantid
            # Extract the device interfaces from the configuration
            interfaces = devices[deviceid]['interfaces']
            err = STATUS_OK
            for interface in device.interfaces:
                interfaces[interface.name]['name'] = interface.name
                if interface.type != '':
                    interfaces[interface.name]['type'] = interface.type
                if interface.type == srv6_controller_utils.InterfaceType.WAN:
                    if len(interface.ipv4_addrs) > 0 or \
                            len(interface.ipv6_addrs) > 0:
                        logging.warning(
                            'Cannot set IP addrs for a WAN interface')
                    if len(interface.ipv4_subnets) > 0 or \
                            len(interface.ipv6_subnets) > 0:
                        logging.warning(
                            'Cannot set subnets for a WAN interface')
                else:
                    if len(interface.ipv4_addrs) > 0:
                        addrs = list()
                        for addr in interfaces[interface.name]['ipv4_addrs']:
                            addrs.append(addr)
                        response = self.srv6_manager.remove_many_ipaddr(
                            devices[deviceid]['mgmtip'],
                            self.grpc_client_port, addrs=addrs,
                            device=interface.name, family=AF_UNSPEC
                        )
                        if response != SbStatusCode.STATUS_SUCCESS:
                            # If the operation has failed,
                            # report an error message
                            logging.warning(
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
                            if response != SbStatusCode.STATUS_SUCCESS:
                                # If the operation has failed,
                                # report an error message
                                logging.warning(
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
                        if response != SbStatusCode.STATUS_SUCCESS:
                            # If the operation has failed,
                            # report an error message
                            logging.warning(
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
                            if response != SbStatusCode.STATUS_SUCCESS:
                                # If the operation has failed,
                                # report an error message
                                logging.warning(
                                    'Cannot assign the private VPN IP address '
                                    'to the interface'
                                )
                                err = status_codes_pb2.STATUS_INTERNAL_ERROR
                            interfaces[interface.name]['ipv6_addrs'].append(
                                ipv6_addr)
                    interfaces[interface.name]['ipv4_subnets'] = list()
                    for subnet in interface.ipv4_subnets:
                        gateway = subnet.gateway
                        subnet = subnet.subnet
                        interfaces[interface.name]['ipv4_subnets'].append(
                            {'subnet': subnet, 'gateway': gateway})
                    interfaces[interface.name]['ipv6_subnets'] = list()
                    for subnet in interface.ipv6_subnets:
                        gateway = subnet.gateway
                        subnet = subnet.subnet
                        interfaces[interface.name]['ipv6_subnets'].append(
                            {'subnet': subnet, 'gateway': gateway})
            # Push the new configuration
            if err == STATUS_OK:
                logging.debug('The device %s has been configured successfully'
                              % deviceid)
                new_devices.append({
                    'deviceid': deviceid,
                    'name': device_name,
                    'description': device_description,
                    'interfaces': interfaces,
                    'configured': True
                })
            else:
                err = 'The device %s rejected the configuration' % deviceid
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
        success = srv6_sdn_controller_state.configure_devices(new_devices)
        if success is False or success is None:
            err = 'Error configuring the devices'
            logging.error(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR, reason=err))
        logging.info('The device configuration has been saved\n\n')
        # Create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    """ Get the registered devices """

    def GetDevices(self, request, context):
        logging.debug('GetDeviceInformation request received')
        # Extract the device IDs from the request
        deviceids = list(request.deviceids)
        deviceids = deviceids if len(deviceids) > 0 else None
        # Extract the tenant ID from the request
        tenantid = request.tenantid
        tenantid = tenantid if tenantid != '' else None
        # Parameters validation
        #
        # Validate the device IDs
        if deviceids is not None:
            for deviceid in deviceids:
                logging.debug('Validating the device ID: %s' % deviceid)
                if not srv6_controller_utils.validate_deviceid(deviceid):
                    # If device ID is invalid, return an error message
                    err = 'Invalid device ID: %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Validate the tenant ID
        if tenantid is not None:
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = 'Invalid tenant ID: %s' % tenantid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Create the response
        response = srv6_vpn_pb2.InventoryServiceReply()
        # Iterate on devices and fill the response message
        devices = srv6_sdn_controller_state.get_devices(
            deviceids=deviceids, tenantid=tenantid)
        if devices is None:
            err = 'Error getting devices'
            logging.error(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR, reason=err))
        for _device in devices:
            device = response.device_information.devices.add()
            device.id = text_type(_device['deviceid'])
            _interfaces = _device.get('interfaces', [])
            for ifinfo in _interfaces:
                interface = device.interfaces.add()
                interface.name = ifinfo['name']
                interface.mac_addr = ifinfo['mac_addr']
                interface.ipv4_addrs.extend(ifinfo['ipv4_addrs'])
                interface.ipv6_addrs.extend(ifinfo['ipv6_addrs'])
                interface.ext_ipv4_addrs.extend(ifinfo['ext_ipv4_addrs'])
                interface.ext_ipv6_addrs.extend(ifinfo['ext_ipv6_addrs'])
                for _subnet in ifinfo['ipv4_subnets']:
                    subnet = interface.ipv4_subnets.add()
                    subnet.subnet = _subnet['subnet']
                    subnet.gateway = _subnet['gateway']
                for _subnet in ifinfo['ipv6_subnets']:
                    subnet = interface.ipv6_subnets.add()
                    subnet.subnet = _subnet['subnet']
                    subnet.gateway = _subnet['gateway']
                interface.type = ifinfo['type']
            mgmtip = _device.get('mgmtip')
            name = _device.get('name')
            description = _device.get('description')
            connected = _device.get('connected')
            configured = _device.get('configured')
            enabled = _device.get('enabled')
            if mgmtip is not None:
                device.mgmtip = mgmtip
            if name is not None:
                device.name = name
            if description is not None:
                device.description = description
            if connected is not None:
                device.connected = connected
            if configured is not None:
                device.configured = configured
            if enabled is not None:
                device.enabled = enabled
        # Return the response
        logging.debug('Sending response:\n%s' % response)
        response.status.code = STATUS_OK
        response.status.reason = 'OK'
        return response

    """ Get the topology information """

    def GetTopologyInformation(self, request, context):
        logging.debug('GetTopologyInformation request received')
        # Create the response
        response = srv6_vpn_pb2.InventoryServiceReply()
        # Build the topology
        topology = srv6_sdn_controller_state.get_topology()
        if topology is None:
            err = 'Error getting the topology'
            logging.error(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                              reason=err))
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
        logging.debug('Sending response:\n%s' % response)
        response.status.code = STATUS_OK
        response.status.reason = 'OK'
        return response

    def _unregister_device(self, deviceid, tenantid):
        # Parameters validation
        #
        # Validate the tenant ID
        logging.debug('Validating the tenant ID: %s' % tenantid)
        tenant_exists = srv6_sdn_controller_state.tenant_exists(tenantid)
        if tenant_exists is None:
            err = 'Error while connecting to the controller state'
            logging.error(err)
            return TenantReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR, reason=err))
        elif tenant_exists is False:
            # If tenant ID is invalid, return an error message
            err = 'Tenant not found: %s' % tenantid
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        # Validate the device ID
        logging.debug('Validating the device ID: %s' % tenantid)
        devices = srv6_sdn_controller_state.get_devices(
            deviceids=[deviceid])
        if devices is None:
            err = 'Error getting devices'
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        elif len(devices) == 0:
            # If device ID is invalid, return an error message
            err = 'Device not found: %s' % deviceid
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        # The device must belong to the tenant
        device = devices[0]
        if device['tenantid'] != tenantid:
            err = ('Cannot unregister the device. '
                   'The device %s does not belong to the tenant %s'
                   % (deviceid, tenantid))
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        # Check tunnels stats
        # If the tenant has some overlays configured
        # it is not possible to unregister it
        num = srv6_sdn_controller_state.get_num_tunnels(deviceid)
        if num is None:
            err = 'Error getting tunnels stats'
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        elif num != 0:
            err = ('Cannot unregister the device %s. '
                   'The device has %s tunnels registered'
                   % (deviceid, num))
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        # All checks passed
        # Let's unregister the device
        #
        # Send shutdown command to device
        res = self.srv6_manager.shutdown_device(
            device['mgmtip'], self.grpc_client_port)
        if res != SbStatusCode.STATUS_SUCCESS:
            err = ('Cannot unregister the device. '
                   'Error while shutting down the device')
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        # Remove management information from the controller (e.g. VTEP info)
        if self.auth_controller is not None:
            res = self.auth_controller.unregister_device(deviceid, tenantid)
            if res != status_codes_pb2.STATUS_SUCCESS:
                err = ('Cannot unregister the device. '
                       'Error while removing management information')
                logging.error(err)
                return STATUS_INTERNAL_SERVER_ERROR, err
        # Remove device from controller state
        success = srv6_sdn_controller_state.unregister_device(deviceid)
        if success is None or success is False:
            err = ('Cannot unregister the device. '
                   'Error while updating the controller state')
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        # Success
        logging.info('Device unregistered successfully\n\n')
        return STATUS_OK, 'OK'

    """ Unregister a device """

    def UnregisterDevice(self, request, context):
        logging.info('UnregisterDevice request received:\n%s', request)
        # Parameters extraction
        #
        # Extract the tenant ID
        tenantid = request.tenantid
        # Extract the device ID
        deviceid = request.deviceid
        # Unregister the device
        code, reason = self._unregister_device(deviceid, tenantid)
        # Create the response
        return OverlayServiceReply(
            status=Status(code=code, reason=reason))

    """Create a VPN from an intent received through the northbound interface"""

    def CreateOverlay(self, request, context):
        logging.info('CreateOverlay request received:\n%s', request)
        # Extract the intents from the request message
        for intent in request.intents:
            logging.info('Processing the intent:\n%s' % intent)
            # Parameters extraction
            #
            # Extract the overlay tenant ID from the intent
            tenantid = intent.tenantid
            # Extract the overlay type from the intent
            overlay_type = intent.overlay_type
            # Extract the overlay name from the intent
            overlay_name = intent.overlay_name
            # Extract the interfaces
            slices = list()
            _devices = set()
            for _slice in intent.slices:
                deviceid = _slice.deviceid
                interface_name = _slice.interface_name
                # Add the slice to the slices set
                slices.append(
                    {'deviceid': deviceid, 'interface_name': interface_name})
                # Add the device to the devices set
                _devices.add(deviceid)
            # Extract tunnel mode
            tunnel_name = intent.tunnel_mode
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Parameters validation
            #
            # Validate the tenant ID
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = 'Invalid tenant ID: %s' % tenantid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Check if the tenant is configured
            is_config = (srv6_sdn_controller_state
                         .is_tenant_configured(tenantid))
            if is_config is None:
                err = 'Error while checking tenant configuration'
                logging.error(err)
                return TenantReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif is_config is False:
                err = ('Cannot create overlay for a tenant unconfigured'
                       'Tenant not found or error during the '
                       'connection to the db')
                logging.warning(err)
                return TenantReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Validate the overlay type
            logging.debug('Validating the overlay type: %s' % overlay_type)
            if not srv6_controller_utils.validate_overlay_type(overlay_type):
                # If the overlay type is invalid, return an error message
                err = 'Invalid overlay type: %s' % overlay_type
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Validate the overlay name
            logging.debug('Validating the overlay name: %s' % overlay_name)
            if not srv6_controller_utils.validate_overlay_name(overlay_name):
                # If the overlay name is invalid, return an error message
                err = 'Invalid overlay name: %s' % overlay_name
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Validate the tunnel mode
            logging.debug('Validating the tunnel mode: %s' % tunnel_name)
            if not srv6_controller_utils.validate_tunnel_mode(
                    tunnel_name, self.supported_tunnel_modes):
                # If the tunnel mode is invalid, return an error message
                err = 'Invalid tunnel mode: %s' % tunnel_name
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Let's check if the overlay does not exist
            logging.debug('Checking if the overlay name is available: %s'
                          % overlay_name)
            exists = srv6_sdn_controller_state.overlay_exists(overlay_name,
                                                              tenantid)
            if exists is True:
                # If the overlay already exists, return an error message
                err = ('Overlay name %s is already in use for tenant %s'
                       % (overlay_name, tenantid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            elif exists is None:
                err = 'Error validating the overlay'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            # Get the devices
            devices = srv6_sdn_controller_state.get_devices(
                deviceids=_devices, return_dict=True)
            if devices is None:
                err = 'Error getting devices'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            # Devices validation
            for deviceid in devices:
                # Let's check if the router exists
                if deviceid not in devices:
                    # If the device does not exist, return an error message
                    err = 'Device not found %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is connected
                if not devices[deviceid]['connected']:
                    # If the device is not connected, return an error message
                    err = 'The device %s is not connected' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is enabled
                if not devices[deviceid]['enabled']:
                    # If the device is not enabled, return an error message
                    err = 'The device %s is not enabled' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the devices have at least a WAN interface
                wan_found = False
                for interface in devices[deviceid]['interfaces']:
                    if interface['type'] == \
                            srv6_controller_utils.InterfaceType.WAN:
                        wan_found = True
                if not wan_found:
                    # No WAN interfaces found on the device
                    err = 'No WAN interfaces found on the device %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Convert interfaces list to a dict representation
            # This step simplifies future processing
            interfaces = dict()
            for deviceid in devices:
                for interface in devices[deviceid]['interfaces']:
                    interfaces[interface['name']] = interface
                devices[deviceid]['interfaces'] = interfaces
            # Validate the slices included in the intent
            for _slice in slices:
                logging.debug('Validating the slice: %s' % _slice)
                # A slice is a tuple (deviceid, interface_name)
                #
                # Extract the device ID
                deviceid = _slice['deviceid']
                # Extract the interface name
                interface_name = _slice['interface_name']
                # Let's check if the router exists
                if deviceid not in devices:
                    # If the device does not exist, return an error message
                    err = 'Device not found %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is enabled
                if not devices[deviceid]['enabled']:
                    # If the device is not enabled, return an error message
                    err = 'The device %s is not enabled' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is connected
                if not devices[deviceid]['connected']:
                    # If the device is not connected, return an error message
                    err = 'The device %s is not connected' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Let's check if the interface exists
                if interface_name not in devices[deviceid]['interfaces']:
                    # If the interface does not exists, return an error
                    # message
                    err = 'The interface does not exist'
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the interface type is LAN
                if devices[deviceid]['interfaces'][interface_name]['type'] != \
                        srv6_controller_utils.InterfaceType.LAN:
                    # The interface type is not LAN
                    err = ('Cannot add non-LAN interface to the overlay: %s '
                           '(device %s)' % (interface_name, deviceid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the slice is already assigned to an overlay
                _overlay = (srv6_sdn_controller_state
                            .get_overlay_containing_slice(_slice, tenantid))
                if _overlay is not None:
                    # Slice already assigned to an overlay
                    err = ('Cannot create overlay: the slice %s is '
                           'already assigned to the overlay %s'
                           % (_slice, _overlay['_id']))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # All the devices must belong to the same tenant
            for device in devices.values():
                if device['tenantid'] != tenantid:
                    err = ('Error while processing the intent: '
                           'All the devices must belong to the '
                           'same tenant %s' % tenantid)
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            logging.info('All checks passed')
            # All checks passed
            #
            # Save the overlay to the controller state
            overlayid = srv6_sdn_controller_state.create_overlay(
                overlay_name, overlay_type, slices, tenantid, tunnel_name)
            if overlayid is None:
                err = 'Cannot save the overlay to the controller state'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            # Get tunnel mode
            tunnel_mode = self.tunnel_modes[tunnel_name]
            # Let's create the overlay
            # Create overlay data structure
            status_code = tunnel_mode.init_overlay_data(
                overlayid, overlay_name, tenantid, tunnel_info)
            if status_code != STATUS_OK:
                err = ('Cannot initialize overlay data (overlay %s, tenant %s)'
                       % (overlay_name, tenantid))
                logging.warning(err)
                # Remove overlay DB status
                if srv6_sdn_controller_state.remove_overlay(
                        overlayid) is not True:
                    logging.error('Cannot remove overlay. Inconsistent data')
                return OverlayServiceReply(
                    status=Status(code=status_code, reason=err))
            # Iterate on slices and add to the overlay
            configured_slices = list()
            for site1 in slices:
                deviceid = site1['deviceid']
                interface_name = site1['interface_name']
                # Init tunnel mode on the devices
                counter = (srv6_sdn_controller_state
                           .get_and_inc_tunnel_mode_counter(tunnel_name,
                                                            deviceid))
                if counter == 0:
                    status_code = tunnel_mode.init_tunnel_mode(
                        deviceid, tenantid, tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot initialize tunnel mode (device %s '
                               'tenant %s)' % (deviceid, tenantid))
                        logging.warning(err)
                        # Remove overlay DB status
                        if srv6_sdn_controller_state.remove_overlay(
                                overlayid) is not True:
                            logging.error(
                                'Cannot remove overlay. Inconsistent data')
                        return OverlayServiceReply(
                            status=Status(code=status_code, reason=err))
                elif counter is None:
                    err = 'Cannot increase tunnel mode counter'
                    logging.error(err)
                    # Remove overlay DB status
                    if srv6_sdn_controller_state.remove_overlay(
                            overlayid) is not True:
                        logging.error(
                            'Cannot remove overlay. Inconsistent data')
                    return OverlayServiceReply(
                        status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                      reason=err))
                # Check if we have already configured the overlay on the device
                if deviceid in _devices:
                    # Init overlay on the devices
                    status_code = tunnel_mode.init_overlay(overlayid,
                                                           overlay_name,
                                                           overlay_type,
                                                           tenantid, deviceid,
                                                           tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot initialize overlay (overlay %s '
                               'device %s, tenant %s)'
                               % (overlay_name, deviceid, tenantid))
                        logging.warning(err)
                        # Remove overlay DB status
                        if srv6_sdn_controller_state.remove_overlay(
                                overlayid) is not True:
                            logging.error(
                                'Cannot remove overlay. Inconsistent data')
                        return OverlayServiceReply(
                            status=Status(code=status_code, reason=err))
                    # Remove device from the to-be-configured devices set
                    _devices.remove(deviceid)
                # Add the interface to the overlay
                status_code = (tunnel_mode
                               .add_slice_to_overlay(overlayid,
                                                     overlay_name, deviceid,
                                                     interface_name, tenantid,
                                                     tunnel_info))
                if status_code != STATUS_OK:
                    err = ('Cannot add slice to overlay (overlay %s, '
                           'device %s, slice %s, tenant %s)'
                           % (overlay_name, deviceid,
                              interface_name, tenantid))
                    logging.warning(err)
                    # Remove overlay DB status
                    if srv6_sdn_controller_state.remove_overlay(
                            overlayid) is not True:
                        logging.error(
                            'Cannot remove overlay. Inconsistent data')
                    return OverlayServiceReply(
                        status=Status(code=status_code, reason=err))
                # Create the tunnel between all the pairs of interfaces
                for site2 in configured_slices:
                    if site1['deviceid'] != site2['deviceid']:
                        status_code = tunnel_mode.create_tunnel(overlayid,
                                                                overlay_name,
                                                                overlay_type,
                                                                site1, site2,
                                                                tenantid,
                                                                tunnel_info)
                        if status_code != STATUS_OK:
                            err = ('Cannot create tunnel (overlay %s site1 %s '
                                   'site2 %s, tenant %s)'
                                   % (overlay_name, site1, site2, tenantid))
                            logging.warning(err)
                            # Remove overlay DB status
                            if srv6_sdn_controller_state.remove_overlay(
                                    overlayid) is not True:
                                logging.error(
                                    'Cannot remove overlay. Inconsistent data')
                            return OverlayServiceReply(
                                status=Status(code=status_code, reason=err))
                # Add the slice to the configured set
                configured_slices.append(site1)
        logging.info('All the intents have been processed successfully\n\n')
        # Create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    """Remove a VPN"""

    def RemoveOverlay(self, request, context):
        logging.info('RemoveOverlay request received:\n%s', request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the overlay ID from the intent
            overlayid = intent.overlayid
            # Extract the tenant ID from the intent
            tenantid = intent.tenantid
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Validate the tenant ID
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = 'Invalid tenant ID: %s' % tenantid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Check if the tenant is configured
            is_config = (srv6_sdn_controller_state
                         .is_tenant_configured(tenantid))
            if is_config is None:
                err = 'Error while checking tenant configuration'
                logging.error(err)
                return TenantReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif is_config is False:
                err = ('Cannot remove overlay for a tenant unconfigured'
                       'Tenant not found or error during the '
                       'connection to the db')
                logging.warning(err)
                return TenantReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Remove VPN
            code, reason = self._RemoveOverlay(
                overlayid, tenantid, tunnel_info)
            if code != STATUS_OK:
                return OverlayServiceReply(
                    status=Status(code=code, reason=reason))
        logging.info('All the intents have been processed successfully\n\n')
        # Create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    def _RemoveOverlay(self, overlayid, tenantid, tunnel_info):
        # Parameters validation
        #
        # Let's check if the overlay exists
        logging.debug('Checking the overlay: %s' % overlayid)
        overlays = srv6_sdn_controller_state.get_overlays(
            overlayids=[overlayid])
        if overlays is None:
            err = 'Error getting the overlay'
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        elif len(overlays) == 0:
            # If the overlay does not exist, return an error message
            err = 'The overlay %s does not exist' % overlayid
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        overlay = overlays[0]
        # Get the tenant ID
        tenantid = overlay['tenantid']
        # Check tenant ID
        if tenantid != overlay['tenantid']:
            # If the overlay does not exist, return an error message
            err = ('The overlay %s does not belong to the tenant %s'
                   % (overlayid, tenantid))
            logging.warning(err)
            return STATUS_BAD_REQUEST, err
        # Get the overlay name
        overlay_name = overlay['name']
        # Get the overlay type
        overlay_type = overlay['type']
        # Get the tunnel mode
        tunnel_name = overlay['tunnel_mode']
        tunnel_mode = self.tunnel_modes[tunnel_name]
        # Get the slices belonging to the overlay
        slices = overlay['slices']
        # All checks passed
        logging.debug('Check passed')
        # Let's remove the VPN
        devices = [slice['deviceid'] for slice in overlay['slices']]
        configured_slices = slices.copy()
        for site1 in slices:
            deviceid = site1['deviceid']
            interface_name = site1['interface_name']
            # Remove the tunnel between all the pairs of interfaces
            for site2 in configured_slices:
                if site1['deviceid'] != site2['deviceid']:
                    status_code = tunnel_mode.remove_tunnel(
                        overlayid, overlay_name, overlay_type, site1,
                        site2, tenantid, tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot create tunnel (overlay %s site1 %s '
                               'site2 %s, tenant %s)'
                               % (overlay_name, site1, site2, tenantid))
                        logging.warning(err)
                        return status_code, err
            # Mark the site1 as unconfigured
            configured_slices.remove(site1)
            # Remove the interface from the overlay
            status_code = tunnel_mode.remove_slice_from_overlay(overlayid,
                                                                overlay_name,
                                                                deviceid,
                                                                interface_name,
                                                                tenantid,
                                                                tunnel_info)
            if status_code != STATUS_OK:
                err = ('Cannot remove slice from overlay (overlay %s, '
                       'device %s, slice %s, tenant %s)'
                       % (overlay_name, deviceid, interface_name, tenantid))
                logging.warning(err)
                return status_code, err
            # Check if the overlay and the tunnel mode
            # has already been deleted on the device
            devices.remove(deviceid)
            if deviceid not in devices:
                # Destroy overlay on the devices
                status_code = tunnel_mode.destroy_overlay(overlayid,
                                                          overlay_name,
                                                          overlay_type,
                                                          tenantid,
                                                          deviceid,
                                                          tunnel_info)
                if status_code != STATUS_OK:
                    err = ('Cannot destroy overlay (overlay %s, device %s '
                           'tenant %s)' % (overlay_name, deviceid, tenantid))
                    logging.warning(err)
                    return status_code, err
            # Destroy tunnel mode on the devices
            counter = (srv6_sdn_controller_state
                       .dec_and_get_tunnel_mode_counter(tunnel_name,
                                                        deviceid))
            if counter == 0:
                status_code = tunnel_mode.destroy_tunnel_mode(
                    deviceid, tenantid, tunnel_info)
                if status_code != STATUS_OK:
                    err = ('Cannot destroy tunnel mode (device %s, tenant %s)'
                           % (deviceid, tenantid))
                    logging.warning(err)
                    return status_code, err
            elif counter is None:
                err = 'Cannot decrease tunnel mode counter'
                logging.error(err)
                return STATUS_INTERNAL_SERVER_ERROR, err
        # Destroy overlay data structure
        status_code = tunnel_mode.destroy_overlay_data(
            overlayid, overlay_name, tenantid, tunnel_info)
        if status_code != STATUS_OK:
            err = ('Cannot destroy overlay data (overlay %s, tenant %s)'
                   % (overlay_name, tenantid))
            logging.warning(err)
            return status_code, err
        # Delete the overlay
        success = srv6_sdn_controller_state.remove_overlay(overlayid)
        if success is None or success is False:
            err = 'Cannot remove the overlay from the controller state'
            logging.error(err)
            return STATUS_INTERNAL_SERVER_ERROR, err
        # Create the response
        return STATUS_OK, 'OK'

    """Assign an interface to a VPN"""

    def AssignSliceToOverlay(self, request, context):
        logging.info('AssignSliceToOverlay request received:\n%s' % request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the overlay ID from the intent
            overlayid = intent.overlayid
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Extract tenant ID
            tenantid = intent.tenantid
            # Validate the tenant ID
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = 'Invalid tenant ID: %s' % tenantid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Check if the tenant is configured
            is_config = (srv6_sdn_controller_state
                         .is_tenant_configured(tenantid))
            if is_config is None:
                err = 'Error while checking tenant configuration'
                logging.error(err)
                return TenantReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif is_config is False:
                err = ('Cannot update overlay for a tenant unconfigured. '
                       'Tenant not found or error during the '
                       'connection to the db')
                logging.warning(err)
                return TenantReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Get the overlay
            overlays = srv6_sdn_controller_state.get_overlays(
                overlayids=[overlayid])
            if overlays is None:
                err = 'Error getting the overlay'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif len(overlays) == 0:
                # If the overlay does not exist, return an error message
                err = 'The overlay %s does not exist' % overlayid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Take the first overlay
            overlay = overlays[0]
            # Check tenant ID
            if tenantid != overlay['tenantid']:
                # If the overlay does not exist, return an error message
                err = ('The overlay %s does not belong to the '
                       'tenant %s' % (overlayid, tenantid))
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Get the overlay name
            overlay_name = overlay['name']
            # Get the overlay type
            overlay_type = overlay['type']
            # Get the tunnel mode
            tunnel_name = overlay['tunnel_mode']
            tunnel_mode = self.tunnel_modes[tunnel_name]
            # Get the slices belonging to the overlay
            slices = overlay['slices']
            # Get the devices on which the overlay has been configured
            _devices = [_slice['deviceid'] for _slice in slices]
            # Extract the interfaces
            incoming_slices = list()
            incoming_devices = set()
            for _slice in intent.slices:
                deviceid = _slice.deviceid
                interface_name = _slice.interface_name
                # Add the slice to the incoming slices set
                incoming_slices.append(
                    {'deviceid': deviceid, 'interface_name': interface_name})
                # Add the device to the incoming devices set
                # if the overlay has not been initiated on it
                if deviceid not in _devices:
                    incoming_devices.add(deviceid)
            # Parameters validation
            #
            # Let's check if the overlay exists
            logging.debug('Checking the overlay: %s' % overlay_name)
            # Get the devices
            devices = srv6_sdn_controller_state.get_devices(
                deviceids=list(incoming_devices) + _devices, return_dict=True)
            if devices is None:
                err = 'Error getting devices'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            # Devices validation
            for deviceid in devices:
                # Let's check if the router exists
                if deviceid not in devices:
                    # If the device does not exist, return an error message
                    err = 'Device not found %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is enabled
                if not devices[deviceid]['enabled']:
                    # If the device is not enabled, return an error message
                    err = 'The device %s is not enabled' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is connected
                if not devices[deviceid]['connected']:
                    # If the device is not connected, return an error message
                    err = 'The device %s is not connected' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the devices have at least a WAN interface
                wan_found = False
                for interface in devices[deviceid]['interfaces']:
                    if interface['type'] == \
                            srv6_controller_utils.InterfaceType.WAN:
                        wan_found = True
                if not wan_found:
                    # No WAN interfaces found on the device
                    err = 'No WAN interfaces found on the device %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Convert interfaces list to a dict representation
            # This step simplifies future processing
            interfaces = dict()
            for deviceid in devices:
                for interface in devices[deviceid]['interfaces']:
                    interfaces[interface['name']] = interface
                devices[deviceid]['interfaces'] = interfaces
            # Iterate on the interfaces and extract the
            # interfaces to be assigned
            # to the overlay and validate them
            for _slice in incoming_slices:
                logging.debug('Validating the slice: %s' % _slice)
                # A slice is a tuple (deviceid, interface_name)
                #
                # Extract the device ID
                deviceid = _slice['deviceid']
                # Extract the interface name
                interface_name = _slice['interface_name']
                # Let's check if the interface exists
                if interface_name not in devices[deviceid]['interfaces']:
                    # If the interface does not exists, return an error
                    # message
                    err = 'The interface does not exist'
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the interface type is LAN
                if devices[deviceid]['interfaces'][interface_name]['type'] != \
                        srv6_controller_utils.InterfaceType.LAN:
                    # The interface type is not LAN
                    err = ('Cannot add non-LAN interface to the overlay: %s '
                           '(device %s)' % (interface_name, deviceid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the slice is already assigned to an overlay
                _overlay = (srv6_sdn_controller_state
                            .get_overlay_containing_slice(_slice, tenantid))
                if _overlay is not None:
                    # Slice already assigned to an overlay
                    err = ('Cannot create overlay: the slice %s is '
                           'already assigned to the overlay %s'
                           % (_slice, _overlay['_id']))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # All the devices must belong to the same tenant
            for device in devices.values():
                if device['tenantid'] != tenantid:
                    err = 'Error while processing the intent: '
                    'All the devices must belong to the '
                    'same tenant %s' % tenantid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            logging.info('All checks passed')
            # All checks passed
            #
            # Let's assign the interface to the overlay
            configured_slices = slices
            for site1 in incoming_slices:
                deviceid = site1['deviceid']
                interface_name = site1['interface_name']
                # Init tunnel mode on the devices
                counter = (srv6_sdn_controller_state
                           .get_and_inc_tunnel_mode_counter(tunnel_name,
                                                            deviceid))
                if counter == 0:
                    status_code = tunnel_mode.init_tunnel_mode(
                        deviceid, tenantid, tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot initialize tunnel mode (device %s '
                               'tenant %s)' % (deviceid, tenantid))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=status_code, reason=err))
                elif counter is None:
                    err = 'Cannot increase tunnel mode counter'
                    logging.error(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                      reason=err))
                # Check if we have already configured the overlay on the device
                if deviceid in incoming_devices:
                    # Init overlay on the devices
                    status_code = tunnel_mode.init_overlay(overlayid,
                                                           overlay_name,
                                                           overlay_type,
                                                           tenantid, deviceid,
                                                           tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot initialize overlay (overlay %s '
                               'device %s, tenant %s)'
                               % (overlay_name, deviceid, tenantid))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=status_code, reason=err))
                    # Remove device from the to-be-configured devices set
                    incoming_devices.remove(deviceid)
                # Add the interface to the overlay
                status_code = tunnel_mode.add_slice_to_overlay(overlayid,
                                                               overlay_name,
                                                               deviceid,
                                                               interface_name,
                                                               tenantid,
                                                               tunnel_info)
                if status_code != STATUS_OK:
                    err = ('Cannot add slice to overlay (overlay %s, '
                           'device %s, slice %s, tenant %s)'
                           % (overlay_name, deviceid,
                              interface_name, tenantid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=status_code, reason=err))
                # Create the tunnel between all the pairs of interfaces
                for site2 in configured_slices:
                    if site1['deviceid'] != site2['deviceid']:
                        status_code = tunnel_mode.create_tunnel(overlayid,
                                                                overlay_name,
                                                                overlay_type,
                                                                site1, site2,
                                                                tenantid,
                                                                tunnel_info)
                        if status_code != STATUS_OK:
                            err = ('Cannot create tunnel (overlay %s site1 %s '
                                   'site2 %s, tenant %s)'
                                   % (overlay_name, site1, site2, tenantid))
                            logging.warning(err)
                            return OverlayServiceReply(
                                status=Status(code=status_code, reason=err))
                # Add the slice to the configured set
                configured_slices.append(site1)
            # Save the overlay to the state
            success = srv6_sdn_controller_state.add_many_slices_to_overlay(
                overlayid, incoming_slices)
            if success is None or success is False:
                err = 'Cannot update overlay in controller state'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
        logging.info('All the intents have been processed successfully\n\n')
        # Create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    """Remove an interface from a VPN"""

    def RemoveSliceFromOverlay(self, request, context):
        logging.info('RemoveSliceFromOverlay request received:\n%s' % request)
        # Extract the intents from the request message
        for intent in request.intents:
            # Parameters extraction
            #
            # Extract the overlay ID from the intent
            overlayid = intent.overlayid
            # Extract tunnel info
            tunnel_info = intent.tunnel_info
            # Extract tenant ID
            tenantid = intent.tenantid
            # Validate the tenant ID
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = 'Invalid tenant ID: %s' % tenantid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Check if the tenant is configured
            is_config = (srv6_sdn_controller_state
                         .is_tenant_configured(tenantid))
            if is_config is None:
                err = 'Error while checking tenant configuration'
                logging.error(err)
                return TenantReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif is_config is False:
                err = ('Cannot update overlay for a tenant unconfigured'
                       'Tenant not found or error during the '
                       'connection to the db')
                logging.warning(err)
                return TenantReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Let's check if the overlay exists
            logging.debug('Checking the overlay: %s' % overlayid)
            overlays = srv6_sdn_controller_state.get_overlays(overlayids=[
                overlayid])
            if overlays is None:
                err = 'Error getting the overlay'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            elif len(overlays) == 0:
                # If the overlay does not exist, return an error message
                err = 'The overlay %s does not exist' % overlayid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Take the first overlay
            overlay = overlays[0]
            # Check tenant ID
            if tenantid != overlay['tenantid']:
                # If the overlay does not exist, return an error message
                err = 'The overlay %s does not belong to the '
                'tenant %s' % (overlayid, tenantid)
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # Get the overlay name
            overlay_name = overlay['name']
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
                deviceid = _slice.deviceid
                interface_name = _slice.interface_name
                # Add the slice to the incoming slices set
                incoming_slices.append(
                    {'deviceid': deviceid, 'interface_name': interface_name})
                # Add the device to the incoming devices set
                # if the overlay has not been initiated on it
                if deviceid not in incoming_devices:
                    incoming_devices.add(deviceid)
            # Get the devices
            devices = srv6_sdn_controller_state.get_devices(
                deviceids=incoming_devices, return_dict=True)
            if devices is None:
                err = 'Error getting devices'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
            # Convert interfaces list to a dict representation
            # This step simplifies future processing
            interfaces = dict()
            for deviceid in devices:
                for interface in devices[deviceid]['interfaces']:
                    interfaces[interface['name']] = interface
                devices[deviceid]['interfaces'] = interfaces
            # Parameters validation
            #
            # Iterate on the interfaces
            # and extract the interfaces to be removed from the VPN
            for _slice in incoming_slices:
                logging.debug('Validating the slice: %s' % _slice)
                # A slice is a tuple (deviceid, interface_name)
                #
                # Extract the device ID
                deviceid = _slice['deviceid']
                # Extract the interface name
                interface_name = _slice['interface_name']
                # Let's check if the router exists
                if deviceid not in devices:
                    # If the device does not exist, return an error message
                    err = 'Device not found %s' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is connected
                if not devices[deviceid]['connected']:
                    # If the device is not connected, return an error message
                    err = 'The device %s is not connected' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Check if the device is enabled
                if not devices[deviceid]['enabled']:
                    # If the device is not enabled, return an error message
                    err = 'The device %s is not enabled' % deviceid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Let's check if the interface exists
                if interface_name not in devices[deviceid]['interfaces']:
                    # If the interface does not exists, return an error
                    # message
                    err = 'The interface does not exist'
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
                # Let's check if the interface is assigned to the given overlay
                if _slice not in overlay['slices']:
                    # The interface is not assigned to the overlay,
                    # return an error message
                    err = ('The interface is not assigned to the overlay %s, '
                           '(name %s, tenantid %s)'
                           % (overlayid, overlay_name, tenantid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            # All the devices must belong to the same tenant
            for device in devices.values():
                if device['tenantid'] != tenantid:
                    err = 'Error while processing the intent: '
                    'All the devices must belong to the '
                    'same tenant %s' % tenantid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
            logging.debug('All checks passed')
            # All checks passed
            #
            # Let's remove the interface from the VPN
            _devices = [slice['deviceid'] for slice in overlay['slices']]
            configured_slices = slices.copy()
            for site1 in incoming_slices:
                deviceid = site1['deviceid']
                interface_name = site1['interface_name']
                # Remove the tunnel between all the pairs of interfaces
                for site2 in configured_slices:
                    if site1['deviceid'] != site2['deviceid']:
                        status_code = tunnel_mode.remove_tunnel(
                            overlayid, overlay_name, overlay_type, site1,
                            site2, tenantid, tunnel_info)
                        if status_code != STATUS_OK:
                            err = ('Cannot create tunnel (overlay %s site1 %s '
                                   'site2 %s, tenant %s)'
                                   % (overlay_name, site1, site2, tenantid))
                            logging.warning(err)
                            return OverlayServiceReply(
                                status=Status(code=status_code, reason=err))
                # Mark the site1 as unconfigured
                configured_slices.remove(site1)
                # Remove the interface from the overlay
                status_code = tunnel_mode.remove_slice_from_overlay(
                    overlayid, overlay_name, deviceid,
                    interface_name, tenantid, tunnel_info)
                if status_code != STATUS_OK:
                    err = ('Cannot remove slice from overlay (overlay %s, '
                           'device %s, slice %s, tenant %s)'
                           % (overlay_name, deviceid,
                              interface_name, tenantid))
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=status_code, reason=err))
                # Check if the overlay and the tunnel mode
                # has already been deleted on the device
                _devices.remove(deviceid)
                if deviceid not in _devices:
                    # Destroy overlay on the devices
                    status_code = tunnel_mode.destroy_overlay(overlayid,
                                                              overlay_name,
                                                              overlay_type,
                                                              tenantid,
                                                              deviceid,
                                                              tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot destroy overlay (overlay %s, device %s '
                               'tenant %s)'
                               % (overlay_name, deviceid, tenantid))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=status_code, reason=err))
                # Destroy tunnel mode on the devices
                counter = (srv6_sdn_controller_state
                           .dec_and_get_tunnel_mode_counter(tunnel_name,
                                                            deviceid))
                if counter == 0:
                    status_code = tunnel_mode.destroy_tunnel_mode(
                        deviceid, tenantid, tunnel_info)
                    if status_code != STATUS_OK:
                        err = ('Cannot destroy tunnel mode (device %s '
                               'tenant %s)' % (deviceid, tenantid))
                        logging.warning(err)
                        return OverlayServiceReply(
                            status=Status(code=status_code, reason=err))
                elif counter is None:
                    err = 'Cannot decrease tunnel mode counter'
                    logging.error(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                      reason=err))
            # Save the overlay to the state
            success = (srv6_sdn_controller_state
                       .remove_many_slices_from_overlay(
                           overlayid, incoming_slices))
            if success is None or success is False:
                err = 'Cannot update overlay in controller state'
                logging.error(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_INTERNAL_SERVER_ERROR,
                                  reason=err))
        logging.info('All the intents have been processed successfully\n\n')
        # Create the response
        return OverlayServiceReply(
            status=Status(code=STATUS_OK, reason='OK'))

    # Get VPNs from the controller inventory
    def GetOverlays(self, request, context):
        logging.debug('GetOverlays request received')
        # Extract the overlay IDs from the request
        overlayids = list(request.overlayids)
        overlayids = overlayids if len(overlayids) > 0 else None
        # Extract the tenant ID
        tenantid = request.tenantid
        tenantid = tenantid if tenantid != '' else None
        # Parameters validation
        #
        # Validate the overlay IDs
        if overlayids is not None:
            for overlayid in overlayids:
                logging.debug('Validating the overlay ID: %s' % overlayid)
                if not srv6_controller_utils.validate_overlayid(overlayid):
                    # If overlay ID is invalid, return an error message
                    err = 'Invalid overlay ID: %s' % overlayid
                    logging.warning(err)
                    return OverlayServiceReply(
                        status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Validate the tenant ID
        if tenantid is not None:
            logging.debug('Validating the tenant ID: %s' % tenantid)
            if not srv6_controller_utils.validate_tenantid(tenantid):
                # If tenant ID is invalid, return an error message
                err = 'Invalid tenant ID: %s' % tenantid
                logging.warning(err)
                return OverlayServiceReply(
                    status=Status(code=STATUS_BAD_REQUEST, reason=err))
        # Create the response
        response = OverlayServiceReply()
        # Build the overlays list
        overlays = srv6_sdn_controller_state.get_overlays(
            overlayids=overlayids, tenantid=tenantid)
        if overlays is None:
            err = 'Error getting overlays'
            logging.error(err)
            return OverlayServiceReply(
                status=Status(code=STATUS_INTERNAL_SERVER_ERROR, reason=err))
        for _overlay in overlays:
            # Add a new overlay to the overlays list
            overlay = response.overlays.add()
            # Set overlay ID
            overlay.overlayid = str(_overlay['_id'])
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
                __slice.deviceid = _slice['deviceid']
                # Add interface name
                __slice.interface_name = _slice['interface_name']
        # Return the overlays list
        logging.debug('Sending response:\n%s' % response)
        response.status.code = STATUS_OK
        response.status.reason = 'OK'
        return response


# Start gRPC server
def start_server(grpc_server_ip=DEFAULT_GRPC_SERVER_IP,
                 grpc_server_port=DEFAULT_GRPC_SERVER_PORT,
                 grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 nb_secure=DEFAULT_SECURE, server_key=DEFAULT_KEY,
                 server_certificate=DEFAULT_CERTIFICATE,
                 sb_secure=DEFAULT_SECURE,
                 client_certificate=DEFAULT_CERTIFICATE,
                 southbound_interface=DEFAULT_SB_INTERFACE,
                 topo_graph=None, vpn_dict=None,
                 devices=None,
                 vpn_file=DEFAULT_VPN_DUMP,
                 controller_state=None,
                 auth_controller=None,
                 verbose=DEFAULT_VERBOSE):
    # Initialize controller state
    # controller_state = srv6_controller_utils.ControllerState(
    #    topology=topo_graph,
    #    devices=devices,
    #    vpn_dict=vpn_dict,
    #    vpn_file=vpn_file
    # )
    # Create SRv6 Manager
    srv6_manager = sb_grpc_client.SRv6Manager(secure=sb_secure,
                                              certificate=client_certificate)
    # Setup gRPC server
    #
    # Create the server and add the handler
    grpc_server = grpc.server(futures.ThreadPoolExecutor())
    service = NorthboundInterface(
        grpc_client_port=grpc_client_port,
        srv6_manager=srv6_manager,
        southbound_interface=southbound_interface,
        auth_controller=auth_controller,
        verbose=verbose
    )
    srv6_vpn_pb2_grpc.add_NorthboundInterfaceServicer_to_server(
        service, grpc_server
    )
    # If secure mode is enabled, we need to create a secure endpoint
    if nb_secure:
        # Read key and certificate
        with open(server_key, 'rb') as f:
            key = f.read()
        with open(server_certificate, 'rb') as f:
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
    logging.info('Listening gRPC')
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
        logging.getLogger().setLevel(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger().setLevel(level=logging.INFO)
    # Debug settings
    SERVER_DEBUG = logging.getEffectiveLevel() == logging.DEBUG
    logging.info('SERVER_DEBUG:' + str(SERVER_DEBUG))
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
        logging.warning(
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
            None, verbose
        )
        while True:
            time.sleep(5)
    else:
        print('Invalid topology')
