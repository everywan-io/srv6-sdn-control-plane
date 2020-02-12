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
# Client of a Northbound interface based on gRPC protocol
#
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#

from __future__ import absolute_import, division, print_function

# General imports
from six import text_type
import grpc
import sys
from socket import AF_INET, AF_INET6

from srv6_sdn_control_plane import srv6_controller_utils

# Add path of proto files
# sys.path.append(srv6_controller_utils.PROTO_FOLDER)

# SRv6 dependencies
from srv6_sdn_proto import srv6_vpn_pb2_grpc
from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import status_codes_pb2
from srv6_sdn_proto import empty_req_pb2

# The IP address and port of the gRPC server started on the SDN controller
#IP_ADDRESS = '2000::a'
#IP_PORT = 12345
# Define wheter to use SSL or not
DEFAULT_SECURE = False
# SSL cerificate for server validation
DEFAULT_CERTIFICATE = 'cert_client.pem'


STATUS_CODES_TO_DESCR = {
    status_codes_pb2.STATUS_SUCCESS: 'OK',
    status_codes_pb2.STATUS_TOPO_NOTFOUND: 'Cannot import the topology',
    status_codes_pb2.STATUS_VPN_INVALID_TENANTID: 'Invalid tenant ID',
    status_codes_pb2.STATUS_VPN_INVALID_TYPE: 'Invalid VPN type',
    status_codes_pb2.STATUS_VPN_NAME_UNAVAILABLE: 'VPN name is already in use',
    status_codes_pb2.STATUS_ROUTER_NOTFOUND: 'The topology does not contain the router',
    status_codes_pb2.STATUS_VPN_INVALID_IP: 'Invalid IP adderess',
    status_codes_pb2.STATUS_VPN_INVALID_PREFIX: 'Invalid VPN prefix',
    status_codes_pb2.STATUS_VPN_NOTFOUND: 'The VPN does not exist',
    status_codes_pb2.STATUS_INTF_NOTFOUND: 'The interface does not exist',
    status_codes_pb2.STATUS_INTF_ALREADY_ASSIGNED: 'The interface is already assigned to a VPN',
    status_codes_pb2.STATUS_INTF_NOTASSIGNED: 'The interface is not assigned to the VPN',
    status_codes_pb2.STATUS_INTERNAL_ERROR: 'Internal error'
}

STR_TO_VPN_TYPE = {
    'IPv4VPN': srv6_vpn_pb2.IPv4Overlay,
    'IPv6VPN': srv6_vpn_pb2.IPv6Overlay
}


# ENCAP = {
#    'SRv6': srv6_vpn_pb2.SRv6,
#    'IPsec_ESP_GRE': srv6_vpn_pb2.IPsec_ESP_GRE,
#    'SRv6_IPsec_ESP_GRE': srv6_vpn_pb2.SRv6_IPsec_ESP_GRE,
#    'SRv6_IPsec_ESP_IP': srv6_vpn_pb2.SRv6_IPsec_ESP_IP
# }


class NorthboundInterface:

    def __init__(self, server_ip, server_port,
                 secure=DEFAULT_SECURE, certificate=DEFAULT_CERTIFICATE):
        self.server_ip = server_ip
        self.server_port = server_port
        self.SECURE = secure
        if secure is True:
            if certificate is None:
                print('Error: "certificate" variable cannot be None '
                      'in secure mode')
                sys.exit(-2)
            self.certificate = certificate

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        addr_family = srv6_controller_utils.getAddressFamily(ip_address)
        if addr_family == AF_INET6:
            ip_address = "ipv6:[%s]:%s" % (ip_address, port)
        elif addr_family == AF_INET:
            ip_address = "ipv4:%s:%s" % (ip_address, port)
        else:
            print('Invalid address: %s' % ip_address)
            return
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(self.certificate) as f:
                certificate = f.read()
            # Then create the SSL credentials and establish the channel
            grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
            channel = grpc.secure_channel(ip_address,
                                          grpc_client_credentials)
        else:
            channel = grpc.insecure_channel(ip_address)
        return srv6_vpn_pb2_grpc.NorthboundInterfaceStub(channel), channel

    def configure_tenant(self, port, info):
        # Create request
        request = srv6_vpn_pb2.Tenant()
        request.port = port
        request.info = info
        # Get the reference of the stub
        srv6_vpn_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Configure the tenant
        response = srv6_vpn_stub.ConfigureTenant(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status, response.token, response.tenantid

    def remove_tenant(self, token):
        # Create request
        request = srv6_vpn_pb2.RemoveTenantRequest()
        request.token = token
        # Get the reference of the stub
        srv6_vpn_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Remove tenant
        response = srv6_vpn_stub.RemoveTenant(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status

    def configure_device(self, device_id, tenantid, device_name='',
                         device_description='', interfaces=[]):
        # Create the request
        request = srv6_vpn_pb2.ConfigureDeviceRequest()
        device = request.configuration.devices.add()
        device.id = device_id
        device.name = device_name
        device.description = device_description
        device.tenantid = tenantid
        for _interface in interfaces:
            interface = device.interfaces.add()
            interface.name = _interface['name']
            if 'addrs' in _interface:
                for ip_addr in _interface['addrs']:
                    addr = ip_addr.split('/')[0]
                    family = srv6_controller_utils.getAddressFamily(addr)
                    if family == AF_INET:
                        interface.ipv4_addrs.append(ip_addr)
                    elif family == AF_INET6:
                        interface.ipv6_addrs.append(ip_addr)
                    else:
                        print('Provided an invalid address: %s' % addr)
                        return None
            if 'subnets' in _interface:
                for subnet in _interface['subnets']:
                    family = srv6_controller_utils.getAddressFamily(subnet)
                    if family == AF_INET:
                        interface.ipv4_subnets.append(subnet)
                    elif family == AF_INET6:
                        interface.ipv6_subnets.append(subnet)
                    else:
                        print('Provided an invalid subnet: %s' % subnet)
                        return None
            if 'type' in _interface:
                interface.type = _interface['type']
        # Get the reference of the stub
        srv6_vpn_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Configure the devices
        response = srv6_vpn_stub.ConfigureDevice(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status

    def get_devices(self, devices=[], tenantid=''):
        # Create the request
        request = srv6_vpn_pb2.InventoryServiceRequest()
        request.deviceids.extend(devices)
        request.tenantid = tenantid
        # Get the reference of the stub
        srv6_vpn_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Get VPNs
        response = srv6_vpn_stub.GetDevices(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve devices information
            devices = list()
            for device in response.device_information.devices:
                device_id = None
                loopbackip = None
                loopbacknet = None
                managementip = None
                interfaces = None
                mgmtip = None
                if device.id is not None:
                    device_id = text_type(device.id)
                if device.mgmtip is not None:
                    mgmtip = text_type(device.mgmtip)
                if device.name is not None:
                    device_name = text_type(device.name)
                if device.description is not None:
                    device_description = text_type(device.description)
                if device.status is not None:
                    device_status = text_type(device.status)
                '''
                if device.loopbackip is not None:
                    loopbackip = text_type(device.loopbackip)
                if device.loopbacknet is not None:
                    loopbacknet = text_type(device.loopbacknet)
                if device.managementip is not None:
                    managementip = text_type(device.managementip)
                if device.interfaces is not None:
                    interfaces = list()
                    for intf in device.interfaces:
                        ipaddrs = list()
                        for ipaddr in intf.ipaddrs:
                            ipaddrs.append(ipaddr)
                        interfaces.append({
                            'ifindex': text_type(intf.index),
                            'ifname': text_type(intf.name),
                            'macaddr': text_type(intf.macaddr),
                            'ipaddrs': intf.ipaddrs,
                            'state': text_type(intf.state),
                        })
                '''
                interfaces = dict()
                if device.interfaces is not None:
                    for intf in device.interfaces:
                        ifname = intf.name
                        type = intf.type
                        mac_addr = intf.mac_addr
                        ipv4_addrs = list()
                        ipv4_addrs = intf.ipv4_addrs
                        ipv6_addrs = intf.ipv6_addrs
                        ext_ipv4_addrs = intf.ext_ipv4_addrs
                        ext_ipv6_addrs = intf.ext_ipv6_addrs
                        ipv4_subnets = intf.ipv4_subnets
                        ipv6_subnets = intf.ipv6_subnets
                        interfaces[ifname] = {
                            'mac_addr': mac_addr,
                            'ipv4_addrs': ipv4_addrs,
                            'ipv6_addrs': ipv6_addrs,
                            'ext_ipv4_addrs': ext_ipv4_addrs,
                            'ext_ipv6_addrs': ext_ipv6_addrs,
                            'ipv4_subnets': ipv4_subnets,
                            'ipv6_subnets': ipv6_subnets,
                            'type': type
                        }
                devices.append({
                    'device_id': device_id,
                    'loopbackip': loopbackip,
                    'loopbacknet': loopbacknet,
                    'managementip': managementip,
                    'interfaces': interfaces,
                    'mgmtip': mgmtip,
                    'name': device_name,
                    'description': device_description,
                    'status': device_status
                })
        else:
            devices = None
        # Let's close the session
        channel.close()
        return devices

    def get_topology_information(self, server_ip, server_port):
        # Create the request
        request = srv6_vpn_pb2.InventoryServiceRequest()
        # Get the reference of the stub
        srv6_vpn_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Get VPNs
        response = srv6_vpn_stub.GetTopologyInformation(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve topology information
            topology = dict()
            topology['routers'] = list()
            topology['links'] = list()
            for router in response.topology_information.routers:
                topology['routers'].append(text_type(router))
            for link in response.topology_information.links:
                topology['links'].append(
                    (text_type(link.l_router), text_type(link.r_router)))
        else:
            topology = None
        # Let's close the session
        channel.close()
        return topology

    def get_overlays(self, overlays=[], tenantid=''):
        # Create the request
        request = srv6_vpn_pb2.InventoryServiceRequest()
        request.overlayids.extend(overlays)
        request.tenantid = tenantid
        # Get the reference of the stub
        srv6_vpn_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Get VPNs
        response = srv6_vpn_stub.GetOverlays(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve tunnel information
            tunnels = list()
            for tunnel in response.overlays:
                id = tunnel.id
                name = tunnel.name
                type = tunnel.type if tunnel.type is not None else None
                tunnel_mode = tunnel.mode if tunnel.mode is not None else None
                tenantid = tunnel.tenantid
                tunnel_interfaces = list()
                for interface in tunnel.slices:
                    deviceid = None
                    interface_name = None
                    if interface.deviceid is not None:
                        deviceid = text_type(interface.deviceid)
                    if interface.interface_name is not None:
                        interface_name = text_type(interface.interface_name)
                    tunnel_interfaces.append({
                        'deviceid': deviceid,
                        'interface_name': interface_name
                    })
                tunnels.append({
                    'id': id,
                    'name': name,
                    'type': type,
                    'interfaces': tunnel_interfaces,
                    'mode': tunnel_mode,
                    'tenantid': tenantid
                })
        else:
            tunnels = None
        # Let's close the session
        channel.close()
        return tunnels

    def create_overlay(self, name, type, interfaces, tenantid, encap='SRv6'):
        # Create the request
        request = srv6_vpn_pb2.OverlayServiceRequest()
        intent = request.intents.add()
        intent.overlay_name = text_type(name)
        intent.overlay_type = type
        intent.tenantid = tenantid
        #intent.encap = int(ENCAP.get(encap, None))
        intent.tunnel = encap
        # if intent.encap is None:
        if intent.tunnel is None:
            print('Invalid encap type')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        for intf in interfaces:
            interface = intent.slices.add()
            interface.deviceid = text_type(intf[0])
            interface.interface_name = text_type(intf[1])
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Create the VPN
        response = srv6_stub.CreateOverlay(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status

    def remove_overlay(self, overlayid, tenantid):
        # Create the request
        request = srv6_vpn_pb2.OverlayServiceRequest()
        intent = request.intents.add()
        intent.overlayid = text_type(overlayid)
        intent.tenantid = tenantid
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Remove the VPN
        response = srv6_stub.RemoveOverlay(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status

    def assign_slice_to_overlay(self, overlayid, tenantid, interfaces):
        # Create the request
        request = srv6_vpn_pb2.OverlayServiceRequest()
        intent = request.intents.add()
        intent.overlayid = text_type(overlayid)
        intent.tenantid = tenantid
        for intf in interfaces:
            interface = intent.slices.add()
            interface.deviceid = text_type(intf[0])
            interface.interface_name = text_type(intf[1])
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Add the interface to the VPN
        response = srv6_stub.AssignSliceToOverlay(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status

    def remove_slice_from_overlay(self, overlayid, tenantid, interfaces):
        # Create the request
        request = srv6_vpn_pb2.OverlayServiceRequest()
        intent = request.intents.add()
        intent.overlayid = text_type(overlayid)
        intent.tenantid = tenantid
        for intf in interfaces:
            interface = intent.slices.add()
            interface.deviceid = text_type(intf[0])
            interface.interface_name = text_type(intf[1])
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(
            self.server_ip, self.server_port, self.SECURE)
        # Remove the interface from the VPN
        response = srv6_stub.RemoveSliceFromOverlay(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status

    def print_overlays(self):
        # Get VPNs
        vpns = self.get_overlays(self.server_ip, self.server_port)
        # Print all VPNs
        if vpns is not None:
            print
            i = 1
            if len(vpns) == 0:
                print("No VPN in the network")
                print()
            for vpn in vpns:
                print("****** VPN %s ******" % i)
                print("Name:", vpn)
                print("Table ID:", vpns[vpn]["tableid"])
                print("Interfaces:")
                for intf in vpns[vpn]["interfaces"]:
                    print(intf.deviceid, intf.interface_name)
                print()
                i += 1
        else:
            print('Error while retrieving the VPNs list')


if __name__ == '__main__':
    '''# Test IPv6-VPN APIs
    srv6_vpn_manager = SRv6VPNManager()

    # Controller address and port
    controller_addr = '::'
    controller_port = 54321

    # Create VPN 10-research
    name = 'research'
    # Create interfaces
    # First interface
    if1 = Interface('fcff:0:1::1', 'ads1-eth3', 'fd00:0:1:1::1',
                    'fd00:0:1:1::/48')
    # Second interface
    if2 = Interface('fcff:0:2::1', 'ads2-eth3', 'fd00:0:1:3::1',
                    'fd00:0:1:3::/48')
    # List of interfaces
    interfaces = [
        if1,
        if2
    ]
    # Tenant ID
    tenantid = 10
    # Send creation command through the northbound API
    srv6_vpn_manager.create_vpn(controller_addr, controller_port,
                                name, VPNType.IPv6VPN, interfaces,
                                tenantid)
    # Remove all addresses in the hosts
    srv6_controller_utils.flush_ipv6_addresses_ssh('2000::4', 'hads11-eth1')
    srv6_controller_utils.flush_ipv6_addresses_ssh('2000::6', 'hads21-eth1')
    # Add the private addresses to the interfaces in the hosts
    srv6_controller_utils.add_ipv6_address_ssh('2000::4', 'hads11-eth1',
                                       'fd00:0:1:1::2/48')
    srv6_controller_utils.add_ipv6_address_ssh('2000::6', 'hads21-eth1',
                                       'fd00:0:1:3::2/48')

    # Add interface to the VPN
    name = 'research'
    # Create the interface
    if1 = Interface('fcff:0:1::1', 'ads1-eth4', 'fd00:0:1:2::1',
                    'fd00:0:1:2::/48')
    tenantid = 10
    srv6_vpn_manager.assign_interface_to_vpn(controller_addr,
                                             controller_port,
                                             name, tenantid, if1)
    # Remove all addresses in the hosts
    srv6_controller_utils.flush_ipv6_addresses_ssh('2000::5', 'hads12-eth1')
    # Add the public addresses to the interfaces in the hosts
    srv6_controller_utils.add_ipv6_address_ssh('2000::5', 'hads12-eth1',
                                       'fd00:0:1:2::2')

    # Remove interface from the VPN
    name = 'research'
    # Create the interface
    if1 = Interface('fcff:0:1::1', 'ads1-eth4')
    # Tenant ID
    tenantid = 10
    # Run remove interface command
    srv6_vpn_manager.remove_interface_from_vpn(controller_addr,
                                               controller_port, name,
                                               tenantid, if1)
    # Add the public prefixes to the interfaces in the routers
    srv6_controller_utils.add_ipv6_nd_prefix_quagga('2000::1', 'ads1-eth4',
                                            'fd00:0:1:3:2::/64')
    # Add the public addresses to the interfaces in the routers
    srv6_controller_utils.add_ipv6_address_quagga('2000::1', 'ads1-eth4',
                                          'fd00:0:1:3:2::1')
    # Remove all addresses in the hosts
    srv6_controller_utils.flush_ipv6_addresses_ssh('2000::5',
                                           'hads12-eth1')
    # Add the public addresses to the interfaces in the hosts
    srv6_controller_utils.add_ipv6_address_ssh('2000::5', 'hads12-eth1',
                                       'fd00:0:1:3:2::2')

    # Remove VPN 10-research
    srv6_vpn_manager.remove_vpn(controller_addr,
                                controller_port, 'research', 10)
    # Add the public prefixes addresses to the interfaces in the routers
    srv6_controller_utils.add_ipv6_nd_prefix_quagga('2000::1', 'ads1-eth3',
                                            'fd00:0:1:3:1::/64')
    srv6_controller_utils.add_ipv6_nd_prefix_quagga('2000::2', 'ads2-eth3',
                                            'fd00:0:2:3:1::/64')
    # Add the public addresses to the interfaces in the routers
    srv6_controller_utils.add_ipv6_address_quagga('2000::1', 'ads1-eth3',
                                          'fd00:0:1:3:1::1')
    srv6_controller_utils.add_ipv6_address_quagga('2000::2', 'ads2-eth3',
                                          'fd00:0:2:3:1::1')
    # Remove all addresses in the hosts
    srv6_controller_utils.flush_ipv6_addresses_ssh('2000::5', 'hads11-eth1')
    srv6_controller_utils.flush_ipv6_addresses_ssh('2000::6', 'hads21-eth1')
    # Add the public addresses to the interfaces in the hosts
    srv6_controller_utils.add_ipv6_address_ssh('2000::5', 'hads11-eth1',
                                       'fd00:0:2:3:1::/64')
    srv6_controller_utils.add_ipv6_address_ssh('2000::6', 'hads21-eth1',
                                       'fd00:0:2:3:1::/64')

    # Test IPv4-VPN APIs

    # Create VPN 10-research
    name = 'research'
    # Create interfaces
    # First interface
    if1 = Interface('fdff::1', 'ads1-eth3',
                    '172.16.1.1/24', '172.16.1.0/24')
    # Second interface
    if2 = Interface('fdff:0:0:100::1', 'ads2-eth3',
                    '172.16.3.1/24', '172.16.3.0/24')
    # List of interfaces
    interfaces = [
        if1,
        if2
    ]
    # Tenant ID
    tenantid = 10
    # Send creation command through the northbound API
    srv6_vpn_manager.create_vpn(controller_addr, controller_port,
                                name, VPNType.IPv4VPN,
                                interfaces, tenantid)

    # Add interface
    name = 'research'
    # Create the interface
    if1 = Interface('fdff::1', 'ads1-eth4',
                    '172.16.40.1/24', '172.16.40.0/24')
    tenantid = 10
    srv6_vpn_manager.assign_interface_to_vpn(controller_addr,
                                             controller_port, name,
                                             tenantid, if1)

    # Remove interface
    name = 'research'
    # Create the interface
    if1 = Interface('fdff::1', 'ads1-eth4')
    # Tenant ID
    tenantid = 20
    # Run remove interface command
    srv6_vpn_manager.remove_interface_from_vpn(controller_addr,
                                               controller_port, name,
                                               tenantid, if1)
    # Add the public addresses to the interfaces in the routers
    srv6_controller_utils.add_ipv4_address_quagga('fdff::1',
                                          'ads1-eth4', '10.3.0.1/16')

    # Remove VPN 10-research
    srv6_vpn_manager.remove_vpn(controller_addr,
                                controller_port, 'research', 10)
    # Add the public addresses to the interfaces in the hosts
    srv6_controller_utils.add_ipv4_address_quagga('fdff::1',
                                          'ads1-eth3', '10.3.0.1/16')
    srv6_controller_utils.add_ipv4_address_quagga('fdff:0:0:200::1',
                                          'sur1-eth3', '10.2.0.1/24')
    srv6_controller_utils.add_ipv4_address_quagga('fdff:0:0:200::1',
                                          'sur1-eth4', '10.5.0.1/24')'''

    #InventoryService = InventoryService()
    #response = InventoryService.configure_tenant('11.3.192.117', 54321, 40000, '')
    #print('Risponse tenant cration: %s --- %s --- %s' % (response[0], response[1], response[2]))
    #response2 = InventoryService.remove_tenant('11.3.192.117', 54321, 'mG4rESBHVO5byMoKq2CJifPZHLjqeYpAYRYrEEenNQe17BzfZRNLY3XVLvaSezdtEzWmz1sq14RIsBWsRoXLZuRffSztIJ3kywqDp1YAdEpMAwCMuTYa6jlIb4F8a5TI')
    #print('Response remove tenat: %s' % response2)
