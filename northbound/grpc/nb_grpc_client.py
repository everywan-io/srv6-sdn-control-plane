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


import grpc

import sys
# Add path of gRPC APIs
sys.path.append("../../grpc")
# Add path of VPN APIs
sys.path.append("../../vpn")

import srv6_vpn_pb2_grpc
import srv6_vpn_pb2

from vpn_utils import *

# Define wheter to use SSL or not
SECURE = False
# SSL cerificate for server validation
CERTIFICATE = 'cert_client.pem'

# The IP address and port of the gRPC server started on the SDN controller
IP_ADDRESS = '::1'
IP_PORT = 12345

# Build a grpc stub
def get_grpc_session(ip_address, port, secure):
    # If secure we need to establish a channel with the secure endpoint
    if secure:
        # Open the certificate file
        with open(CERTIFICATE) as f:
            certificate = f.read()
        # Then create the SSL credentials and establish the channel
        grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
        channel = grpc.secure_channel("ipv6:[%s]:%s" %(ip_address, port), grpc_client_credentials)
    else:
        channel = grpc.insecure_channel("ipv6:[%s]:%s" %(ip_address, port))
    return srv6_vpn_pb2_grpc.SRv6VPNHandlerStub(channel), channel

def create_vpn(intent):
    # Create the request
    request = srv6_vpn_pb2.Intent()
    request.name = str(intent.name)
    request.tenant_id = str(intent.tenant_id)
    for intf in intent.interfaces:
        interface = request.interfaces.add()
        interface.router_id = str(intf[0])
        interface.name = str(intf[1])
        interface.ip_address = str(intf[2])
    # Get the reference of the stub
    srv6_stub,channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Create the VPN
    response = srv6_stub.CreateVPNFromIntent(request)
    # Let's close the session
    channel.close()
    return response.message == "OK"

def get_vpns():
    # Create the request
    request = srv6_vpn_pb2.EmptyRequest()
    # Get the reference of the stub
    srv6_stub,channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Get VPNs
    response = srv6_stub.GetVPNs(request)
    # Parse response and retrieve VPNs information
    vpns = dict()
    for vpn in response.vpns:
        vpn_name = vpn.name
        table_id = vpn.table_id
        interfaces = list()
        for intf in vpn.interfaces:
            interfaces.append(intf)
        vpns[vpn_name] = {
            "table_id": table_id,
            "interfaces": interfaces
        }
    # Let's close the session
    channel.close()
    return vpns

def remove_vpn(vpn_name, tenant_id):
    # Create the request
    request = srv6_vpn_pb2.RemoveVPNByNameRequest()
    request.name = vpn_name
    request.tenant_id = str(tenant_id)
    # Get the reference of the stub
    srv6_stub,channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Remove the VPN
    response = srv6_stub.RemoveVPNByName(request)
    # Let's close the session
    channel.close()
    return response.message == "OK"

def print_vpns():
    # Get VPNs
    vpns = get_vpns()
    # Print all VPNs
    print
    i = 1
    if len(vpns) == 0:
        print "No VPN in the network"
        print
    for vpn in vpns:
        print "****** VPN %s ******" % i
        print "Name:", vpn
        print "Table ID:", vpns[vpn]["table_id"]
        print "Interfaces:"
        for intf in vpns[vpn]["interfaces"]:
            print intf
        print
        i += 1


if __name__ == '__main__':
     # Create VPNs for testing purposes

    name = 'research'
    interfaces = [('0.0.0.1', 'ads1-eth3', '1111::1/64'),('0.0.0.2', 'ads2-eth3', '1211::1/64')]
    tenant_id = 10
    intent = VPNIntent(name, interfaces, tenant_id)
    create_vpn(intent)

    name = 'research'
    interfaces = [('0.0.0.1', 'ads1-eth4', '2111::1/64'),('0.0.0.3', 'sur1-eth3', '2211::1/64'), ('0.0.0.3', 'sur1-eth4', '2311::1/64')]
    tenant_id = 20
    intent = VPNIntent(name, interfaces, tenant_id)
    create_vpn(intent)

    '''
    remove_vpn('research', 20)

    name = 'research'
    interfaces = [('0.0.0.1', 'ads1-eth4', '3111::1/64'),('0.0.0.2', 'ads2-eth4', '3211::1/64'), ('0.0.0.3', 'sur1-eth4', '3311::1/64')]
    tenant_id = 20
    intent = VPNIntent(name, interfaces, tenant_id)
    create_vpn(intent)
    '''

    print_vpns()
