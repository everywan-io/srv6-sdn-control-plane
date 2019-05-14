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
# Interface names discovery
#
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#

import grpc
import json
import os
from optparse import OptionParser

import pprint

import sys

# Folders
CONTROL_PLANE_FOLDER = "/home/user/repos/srv6-sdn-control-plane/"
SB_GRPC_FOLDER = CONTROL_PLANE_FOLDER + "southbound/grpc/"


# Add path of gRPC APIs
sys.path.append(SB_GRPC_FOLDER)

from sb_grpc_client import InterfaceManager


# Folder of the interfaces dump
INTF_FOLDER = "interface_discovery"
# Interface IPs file
INTF_FILE = "%s/interfaces.json" % (INTF_FOLDER)


# NetworkX
import networkx as nx
from networkx.readwrite import json_graph

# Topology file
TOPOLOGY_FILE = CONTROL_PLANE_FOLDER + "topology/topo_extraction/topology.json"

# Verbose mode
VERBOSE = False


# Read the topology graph and convert to a NetworkX object
def read_json_file(filename):
    with open(filename) as f:
        js_graph = json.load(f)
    return json_graph.node_link_graph(js_graph)


def interface_discovery(routers, verbose=False):
    interfaceManager = InterfaceManager()
    # Check if INTF_FOLDER exists, if not create it
    if not os.path.exists(INTF_FOLDER):
        os.makedirs(INTF_FOLDER)
    # Mapping router to interfaces list
    router_to_interfaces = dict()
    # Extract interfaces
    for router in routers:
        if verbose:
            print ("\n*********** Extracting interfaces from %s ***********"
                   % router)
        try:
            router_to_interfaces[router] = (interfaceManager
                                            .get_interfaces(router))
        except grpc.RpcError as e:
            if e.details() == 'Connect Failed' and verbose:
                print "Cannot connect to %s" % router
    # Print interfaces
    if verbose:
        pp = pprint.PrettyPrinter()
        pp.pprint(router_to_interfaces)
    return router_to_interfaces


# Utility function to dump relevant information of the interfaces
def dump_interfaces(router_to_interfaces, output_filename=None):
    # Export interfaces into a json file
    # Json dump of the interfaces
    if output_filename is None:
        output_filename = INTF_FILE
    with open(output_filename, 'w') as outfile:
        # Dump the ips of the interfaces
        json.dump(router_to_interfaces, outfile, sort_keys=True, indent=2)


# Parse command line options and dump results
def parseOptions():
    global INTF_FOLDER, INTF_FILE, VERBOSE
    parser = OptionParser()
    # ip of the routers
    parser.add_option('--ips', dest='ips', type='string', default=None,
                      help='ip-port,ip-port map ip port of the routers')
    # Output directory
    parser.add_option('--out_dir', dest='out_dir', type='string', default="./",
                      help='output directory')
    # Enable verbose mode
    parser.add_option("-v", "--verbose", action="store_true",
                      default=False, help="Enable verbose mode")
    # Parse input parameters
    (options, args) = parser.parse_args()
    # Verbose mode
    VERBOSE = options.verbose
    # Interfaces folder
    INTF_FOLDER = "%s/%s" % (options.out_dir, INTF_FOLDER)
    # Interface IPs file
    INTF_FILE = "%s/interfaces.json" % (INTF_FOLDER)
    # Done, return
    return options


if __name__ == '__main__':
    # Let's parse input parameters
    opts = parseOptions()
    # Let's parse the input
    routers = []
    # First create the chunk
    if opts.ips is None:
        # In-Band solution
        # Get the network topology
        topology = read_json_file(TOPOLOGY_FILE)
        # Get the loopback prefixes of the routers
        routerid_to_loopbackip = nx.get_node_attributes(topology, 'loopbackip')
        for ip in routerid_to_loopbackip.itervalues():
            routers.append(ip)
    else:
        routers = opts.ips.split(",")
    # Extract interface info
    if len(routers) > 0:
        router_to_interfaces = interface_discovery(routers)
        # Dump relevant information of the network graph
        dump_interfaces(router_to_interfaces, VERBOSE)
    else:
        print "No router selected"
