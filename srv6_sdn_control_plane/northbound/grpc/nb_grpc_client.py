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
import os
import sys

#GRPC_FOLDER = '.'
# Adjust relative paths
#script_path = os.path.dirname(os.path.abspath(__file__))
#GRPC_FOLDER = os.path.join(script_path, GRPC_FOLDER)
#sys.path.append(GRPC_FOLDER)
from . import nb_grpc_utils

# Add path of proto files
#sys.path.append(nb_grpc_utils.PROTO_FOLDER)

# SRv6 dependencies
from srv6_sdn_proto import srv6_vpn_pb2_grpc
from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import status_codes_pb2
from srv6_sdn_proto import empty_req_pb2
from srv6_sdn_proto import inventory_service_pb2_grpc
from srv6_sdn_proto import inventory_service_pb2
from .nb_grpc_utils import VPN
from .nb_grpc_utils import Interface
from .nb_grpc_utils import VPNType

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
    'IPv4VPN': srv6_vpn_pb2.IPv4VPN,
    'IPv6VPN': srv6_vpn_pb2.IPv6VPN
}


#ENCAP = {
#    'SRv6': srv6_vpn_pb2.SRv6,
#    'IPsec_ESP_GRE': srv6_vpn_pb2.IPsec_ESP_GRE,
#    'SRv6_IPsec_ESP_GRE': srv6_vpn_pb2.SRv6_IPsec_ESP_GRE,
#    'SRv6_IPsec_ESP_IP': srv6_vpn_pb2.SRv6_IPsec_ESP_IP
#}


class InventoryService:

    def __init__(self, secure=DEFAULT_SECURE, certificate=DEFAULT_CERTIFICATE):
        self.SECURE = secure
        if secure is True:
            if certificate is None:
                print('Error: "certificate" variable cannot be None '
                      'in secure mode')
                sys.exit(-2)
            self.certificate = certificate

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(self.certificate) as f:
                certificate = f.read()
            # Then create the SSL credentials and establish the channel
            grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
            channel = grpc.secure_channel("ipv6:[%s]:%s" % (ip_address, port),
                                          grpc_client_credentials)
        else:
            channel = grpc.insecure_channel("ipv6:[%s]:%s" % (ip_address, port))
        return inventory_service_pb2_grpc.InventoryServiceStub(channel), channel


    def get_device_information(self, server_ip, server_port):
        # Create the request
        request = inventory_service_pb2.InventoryServiceRequest()
        # Get the reference of the stub
        inventory_service_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Get VPNs
        response = inventory_service_stub.GetDeviceInformation(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve devices information
            devices = dict()
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
                        mac_addrs = list()
                        for mac_addr in intf.mac_addrs:
                            mac_addrs.append({
                                'broadcast': mac_addr.broadcast,
                                'addr': mac_addr.addr,
                            })
                        ipv4_addrs = list()
                        for ipv4_addr in intf.ipv4_addrs:
                            ipv4_addrs.append({
                                'broadcast': ipv4_addr.broadcast,
                                'netmask': ipv4_addr.netmask,
                                'addr': ipv4_addr.addr,
                            })
                        ipv6_addrs = list()
                        for ipv6_addr in intf.ipv6_addrs:
                            ipv6_addrs.append({
                                'broadcast': ipv6_addr.broadcast,
                                'netmask': ipv6_addr.netmask,
                                'addr': ipv6_addr.addr,
                            })
                        interfaces[ifname] = {
                            'mac_addrs': mac_addrs,
                            'ipv4_addrs': ipv4_addrs,
                            'ipv6_addrs': ipv6_addrs
                        }
                devices[device_id] = {
                    'device_id': device_id,
                    'loopbackip': loopbackip,
                    'loopbacknet': loopbacknet,
                    'managementip': managementip,
                    'interfaces': interfaces,
                    'mgmtip': mgmtip
                }
        else:
            devices = None
        # Let's close the session
        channel.close()
        return devices


    def get_topology_information(self, server_ip, server_port):
        # Create the request
        request = inventory_service_pb2.InventoryServiceRequest()
        # Get the reference of the stub
        inventory_service_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Get VPNs
        response = inventory_service_stub.GetTopologyInformation(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve topology information
            topology = dict()
            topology['routers'] = list()
            topology['links'] = list()
            for router in response.topology_information.routers:
                topology['routers'].append(text_type(router))
            for link in response.topology_information.links:
                topology['links'].append((text_type(link.l_router), text_type(link.r_router)))
        else:
            topology = None
        # Let's close the session
        channel.close()
        return topology


    def get_tunnel_information(self, server_ip, server_port):
        # Create the request
        request = inventory_service_pb2.InventoryServiceRequest()
        # Get the reference of the stub
        inventory_service_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Get VPNs
        response = inventory_service_stub.GetTunnelInformation(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve tunnel information
            tunnels = list()
            for tunnel in response.tunnel_information.tunnels:
                name = None
                tunnel_interfaces = list()
                for interface in tunnel.tunnel_interfaces:
                    routerid = None
                    interface_name = None
                    interface_ip = None
                    if interface.routerid is not None:
                        routerid = text_type(interface.routerid)
                    if interface.interface_name is not None:
                        interface_name = text_type(interface.interface_name)
                    if interface.interface_ip is not None:
                        interface_ip = text_type(interface.interface_ip)
                    if interface.site_prefix is not None:
                        site_prefix = text_type(interface.site_prefix)
                    tunnel_interfaces.append({
                        'routerid': routerid,
                        'interface_name': interface_name,
                        'interface_ip': interface_ip,
                        'site_prefix': site_prefix
                    })
                tunnels.append({
                    'name': name,
                    'tunnel_interfaces': tunnel_interfaces
                })
        else:
            tunnels = None
        # Let's close the session
        channel.close()
        return tunnels


class SRv6VPNManager:

    def __init__(self, secure=DEFAULT_SECURE, certificate=DEFAULT_CERTIFICATE):
        self.SECURE = secure
        if secure is True:
            if certificate is None:
                print('Error: "certificate" variable cannot be None '
                      'in secure mode')
                sys.exit(-2)
            self.certificate = certificate

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(self.certificate) as f:
                certificate = f.read()
            # Then create the SSL credentials and establish the channel
            grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
            channel = grpc.secure_channel("ipv6:[%s]:%s" % (ip_address, port),
                                          grpc_client_credentials)
        else:
            channel = grpc.insecure_channel("ipv6:[%s]:%s" % (ip_address, port))
        return srv6_vpn_pb2_grpc.SRv6VPNStub(channel), channel


    def get_vpns(self, server_ip, server_port):
        # Create the request
        request = empty_req_pb2.EmptyRequest()
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Get VPNs
        response = srv6_stub.GetVPNs(request)
        if response.status == status_codes_pb2.STATUS_SUCCESS:
            # Parse response and retrieve VPNs information
            vpns = dict()
            for vpn in response.vpns:
                vpn_name = text_type(vpn.vpn_name)
                tableid = int(vpn.tableid)
                interfaces = list()
                for intf in vpn.interfaces:
                    subnets = list()
                    for subnet in intf.subnets:
                        subnets.append(text_type(subnet))
                    interfaces.append(Interface(text_type(intf.routerid),
                                                text_type(intf.interface_name),
                                                text_type(intf.interface_ip),
                                                subnets))
                vpns[vpn_name] = {
                    "tableid": tableid,
                    "interfaces": interfaces
                }
        else:
            vpns = None
        # Let's close the session
        channel.close()
        return vpns


    def create_vpn(self, server_ip, server_port, 
                   name, type, interfaces, tenantid, encap='SRv6'):
        # Create the request
        request = srv6_vpn_pb2.SRv6VPNRequest()
        intent = request.intents.add()
        intent.vpn_name = text_type(name)
        intent.vpn_type = int(STR_TO_VPN_TYPE[type])
        intent.tenantid = int(tenantid)
        #intent.encap = int(ENCAP.get(encap, None))
        intent.tunnel = encap
        #if intent.encap is None:
        if intent.tunnel is None:
            print('Invalid encap type')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        for intf in interfaces:
            interface = intent.interfaces.add()
            interface.routerid = text_type(intf[0])
            interface.interface_name = text_type(intf[1])
            interface.interface_ip = text_type(intf[2])
            for subnet in intf[3]:
                interface.subnets.append(text_type(subnet))
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Create the VPN
        response = srv6_stub.CreateVPN(request)
        # Let's close the session
        channel.close()
        # Return
        return response.status


    def remove_vpn(self, server_ip, server_port, vpn_name, tenantid):
        # Create the request
        request = srv6_vpn_pb2.SRv6VPNRequest()
        intent = request.intents.add()
        intent.vpn_name = text_type(vpn_name)
        intent.tenantid = int(tenantid)
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Remove the VPN
        response = srv6_stub.RemoveVPN(intent)
        # Let's close the session
        channel.close()
        # Return
        return response.status


    def assign_interface_to_vpn(self, server_ip, server_port, vpn_name, tenantid, intf):
        # Create the request
        request = srv6_vpn_pb2.SRv6VPNRequest()
        intent = request.intents.add()
        intent.vpn_name = text_type(vpn_name)
        intent.tenantid = int(tenantid)
        interface = intent.interfaces.add()
        interface.routerid = text_type(intf[0])
        interface.interface_name = text_type(intf[1])
        interface.interface_ip = text_type(intf[2])
        for subnet in intf[3]:
            interface.subnets.append(text_type(subnet))
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Add the interface to the VPN
        response = srv6_stub.AssignInterfaceToVPN(intent)
        # Let's close the session
        channel.close()
        # Return
        return response.status


    def remove_interface_from_vpn(self, server_ip, server_port, vpn_name, tenantid, intf):
        # Create the request
        request = srv6_vpn_pb2.SRv6VPNRequest()
        intent = request.intents.add()
        intent.vpn_name = text_type(vpn_name)
        intent.tenantid = int(tenantid)
        interface = intent.interfaces.add()
        interface.routerid = text_type(intf[0])
        interface.interface_name = text_type(intf[1])
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(server_ip, server_port, self.SECURE)
        # Remove the interface from the VPN
        response = srv6_stub.RemoveInterfaceFromVPN(intent)
        # Let's close the session
        channel.close()
        # Return
        return response.status


    def print_vpns(self, server_ip, server_port):
        # Get VPNs
        vpns = self.get_vpns(server_ip, server_port)
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
                    subnet = list()
                    for subnet in intf.subnets:
                        subnets.append(subnet)
                    print(intf.routerid, intf.interface_name, intf.interface_ip, subnets)
                print()
                i += 1
        else:
            print('Error while retrieving the VPNs list')


if __name__ == '__main__':
    # Test IPv6-VPN APIs
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
    nb_grpc_utils.flush_ipv6_addresses_ssh('2000::4', 'hads11-eth1')
    nb_grpc_utils.flush_ipv6_addresses_ssh('2000::6', 'hads21-eth1')
    # Add the private addresses to the interfaces in the hosts
    nb_grpc_utils.add_ipv6_address_ssh('2000::4', 'hads11-eth1',
                                       'fd00:0:1:1::2/48')
    nb_grpc_utils.add_ipv6_address_ssh('2000::6', 'hads21-eth1',
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
    nb_grpc_utils.flush_ipv6_addresses_ssh('2000::5', 'hads12-eth1')
    # Add the public addresses to the interfaces in the hosts
    nb_grpc_utils.add_ipv6_address_ssh('2000::5', 'hads12-eth1',
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
    nb_grpc_utils.add_ipv6_nd_prefix_quagga('2000::1', 'ads1-eth4',
                                            'fd00:0:1:3:2::/64')
    # Add the public addresses to the interfaces in the routers
    nb_grpc_utils.add_ipv6_address_quagga('2000::1', 'ads1-eth4',
                                          'fd00:0:1:3:2::1')
    # Remove all addresses in the hosts
    nb_grpc_utils.flush_ipv6_addresses_ssh('2000::5',
                                           'hads12-eth1')
    # Add the public addresses to the interfaces in the hosts
    nb_grpc_utils.add_ipv6_address_ssh('2000::5', 'hads12-eth1',
                                       'fd00:0:1:3:2::2')

    # Remove VPN 10-research
    srv6_vpn_manager.remove_vpn(controller_addr,
                                controller_port, 'research', 10)
    # Add the public prefixes addresses to the interfaces in the routers
    nb_grpc_utils.add_ipv6_nd_prefix_quagga('2000::1', 'ads1-eth3',
                                            'fd00:0:1:3:1::/64')
    nb_grpc_utils.add_ipv6_nd_prefix_quagga('2000::2', 'ads2-eth3',
                                            'fd00:0:2:3:1::/64')
    # Add the public addresses to the interfaces in the routers
    nb_grpc_utils.add_ipv6_address_quagga('2000::1', 'ads1-eth3',
                                          'fd00:0:1:3:1::1')
    nb_grpc_utils.add_ipv6_address_quagga('2000::2', 'ads2-eth3',
                                          'fd00:0:2:3:1::1')
    # Remove all addresses in the hosts
    nb_grpc_utils.flush_ipv6_addresses_ssh('2000::5', 'hads11-eth1')
    nb_grpc_utils.flush_ipv6_addresses_ssh('2000::6', 'hads21-eth1')
    # Add the public addresses to the interfaces in the hosts
    nb_grpc_utils.add_ipv6_address_ssh('2000::5', 'hads11-eth1',
                                       'fd00:0:2:3:1::/64')
    nb_grpc_utils.add_ipv6_address_ssh('2000::6', 'hads21-eth1',
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
    nb_grpc_utils.add_ipv4_address_quagga('fdff::1',
                                          'ads1-eth4', '10.3.0.1/16')

    # Remove VPN 10-research
    srv6_vpn_manager.remove_vpn(controller_addr,
                                controller_port, 'research', 10)
    # Add the public addresses to the interfaces in the hosts
    nb_grpc_utils.add_ipv4_address_quagga('fdff::1',
                                          'ads1-eth3', '10.3.0.1/16')
    nb_grpc_utils.add_ipv4_address_quagga('fdff:0:0:200::1',
                                          'sur1-eth3', '10.2.0.1/24')
    nb_grpc_utils.add_ipv4_address_quagga('fdff:0:0:200::1',
                                          'sur1-eth4', '10.5.0.1/24')
