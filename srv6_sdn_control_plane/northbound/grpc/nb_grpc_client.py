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


# General imports
import grpc
import os
import sys

GRPC_FOLDER = '.'
# Adjust relative paths
script_path = os.path.dirname(os.path.abspath(__file__))
GRPC_FOLDER = os.path.join(script_path, GRPC_FOLDER)
sys.path.append(GRPC_FOLDER)
import nb_grpc_utils as utils

# Add path of proto files
sys.path.append(utils.PROTO_FOLDER)

# SRv6 dependencies
import srv6_vpn_pb2_grpc
import srv6_vpn_pb2
import status_codes_pb2
import empty_req_pb2
import nb_grpc_utils
from nb_grpc_utils import VPN
from nb_grpc_utils import Interface
from nb_grpc_utils import VPNType

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


ENCAP = {
    'SRv6': srv6_vpn_pb2.SRv6,
    'IPsec_ESP_GRE': srv6_vpn_pb2.IPsec_ESP_GRE,
    'SRv6_IPsec_ESP_GRE': srv6_vpn_pb2.SRv6_IPsec_ESP_GRE,
    'SRv6_IPsec_ESP_IP': srv6_vpn_pb2.SRv6_IPsec_ESP_IP
}


class SRv6VPNManager:

    def __init__(self, secure=DEFAULT_SECURE, certificate=DEFAULT_CERTIFICATE):
        self.SECURE = secure
        if secure is True:
            if certificate_path is None:
                print('Error: "certificate" variable cannot be None '
                      'in secure mode')
                sys.exit(-2)
            self.CERTIFICATE = certificate

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(CERTIFICATE) as f:
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
                vpn_name = vpn.vpn_name
                tableid = vpn.tableid
                interfaces = list()
                for intf in vpn.interfaces:
                    interfaces.append(Interface(intf.routerid, intf.interface_name,
                                                intf.interface_ip, intf.vpn_prefix))
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
        intent.vpn_name = name
        intent.vpn_type = STR_TO_VPN_TYPE[type]
        intent.tenantid = tenantid
        intent.encap = ENCAP.get(encap, None)
        if intent.encap is None:
            print('Invalid encap type')
            return status_codes_pb2.STATUS_INTERNAL_ERROR
        for intf in interfaces:
            interface = intent.interfaces.add()
            interface.routerid = str(intf[0])
            interface.interface_name = str(intf[1])
            interface.interface_ip = str(intf[2])
            interface.vpn_prefix = str(intf[3])
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
        intent.vpn_name = vpn_name
        intent.tenantid = tenantid
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
        intent.vpn_name = vpn_name
        intent.tenantid = tenantid
        interface = intent.interfaces.add()
        interface.routerid = str(intf[0])
        interface.interface_name = str(intf[1])
        interface.interface_ip = str(intf[2])
        interface.vpn_prefix = str(intf[3])
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
        intent.vpn_name = vpn_name
        intent.tenantid = tenantid
        interface = intent.interfaces.add()
        interface.routerid = str(intf[0])
        interface.interface_name = str(intf[1])
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
                    print (intf.routerid, intf.interface_name, intf.interface_ip, intf.vpn_prefix)
                print()
                i += 1
        else:
            print('Error while retrieving the VPNs list')


if __name__ == '__main__':
    # Test IPv6-VPN APIs

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
    # Create the intent
    intent = VPNIntent(name, VPNType.IPv6VPN, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)
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
    add_interface_to_vpn(name, tenantid, if1)
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
    remove_interface_from_vpn(name, tenantid, if1)
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
    remove_vpn('research', 10)
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
    # Create the intent
    intent = VPNIntent(name, VPNType.IPv4VPN,
                       interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)

    # Add interface
    name = 'research'
    # Create the interface
    if1 = Interface('fdff::1', 'ads1-eth4',
                    '172.16.40.1/24', '172.16.40.0/24')
    tenantid = 10
    add_interface_to_vpn(name, tenantid, if1)

    # Remove interface
    name = 'research'
    # Create the interface
    if1 = Interface('fdff::1', 'ads1-eth4')
    # Tenant ID
    tenantid = 20
    # Run remove interface command
    remove_interface_from_vpn(name, tenantid, if1)
    # Add the public addresses to the interfaces in the routers
    nb_grpc_utils.add_ipv4_address_quagga('fdff::1',
                                          'ads1-eth4', '10.3.0.1/16')

    # Remove VPN 10-research
    remove_vpn('research', 10)
    # Add the public addresses to the interfaces in the hosts
    nb_grpc_utils.add_ipv4_address_quagga('fdff::1',
                                          'ads1-eth3', '10.3.0.1/16')
    nb_grpc_utils.add_ipv4_address_quagga('fdff:0:0:200::1',
                                          'sur1-eth3', '10.2.0.1/24')
    nb_grpc_utils.add_ipv4_address_quagga('fdff:0:0:200::1',
                                          'sur1-eth4', '10.5.0.1/24')
