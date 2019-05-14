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
# Add path of proto files
sys.path.append("/home/user/repos/srv6-sdn-proto/")
sys.path.append("/home/user/repos/srv6-sdn-control-plane/vpn")

import srv6_vpn_nb_pb2_grpc
import srv6_vpn_msg_pb2
import common_pb2

from vpn_utils import Interface, IPAddress

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
        channel = grpc.secure_channel("ipv6:[%s]:%s" % (ip_address, port),
                                      grpc_client_credentials)
    else:
        channel = grpc.insecure_channel("ipv6:[%s]:%s" % (ip_address, port))
    return srv6_vpn_nb_pb2_grpc.SRv6NorthboundVPNStub(channel), channel


def get_vpns():
    # Create the request
    request = common_pb2.EmptyRequest()
    # Get the reference of the stub
    srv6_stub, channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Get VPNs
    response = srv6_stub.GetVPNs(request)
    # Parse response and retrieve VPNs information
    vpns = dict()
    for vpn in response.vpns:
        vpn_name = vpn.vpn_name
        tableid = vpn.tableid
        interfaces = list()
        for intf in vpn.interfaces:
            ipaddrs = list()
            for ipaddr in intf.ipaddrs:
                ipaddrs.append(IPAddress(ipaddr.ip, ipaddr.net))
            ipaddrs = tuple(ipaddrs)
            interfaces.append(Interface(intf.router, intf.ifname, ipaddrs))
        vpns[vpn_name] = {
            "tableid": tableid,
            "interfaces": interfaces
        }
    # Let's close the session
    channel.close()
    return vpns


def create_vpn(intent):
    # Create the request
    request = srv6_vpn_msg_pb2.Intent()
    request.vpn_name = str(intent.vpn_name)
    request.tenantid = intent.tenantid
    for intf in intent.interfaces:
        interface = request.interfaces.add()
        interface.router = str(intf.router)
        interface.ifname = str(intf.ifname)
        for ipaddr in intf.ipaddrs:
            ipaddress = interface.ipaddrs.add()
            ipaddress.ip = str(ipaddr.ip)
            ipaddress.net = str(ipaddr.net)
    # Get the reference of the stub
    srv6_stub, channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Create the VPN
    response = srv6_stub.CreateVPN(request)
    # Let's close the session
    channel.close()
    # Print error
    if response.message != "OK":
        print response.message
    return response.message == "OK"


def remove_vpn(vpn_name, tenantid):
    # Create the request
    request = srv6_vpn_msg_pb2.RemoveVPNByNameRequest()
    request.vpn_name = vpn_name
    request.tenantid = tenantid
    # Get the reference of the stub
    srv6_stub, channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Remove the VPN
    response = srv6_stub.RemoveVPN(request)
    # Let's close the session
    channel.close()
    # Print error
    if response.message != "OK":
        print response.message
    return response.message == "OK"


def add_interface_to_vpn(vpn_name, tenantid, intf):
    # Create the request
    request = srv6_vpn_msg_pb2.AddInterfaceToVPNRequest()
    request.vpn_name = vpn_name
    request.tenantid = tenantid
    interface = request.interface
    interface.router = str(intf.router)
    interface.ifname = str(intf.ifname)
    for ipaddr in intf.ipaddrs:
        ipaddress = interface.ipaddrs.add()
        ipaddress.ip = str(ipaddr.ip)
        ipaddress.net = str(ipaddr.net)
    # Get the reference of the stub
    srv6_stub, channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Add the interface to the VPN
    response = srv6_stub.AddInterfaceToVPN(request)
    # Let's close the session
    channel.close()
    # Print error
    if response.message != "OK":
        print response.message
    return response.message == "OK"


def remove_interface_from_vpn(vpn_name, tenantid, intf):
    # Create the request
    request = srv6_vpn_msg_pb2.RemoveInterfaceFromVPNRequest()
    request.vpn_name = vpn_name
    request.tenantid = tenantid
    request.interface.router = str(intf.router)
    request.interface.ifname = str(intf.ifname)
    # Get the reference of the stub
    srv6_stub, channel = get_grpc_session(IP_ADDRESS, IP_PORT, SECURE)
    # Remove the interface from the VPN
    response = srv6_stub.RemoveInterfaceFromVPN(request)
    # Let's close the session
    channel.close()
    # Print error
    if response.message != "OK":
        print response.message
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
        print "Table ID:", vpns[vpn]["tableid"]
        print "Interfaces:"
        for intf in vpns[vpn]["interfaces"]:
            for ipaddr in intf.ipaddrs:
                print (intf.router, intf.ifname, ipaddr.ip, ipaddr.net)
        print
        i += 1
