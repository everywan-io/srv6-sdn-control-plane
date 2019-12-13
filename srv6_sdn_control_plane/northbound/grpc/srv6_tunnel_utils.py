#!/usr/bin/python

# Copyright (C) 2018 Carmine Scarpitta, Pier Luigi Ventre, Stefano Salsano - (CNIT and University of Rome 'Tor Vergata')
#
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
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
from sshutil.cmd import SSHCommand
import sys
import logging
import telnetlib
import socket
import json
import time
import os
import random
from socket import AF_INET
from socket import AF_INET6
# ipaddress dependencies
from ipaddress import IPv4Interface
from ipaddress import IPv6Interface
from ipaddress import AddressValueError
# NetworkX dependencies
import networkx as nx
from networkx.readwrite import json_graph
# SRv6 dependencies
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils


################## Setup these variables ##################

# Path of the proto files
#PROTO_FOLDER = "/home/user/repos/srv6-sdn-proto/"

###########################################################


# Adjust relative paths
#script_path = os.path.dirname(os.path.abspath(__file__))
#PROTO_FOLDER = os.path.join(script_path, PROTO_FOLDER)

# Check paths
#if PROTO_FOLDER == '':
#    print('Error: Set PROTO_FOLDER variable in nb_grpc_client.py')
#    sys.exit(-2)
#if not os.path.exists(PROTO_FOLDER):
#    print('Error: PROTO_FOLDER variable in nb_grpc_client.py '
#          'points to a non existing folder\n')
#    sys.exit(-2)

ZEBRA_PORT = 2601
SSH_PORT = 22
MIN_TABLE_ID = 2
# Linux kernel supports up to 255 different tables
MAX_TABLE_ID = 255
# Table where we store our seg6local routes
LOCAL_SID_TABLE = 1
# Reserved table IDs
RESERVED_TABLEIDS = [0, 253, 254, 255]
RESERVED_TABLEIDS.append(LOCAL_SID_TABLE)

WAIT_TOPOLOGY_INTERVAL = 1

# SRv6 dependencies
from srv6_generators import SIDAllocator

# Logger reference
logger = logging.getLogger(__name__)

class SRv6SpecificTunnelData:
    def __init__(self, tableid=-1):
        # Table ID
        self.tableid = tableid


class ControllerStateSRv6:
    """This class maintains the state of the SRv6 controller and provides some
       methods to handle it
    """

    def __init__(self, controller_state):
        # Create Table IDs allocator
        self.tableid_allocator = nb_grpc_utils.TableIDAllocator()
        # Create SIDs allocator
        self.sid_allocator = SIDAllocator()
        # Controller state
        self.controller_state = controller_state
        # Interfaces in VPN
        self.interfaces_in_vpn = dict()
        # SRv6 VPNs
        self.srv6_vpns = dict()
        # Sites in VPN
        self.sites_in_vpn = dict()
        # If VPN dumping is enabled, import the VPNs from the dump

        '''
        if vpn_file is not None:
            try:
                self.import_vpns_from_dump()
            except:
                print('Corrupted VPN file')
        '''

    # Return VPN type
    def get_vpn_tableid(self, vpn_name):
        print('srv6', self.srv6_vpns)
        if vpn_name not in self.srv6_vpns:
            return None
        return self.srv6_vpns[vpn_name].tableid

    # Return SID
    def get_sid(self, routerid, tableid):
        return self.sid_allocator.getSID(routerid, tableid)

    # Return SID
    def get_sid_family(self, routerid):
        return self.sid_allocator.getSIDFamily(routerid)

    # Get a new table ID
    def get_new_tableid(self, vpn_name, tenantid):
        return self.tableid_allocator.get_new_tableid(vpn_name, tenantid)

    # Get a new table ID
    def get_tableid(self, vpn_name):
        return self.tableid_allocator.get_tableid(vpn_name)

    # Release a table ID
    def release_tableid(self, vpn_name):
        return self.tableid_allocator.release_tableid(vpn_name)
