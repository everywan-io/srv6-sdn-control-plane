#!/usr/bin/python

from __future__ import print_function

# General imports
import time
import os
import sys
import json
import threading
import logging
from filelock import FileLock
from argparse import ArgumentParser
from threading import Thread
from threading import Lock
# ipaddress dependencies
from ipaddress import IPv6Interface
# NetworkX dependencies
import networkx as nx
from networkx.readwrite import json_graph
import srv6_controller_utils as utils
# SRv6 dependencies
from interface_discovery.interface_discovery import interface_discovery
from topology.ti_extraction import draw_topo
from topology.ti_extraction import connect_and_extract_topology
from srv6_sdn_control_plane.southbound.grpc.sb_grpc_client import NetworkEventsListener
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_server
#
from pymerang.pymerang_server import PymerangController

################## Setup these variables ##################

# Path of the proto files
#PROTO_FOLDER = '../srv6-sdn-proto/'
# Mapping router ID to management IP
ROUTERID_TO_MGMTIP = {
    #'0.0.0.1': '2000::1',
    #'0.0.0.2': '2000::2',
    #'0.0.0.3': '2000::3'
    '0.0.0.1': '2000:0:0:1::1',
    '0.0.0.2': '2000:0:0:2::1',
    '0.0.0.3': '2000:0:0:3::1',
}

###########################################################

# Path of the interface discovery module
#INTERFACE_DISCOVERY_PATH = './interface_discovery'
# Path of the topology information extraction module
#TI_EXTRACTION_PATH = './topology'
# Path of the gRPC Southbound client
#SB_GRPC_CLIENT_PATH = './southbound/grpc/'
# Path of the gRPC Northbound server
#NB_GRPC_CLIENT_PATH = './northbound/grpc/'

# Adjust relative paths
#script_path = os.path.dirname(os.path.abspath(__file__))
#INTERFACE_DISCOVERY_PATH = os.path.join(script_path, INTERFACE_DISCOVERY_PATH)
#TI_EXTRACTION_PATH = os.path.join(script_path, TI_EXTRACTION_PATH)
#SB_GRPC_CLIENT_PATH = os.path.join(script_path, SB_GRPC_CLIENT_PATH)
#NB_GRPC_CLIENT_PATH = os.path.join(script_path, NB_GRPC_CLIENT_PATH)
#PROTO_FOLDER = os.path.join(script_path, PROTO_FOLDER)

# Check paths
#if PROTO_FOLDER == '':
#    utils.print_and_die('Error: Set PROTO_FOLDER '
#                        'variable in srv6_controller.py')
#if not os.path.exists(PROTO_FOLDER):
#    utils.print_and_die('Error: PROTO_FOLDER variable in srv6_controller.py '
#                        'points to a non existing file\n')

# Add path of interface discovery
#sys.path.append(INTERFACE_DISCOVERY_PATH)
# Add path of topology information extraction
#sys.path.append(TI_EXTRACTION_PATH)
# Add path of gRPC southbound client
#sys.path.append(SB_GRPC_CLIENT_PATH)
# Add path of gRPC northbound client
#sys.path.append(NB_GRPC_CLIENT_PATH)
# Add path of proto files
#sys.path.append(PROTO_FOLDER)


# In our experiment we use srv6 as default password
DEFAULT_OSPF6D_PASSWORD = 'srv6'
# Default topology file
DEFAULT_TOPOLOGY_FILE = '/tmp/topology.json'
# Interval between two consecutive extractions (in seconds)
DEFAULT_TOPO_EXTRACTION_PERIOD = 10
# Dot file used to draw topology graph
DOT_FILE_TOPO_GRAPH = '/tmp/topology.dot'
# Default folder where to save extracted OSPF databases
OSPF_DB_PATH = '/tmp/ospf_db'
# Supported southbound interfaces
SUPPORTED_SB_INTERFACES = ['gRPC']
# Supported northbound interfaces
SUPPORTED_NB_INTERFACES = ['None', 'gRPC']
# Logger reference
logger = logging.getLogger(__name__)
# Server ip and port
DEFAULT_GRPC_SERVER_IP = '::'
DEFAULT_GRPC_SERVER_PORT = 54321
DEFAULT_GRPC_CLIENT_PORT = 12345
# Debug option
SERVER_DEBUG = False
# Secure option
DEFAULT_SECURE = False
# Server certificate
DEFAULT_CERTIFICATE = 'cert_server.pem'
# Server key
DEFAULT_KEY = 'key_server.pem'
# Default southbound interface
DEFAULT_SB_INTERFACE = 'gRPC'
# Default northbound interface
DEFAULT_NB_INTERFACE = 'gRPC'
# Minimum interval between two topology dumps (in seconds)
DEFAULT_MIN_INTERVAL_BETWEEN_TOPO_DUMPS = 5


class SDWANControllerState:

    def __init__(self):
        self.devices = dict()


class SRv6Controller(object):

    def __init__(self, nodes, period, topo_file, topo_graph, out_of_band,
                 ospf6d_pwd, sb_interface, nb_interface,
                 secure, key, certificate, grpc_server_ip, grpc_server_port,
                 grpc_client_port, min_interval_between_topo_dumps,
                 vpn_dump=None, verbose=False):
        # Verbose mode
        self.VERBOSE = verbose
        if self.VERBOSE:
            print('*** Initializing controller variables')
        # Initialize variables
        # Nodes from which the topology has to be extracted
        self.nodes = nodes
        # Password used to log into ospf6d
        self.ospf6d_pwd = ospf6d_pwd
        # Period between two extractions
        self.period = period
        # Topology file
        self.topology_file = topo_file
        # Topology file
        self.topology_graph = topo_graph
        # Out-of-Band control
        self.out_of_band = out_of_band
        # Southbound interface
        self.sb_interface = sb_interface
        # Northbound interface
        self.nb_interface = nb_interface
        # Init lock for topology file
        self.topoFileLock = Lock()
        # Init Network Event Listener
        self.eventsListener = NetworkEventsListener()
        # Mapping router ID to listener thread
        self.listenerThreads = dict()
        # IP of the gRPC server
        self.grpc_server_ip = grpc_server_ip
        # Port of the gRPC server
        self.grpc_server_port = grpc_server_port
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Secure mode
        self.secure = secure
        # Server key
        self.key = key
        # Server certificate
        self.certificate = certificate
        # VPN dump
        self.vpn_file = vpn_dump
        # VPN dict
        self.vpn_dict = dict()
        # Graph
        self.G = nx.Graph()
        # Topology information
        self.topoInfo = {
            'routers': dict(),
            'nets': dict(),
            'interfaces': dict()
        }
        # Flag used to signal when the topology has changed
        self.topology_changed_flag = threading.Event()
        # Timestamp of the last topology dump
        self.last_dump_timestamp = 0
        # Lock used to protect topology graph data structure
        self.topo_graph_lock = Lock()
        # Minimum interval between dumps
        self.min_interval_between_topo_dumps = min_interval_between_topo_dumps
        if self.VERBOSE:
            print()
            print('Configuration')
            print(('*** Nodes: %s' % self.nodes))
            print(('*** ospf6d password: %s' % self.ospf6d_pwd))
            print(('*** Topology Information Extraction period: %s' % self.period))
            print(('*** Topology file: %s' % self.topology_file))
            print(('*** topology_graph: %s' % self.topology_graph))
            print(('*** Selected southbound interface: %s' % self.sb_interface))
            print(('*** Selected northbound interface: %s' % self.nb_interface))
            print()
        # Controller state
        self.controller_state = SDWANControllerState()

    # Get the interface of the router facing on a net
    def get_interface_facing_on_net(self, routerid, net):
        interfaces = self.topoInfo['interfaces'].get(routerid)
        if interfaces is None:
            # The router does not exists
            # Topology has not changed, return False
            return None
        # Iterate on the interfaces
        for ifindex, ifdata in list(interfaces.items()):
            # Iterate on IP addresses
            for ipaddr in ifdata['ipaddr']:
                # Check if the IP address is in the net
                if utils.IPv6AddrInNet(ipaddr, net):
                    # Interface has been found
                    return ifdata
        # The interface does not exist
        return None

    # Get an address (loopback or management) for the router
    # The implementation of this method is different for
    # In-Band and Out-of-Band controller
    def get_router_address(self, routerid):
        pass

    ''' Router interfaces '''

    # Create/Update a router interface
    def create_router_interface(self, routerid, ifindex, ifname=None,
                                macaddr=None, ipaddr=None, state=None):
        # Create router if it does not exist
        if self.topoInfo['interfaces'].get(routerid) is None:
            self.topoInfo['interfaces'][routerid] = dict()
        # Create/Update a new interface
        if self.topoInfo['interfaces'][routerid].get(ifindex) is None:
            self.topoInfo['interfaces'][routerid][ifindex] = dict()
        # Get the interface
        interface = self.topoInfo['interfaces'][routerid][ifindex]
        # Set the interface name
        if ifname is not None:
            interface['ifname'] = ifname
        # Set the MAC address
        if macaddr is not None:
            interface['macaddr'] = macaddr
        # Set the IP address
        if ipaddr is not None:
            interface['ipaddr'] = list()
            interface['ipaddr'].append(ipaddr)
        # Set the state
        if state is not None:
            interface['state'] = state
        # The topology has changed, return True
        return True

    # Delete a router interface
    def delete_router_interface(self, routerid, ifindex):
        if self.topoInfo['interfaces'].get(routerid) is None:
            # The router does not exist
            # The topology has not changed
            return False
        if self.topoInfo['interfaces'][routerid].get(ifindex) is None:
            # The interface does not exist
            # The topology has not changed
            return False
        # Delete the interface
        del self.topoInfo['interfaces'][routerid][ifindex]
        # The topology has not changed
        return True

    ''' General helper functions for network-related data structures '''

    # Attach a router to an existing net
    def attach_router_to_net(self, routerid, net):
        # Attach the new router
        attached_routers = self.topoInfo['nets'].get(net)
        if attached_routers is None:
            # The network does not exist
            self.topoInfo['nets'][net] = set()
        self.topoInfo['nets'][net].add(routerid)
        # Topology has changed, return true
        return True

    # Detach a router from an existing net
    def detach_router_from_net(self, routerid, net):
        # Detach the router
        attached_routers = self.topoInfo['nets'].get(net)
        if attached_routers is None:
            # The network does not exist
            # Topology has not changed, return False
            return False
        if routerid not in attached_routers:
            # The router is not attached to the net
            # Topology has not changed, return False
            return False
        attached_routers.remove(routerid)
        # Topology has changed, return True
        return True

    # Detach a router interface from an existing net
    def detach_router_interface_from_net(self, routerid, ifindex):
        interfaces = self.topoInfo['interfaces'].get(routerid)
        if interfaces is None:
            # The router does not exist
            # Topology has not changed, return False
            return False
        if interfaces.get(ifindex) is None:
            # The interface does not exist
            # Topology has not changed, return False
            return False
        # Iterate on IP addresses
        topo_changed = False
        for ipaddr in interfaces[ifindex]['ipaddr']:
            # Detach router interface from net
            net = str(IPv6Interface(ipaddr).network)
            if self.detach_router_from_net(routerid, net):
                topo_changed = True
        # Return True if topo has changed, False otherwise
        return topo_changed

    ''' Manage detached networks '''

    # Get detached nets
    def get_detached_nets(self, new_nets):
        detached_nets = dict()
        old_nets = list(self.topoInfo['nets'].items())
        # Iterate on stub networks
        for net, attached_routers in old_nets:
            if net not in new_nets:
                # The network has been detached from the topology
                detached_nets[net] = attached_routers
            else:
                # The network still exists
                # Iterate on routers and get routers detached from the net
                for router in attached_routers:
                    if router not in new_nets[net]:
                        # Add detached routers to the net
                        if detached_nets.get(net) is None:
                            detached_nets[net] = set()
                        detached_nets[net].add(router)
        # Return the detached nets
        return detached_nets

    # Get new attached nets
    def get_attached_nets(self, new_nets):
        attached_nets = dict()
        # Iterate on new nets
        for net, attached_routers in list(new_nets.items()):
            old_attached_routers = self.topoInfo['nets'].get(net)
            if old_attached_routers is None:
                # The network does not existed before
                # New network
                attached_nets[net] = attached_routers
            else:
                # The network already existed before
                # Iterate on routers and get new routers attached to the net
                for router in attached_routers:
                    if router not in old_attached_routers:
                        # New attached router
                        if attached_nets.get(net) is None:
                            attached_nets[net] = set()
                        attached_nets[net].add(router)
        # Return the attached nets
        return attached_nets

    ''' Manage routers information '''

    # Get disconnected routers
    def get_disconnected_routers(self, new_routers):
        disconnected_routers = dict()
        old_routers = list(self.topoInfo['routers'].items())
        # Iterate on old routers
        for routerid, router_info in old_routers:
            if new_routers.get(routerid) is None:
                # The router is not present in the new topology
                # Router has been disconnected
                disconnected_routers[routerid] = router_info
        # Return disconnected routers set
        return disconnected_routers

    # Get changed routers
    def get_changed_routers(self, new_routers):
        changed_routers = dict()
        # Iterate on new routers
        for routerid, router_info in list(new_routers.items()):
            old_router = self.topoInfo['routers'].get(routerid)
            if router_info != old_router:
                # Router has changed
                changed_routers[routerid] = router_info
        # Return changed routers
        return changed_routers

    # Get new routers
    def get_new_routers(self, new_routers):
        _new_routers = dict()
        # Iterate on new routers
        for routerid, router_info in list(new_routers.items()):
            old_routers = self.topoInfo['routers']
            if routerid not in old_routers:
                # New router
                _new_routers[routerid] = router_info
        # Return the new routers
        return _new_routers

    # Add/Update routers to the topology
    def add_routers_to_topo(self, routers):
        # Iterate on routers
        for routerid, router_info in list(routers.items()):
            # Add the router to the topology information
            self.topoInfo['routers'][routerid] = router_info
        # Topology has changed, return True
        return True

    # Remove routers from the topology
    def remove_routers_from_topo(self, routers):
        topo_changed = False
        # Iterate on routers
        for routerid in routers:
            # Remove the router from the topology information
            if self.topoInfo['routers'].pop(routerid, None) is not None:
                topo_changed = True
        # Return True if the topology has changed, False otherwise
        return topo_changed

    ''' Manage interface information '''

    # Add an IP address to an interface
    def add_ipaddr_to_interface(self, routerid, ifindex, ipaddr):
        # Get router interfaces
        interfaces = self.topoInfo['interfaces'].get(routerid)
        if interfaces is None:
            # The router does not existxist
            # Topology has not changed
            return False
        if interfaces.get(ifindex):
            # The interface does not exist
            # Topology has not changed
            return False
        # Add the IP address to the interface
        self.topoInfo['interfaces'][routerid][ifindex]['ipaddr'] \
            .append(ipaddr)
        # Topology has changed
        return True

    # Remove an IP address from an interface
    def remove_ipaddr_from_interface(self, routerid, ifindex, ipaddr):
        # Get router interfaces
        interfaces = self.topoInfo['interfaces'].get(routerid)
        if interfaces is None:
            # The router does not existxist
            # Topology has not changed
            return False
        if interfaces.get(ifindex):
            # The interface does not exist
            # Topology has not changed
            return False
        if ipaddr not in interfaces[ifindex]['ipaddr']:
            # The IP address does not exist
            # Topology has not changed
            return False
        # Remove the IP address from the interface
        self.topoInfo['interfaces'][routerid][ifindex]['ipaddr'] \
            .remove(ipaddr)
        # Topology has changed
        return True

    ''' Interface discovery '''

    # Update the interfaces of the router by running interface discovery
    def discover_and_update_router_interfaces(self, routerid):
        if self.VERBOSE:
            print(('*** Extracting interface from router %s' % routerid))
        # Get the IP address of the router
        router = self.get_router_address(routerid)
        if router is None:
            # Router address not found
            # The topology has not changed
            return False
        # Discover the interfaces
        interfaces = interface_discovery(router, self.grpc_client_port, verbose=True)
        # Update topology information
        self.topoInfo['interfaces'][routerid] = interfaces
        # Return True if the operation completed successfully
        return interfaces is not None

    ''' Network Events Listener '''

    # Handle 'Interface UP' event
    # Return true if the topology has changed
    def handle_interface_up_event(self, routerid, ifindex, ifname, macaddr):
        topo_changed = False
        if self.create_router_interface(routerid=routerid,
                                        ifindex=ifindex,
                                        ifname=ifname,
                                        macaddr=macaddr,
                                        state='UP'):
            topo_changed = True
        # Return True if the topology has changed, False otherwise
        return topo_changed

    # Handle 'Interface DOWN' event
    # Return true if the topology has changed
    def handle_interface_down_event(self, routerid, ifindex, ifname, macaddr):
        topo_changed = False
        # The interface does not exist, let's create a new one
        if self.create_router_interface(routerid=routerid,
                                      ifindex=ifindex,
                                      ifname=ifname,
                                      macaddr=macaddr,
                                      state='DOWN'):
            topo_changed = True
        # Return True if the topology has changed, False otherwise
        return topo_changed

    # Handle 'Interface DEL' event
    # Return true if the topology has changed
    def handle_interface_del_event(self, routerid, ifindex):
        topo_changed = False
        # Detach the router from the net
        if self.detach_router_interface_from_net(routerid, ifindex):
            topo_changed = True
        # Let's remove the interface
        if self.delete_router_interface(routerid, ifindex):
            topo_changed = True
        # The topology has been updated
        return topo_changed

    # Handle 'NEW ADDR' event
    # Return true if the topology has changed
    def handle_new_addr_event(self, routerid, ifindex, ipaddr):
        topo_changed = False
        # Let's update the interface
        if self.add_ipaddr_to_interface(routerid, ifindex, ipaddr):
            topo_changed = True
        # Add the new network to the topology
        net = IPv6Interface(ipaddr).network
        if not net.is_link_local:
            # and attach the router to it
            if self.attach_router_to_net(routerid, str(net)):
                topo_changed = True
        # The topology has been updated
        return topo_changed

    # Handle 'DEL ADDR' event
    # Return true if the topology has changed
    def handle_del_addr_event(self, routerid, ifindex, ipaddr):
        topo_changed = False
        # Let's update the interface
        if self.remove_ipaddr_from_interface(routerid, ifindex, ipaddr):
            topo_changed = True
        # Get the network associated to the interface
        net = str(IPv6Interface(ipaddr).network)
        # and detach the router from it
        if self.detach_router_from_net(routerid, net):
            topo_changed = True
        # The topology has been updated
        return topo_changed

    # This function processes some network-related notifications
    # received from the nodes through the Southbound interface
    def listen_network_events(self, routerid):
        topo_changed = False
        router = self.get_router_address(routerid)
        if router is None:
            logging.warning('Error in listen_network_events(): '
                            'Cannot find an address for the router %s'
                            % router)
            return
        if self.VERBOSE:
            print('*** Listening network events from router %s' % router)
        if self.sb_interface == 'gRPC':
            # Wait for next network event notification and process it
            for event in self.eventsListener.listen(router, self.grpc_client_port):
                if self.VERBOSE:
                    print('*** Received a new network event from router %s:\n%s'
                           % (routerid, event))
                if event['type'] == 'CONNECTION_ESTABLISHED':
                    # 'Connection established' message
                    # Run interface discovery to get missing information
                    # In the future, we don't need to run the interface
                    # discovery procedure anymore, since the SRv6 controller
                    # listens for network events from this node
                    if not self.discover_and_update_router_interfaces(routerid):
                        # If the gRPC server on the node does not respond,
                        # abort and retry later
                        return
                    # Let's update the interfaces
                    for r, interfaces in \
                            list(self.topoInfo['interfaces'].items()):
                        for ifindex, ifdata in list(interfaces.items()):
                            for ipaddr in ifdata['ipaddr']:
                                # Add the new network to the topology
                                net = IPv6Interface(ipaddr).network
                                if not net.is_link_local:
                                    # and attach the router to it
                                    if self.attach_router_to_net(r, str(net)):
                                        topo_changed = True
                elif event['type'] == 'INTF_UP':
                    # Interface UP event
                    interface = event['interface']
                    # Extract interface index
                    ifindex = interface['index']
                    # Extract interface name
                    ifname = interface['name']
                    # Extract interface MAC address
                    macaddr = interface['macaddr']
                    # Handle interface up event
                    topo_changed = self.handle_interface_up_event(routerid, ifindex,
                                                                  ifname, macaddr)
                elif event['type'] == 'INTF_DOWN':
                    # Interface DOWN event
                    interface = event['interface']
                    # Extract interface index
                    ifindex = interface['index']
                    # Extract interface name
                    ifname = interface['name']
                    # Extract interface MAC address
                    macaddr = interface['macaddr']
                    # Handle interface down event
                    topo_changed = self.handle_interface_down_event(routerid, ifindex,
                                                                    ifname, macaddr)
                elif event['type'] == 'INTF_DEL':
                    # Interface DEL event
                    interface = event['interface']
                    # Extract interface index
                    ifindex = interface['index']
                    # Handle interface down event
                    topo_changed = self.handle_interface_del_event(routerid, ifindex)
                elif event['type'] == 'NEW_ADDR':
                    # New address event
                    interface = event['interface']
                    # Extract interface index
                    ifindex = interface['index']
                    # Extract address
                    ipaddr = interface['ipaddr']
                    # Handle new address event
                    topo_changed = self.handle_new_addr_event(routerid,
                                                              ifindex, ipaddr)
                elif event['type'] == 'DEL_ADDR':
                    # Del address event
                    interface = event['interface']
                    # Extract interface index
                    ifindex = interface['index']
                    # Extract address
                    ipaddr = interface['ipaddr']
                    # Handle interface del event
                    topo_changed = self.handle_del_addr_event(routerid,
                                                              ifindex, ipaddr)
                # Build, dump and draw topology, if it has changed
                if topo_changed:
                    if self.VERBOSE:
                        print('*** Topology has changed')
                    self.build_topo_graph()
        else:
            logging.error('Unsopported or invalid southbound interface')

    # Check if network events listener
    # is already started for a given router
    def check_network_events_listener(self, routerid):
        # Get the thread which handles the events listening
        listenerThread = self.listenerThreads.get(routerid)
        if listenerThread is not None and listenerThread.isAlive():
            # The thread is still alive
            return True
        else:
            # The thread is dead
            return False

    # Start network events listeners
    def start_network_events_listeners(self):
        # Iterate on routers
        for routerid, router_info in list(self.topoInfo['routers'].items()):
            if not self.check_network_events_listener(routerid):
                # The thread which handles the events listening is not active
                # Start a new thread events listener in a new thread
                thread = Thread(name=routerid,
                                target=self.listen_network_events,
                                args=(routerid, ))
                thread.daemon = True
                # and update the mapping
                self.listenerThreads[routerid] = thread
                thread.start()


    ''' Topology Information Extraction '''

    # Utility function to dump relevant information of the topology
    def dump_topo(self, G):
        if self.VERBOSE:
            print(('*** Saving topology dump to %s' % self.topology_file))
        # Export NetworkX object into a json file
        # Json dump of the topology
        with FileLock(self.topology_file):
            with open(self.topology_file, 'w') as outfile:
                # Get json topology
                json_topology = json_graph.node_link_data(G)
                # Convert links
                json_topology['links'] = [
                    {
                        'source_id': json_topology['nodes'][link['source']]['id'],
                        'target_id': json_topology['nodes'][link['target']]['id'],
                        'source': link['source'],
                        'target': link['target'],
                        'source_ip': link['source_ip'],
                        'target_ip': link['target_ip'],
                        'source_intf': link['source_intf'],
                        'target_intf': link['target_intf'],
                        'net': link['net']
                    }
                    for link in json_topology['links']]
                # Convert nodes
                json_topology['nodes'] = [
                    {
                        'id': node['id'],
                        'routerid': node['routerid'],
                        'loopbacknet': node['loopbacknet'],
                        'loopbackip': node['loopbackip'],
                        'managementip': node.get('managementip'),
                        'interfaces': node['interfaces'],
                        'type': node.get('type', '')
                    }
                    if node.get('type') == 'router'
                    else  # stub network
                    {
                        'id': node['id'],
                        'type': node.get('type', '')
                    }
                    for node in json_topology['nodes']]
                # Dump the topology
                json.dump(json_topology, outfile, sort_keys=True, indent=2)

    # Build NetworkX Topology graph
    def build_topo_graph(self):
        if self.VERBOSE:
            print('*** Building topology')
            print(('*** Routers: %s' % list(self.topoInfo['routers'].keys())))
            print(('*** Nets: %s' % list(self.topoInfo['nets'].keys())))
        # Topology graph
        #G = nx.Graph()
        # Build topology graph
        with self.topo_graph_lock:
            # Remove all nodes and edges from the graph
            self.G.clear()
            # Build nodes list
            # Add routers to the graph
            for routerid, router_info in list(self.topoInfo['routers'].items()):
                # Extract loopback net
                loopbacknet = router_info.get('loopbacknet')
                # Extract loopback IP
                loopbackip = router_info.get('loopbackip')
                # Extract management IP
                if self.out_of_band:
                    managementip = self.routerid_to_mgmtip.get(routerid)
                else:
                    managementip = None
                # Extract router interfaces
                interfaces = self.topoInfo['interfaces'].get(routerid)
                # Add the node to the graph
                self.G.add_node(routerid, routerid=routerid, fillcolor='red',
                        style='filled', shape='ellipse',
                        loopbacknet=loopbacknet, loopbackip=loopbackip,
                        managementip=managementip, interfaces=interfaces, type='router')
            # Build edges list
            for net, routerids in list(self.topoInfo['nets'].items()):
                if len(routerids) == 2:
                    # Transit network
                    # Link between two routers
                    edge = list(routerids)
                    edge = (edge[0], edge[1])
                    # Get the two router interfaces corresponding to this edge
                    # Get interface name and IP address
                    # corresponding to the left router
                    lhs_intf = self.get_interface_facing_on_net(edge[0], net)
                    if lhs_intf is None or lhs_intf['state'] == 'DOWN':
                        # The interface is 'DOWN'
                        # Skip
                        continue
                    lhs_ifname = lhs_intf.get('ifname')
                    lhs_ip = utils.findIPv6AddrInNet(lhs_intf.get('ipaddr'), net)
                    # Get interface name and IP address
                    # corresponding to the right router
                    rhs_intf = self.get_interface_facing_on_net(edge[1], net)
                    if rhs_intf is None or rhs_intf['state'] == 'DOWN':
                        # The interface is 'DOWN'
                        # Skip
                        continue
                    rhs_ifname = rhs_intf.get('ifname')
                    rhs_ip = utils.findIPv6AddrInNet(rhs_intf.get('ipaddr'), net)
                    # Add edge to the graph
                    # This is a transit network, set the net as label
                    self.G.add_edge(*edge, label=net, fontsize=9, net=net,
                            source_ip=rhs_ip, source_intf=rhs_ifname,
                            target_ip=lhs_ip, target_intf=lhs_ifname)
                elif len(routerids) == 1:
                    # Stub networks
                    # Link between a router and a stub network
                    edge = (list(routerids)[0], net)
                    # Get the interface of the left router
                    lhs_intf = self.get_interface_facing_on_net(edge[0], net)
                    if lhs_intf is None or lhs_intf['state'] == 'DOWN':
                        # The interface is 'DOWN'
                        # Skip
                        continue
                    lhs_ifname = lhs_intf.get('ifname')
                    lhs_ip = utils.findIPv6AddrInNet(lhs_intf.get('ipaddr'), net)
                    # Add a node representing the net to the graph
                    self.G.add_node(net, fillcolor='cyan', style='filled',
                            shape='box', type='stub_network')
                    # Add edge to the graph
                    # This is a stub network, no label on the edge
                    self.G.add_edge(*edge, label='', fontsize=9, net=net,
                            source_ip=None, source_intf=None,
                            target_ip=lhs_ip, target_intf=lhs_intf)
        # Set the topology changed flag
        self.topology_changed_flag.set()

    def dump_and_draw_topo(self):
        while True:
            # Wait until the topology changes
            self.topology_changed_flag.wait()
            # Clear the topology changed flag
            self.topology_changed_flag.clear()
            if self.G is None:
                # No graph to draw
                continue
            # Wait for minimum interval between two topology dumps
            wait = self.last_dump_timestamp + self.min_interval_between_topo_dumps - time.time()
            if wait > 0:
                time.sleep(wait)
            with self.topo_graph_lock:
                # Dump relevant information of the network graph
                self.dump_topo(self.G)
                # Export the network graph as an image file
                if self.topology_graph is not None:
                    draw_topo(self.G, self.topology_graph, DOT_FILE_TOPO_GRAPH)
            # Update last dump timestamp
            self.last_dump_timestamp = time.time()

    def update_topology_info(self, routers, nets):
        topo_changed = False
        # Get disconnected routers
        disconnected_routers = self.get_disconnected_routers(routers)
        # Get changed routers
        changed_routers = self.get_changed_routers(routers)
        # Get new routers
        new_routers = self.get_new_routers(routers)
        # Get detached nets
        detached_nets = self.get_detached_nets(nets)
        # Get attached nets
        attached_nets = self.get_attached_nets(nets)
        # Print results
        if self.VERBOSE:
            print(('*** New routers: %s' % new_routers))
            print(('*** Changed routers: %s' % changed_routers))
            print(('*** Disconnected routers: %s' % disconnected_routers))
        # Update the topology
        # Process disconnected routers
        if self.remove_routers_from_topo(disconnected_routers):
            topo_changed = True
        # Process new routers
        if self.add_routers_to_topo(new_routers):
            topo_changed = True
        # Process detached nets
        for net, routerids in list(detached_nets.items()):
            for routerid in routerids.copy():
                if self.detach_router_from_net(routerid, net):
                    topo_changed = True
        # Process attached nets
        for net, routerids in list(attached_nets.items()):
            for routerid in routerids.copy():
                if self.attach_router_to_net(routerid, net):
                    topo_changed = True
        # Return true if the topology has changed, False otherwise
        return topo_changed

    # Topology Information Extraction
    def topology_information_extraction(self):
        if self.VERBOSE:
            print('*** Starting Topology Information Extraction')
        # Loop
        stop = False
        while not stop:
            # Extract the topology from the routers
            routers, stub_nets, transit_nets = \
                        connect_and_extract_topology(self.nodes, OSPF_DB_PATH,
                                                     self.ospf6d_pwd, True)
            nets = utils.merge_two_dicts(stub_nets, transit_nets)
            # Update the topology information
            if self.update_topology_info(routers, nets):
                # If topology has been updated
                # Build, dump and draw topology
                self.build_topo_graph()
            # Start receiving Netlink messages from new routers
            self.start_network_events_listeners()
            # Wait 'period' seconds between two extractions
            try:
                time.sleep(period)
            except KeyboardInterrupt:
                if self.VERBOSE:
                    print('*** Stopping Topology Information Extraction')
                stop = True
        if self.VERBOSE:
            print('*** Done')

    # Start registration server
    def start_registration_server(self):
        logging.info('*** Starting registration server')
        server = PymerangController(devices=self.controller_state.devices)
        server.load_device_config()
        server.serve()

    # Run the SRv6 controller
    def run(self):
        if self.VERBOSE:
            print('*** Starting the SRv6 Controller')
        # Init Northbound Interface
        if self.nb_interface == 'gRPC':
            if self.VERBOSE:
                print('*** Starting gRPC Northbound server')
            # Start a new thread events listener in a new thread
            thread = Thread(
                target=nb_grpc_server.start_server,
                kwargs=({
                        'grpc_server_ip': self.grpc_server_ip,
                        'grpc_server_port': self.grpc_server_port,
                        'grpc_client_port': self.grpc_client_port,
                        'secure': self.secure,
                        'key': self.key,
                        'certificate': self.certificate,
                        'southbound_interface': self.sb_interface,
                        'topo_graph': self.G,
                        'vpn_dict': self.vpn_dict,
                        'devices': self.controller_state.devices,
                        'vpn_file': self.vpn_file,
                        'use_mgmt_ip': self.out_of_band,
                        'verbose': self.VERBOSE
                    }
                )
            )
            thread.daemon = True
            thread.start()
        # Start 'dump and draw' thread
        thread = Thread(
            target=self.dump_and_draw_topo
        )
        thread.daemon = True
        thread.start()
        # Start registration server
        thread = Thread(
            target=self.start_registration_server
        )
        thread.daemon = True
        thread.start()
        # Start topology information extraction
        self.topology_information_extraction()


class InBandSRv6Controller(SRv6Controller):

    def __init__(self, nodes, period, topo_file,
                 topo_graph, ospf6d_pwd, sb_interface, nb_interface, secure,
                 key, certificate, grpc_server_ip, grpc_server_port, grpc_client_port,
                 min_interval_between_topo_dumps, vpn_dump, verbose):
        super(InBandSRv6Controller, self).__init__(
            nodes=nodes,
            period=period,
            topo_file=topo_file,
            out_of_band=False,
            topo_graph=topo_graph,
            ospf6d_pwd=ospf6d_pwd,
            sb_interface=sb_interface,
            nb_interface=nb_interface,
            secure=secure,
            key=key,
            certificate=certificate,
            grpc_server_ip=grpc_server_ip,
            grpc_server_port=grpc_server_port,
            grpc_client_port=grpc_client_port,
            min_interval_between_topo_dumps=min_interval_between_topo_dumps,
            vpn_dump=vpn_dump,
            verbose=verbose
        )

    # In-band controllers use loopback IPs
    # Get a loopback address for the router
    def get_router_address(self, routerid):
        router_info = self.topoInfo['routers'].get(routerid)
        if router_info is not None:
            return router_info['loopbackip']


class OutOfBandSRv6Controller(SRv6Controller):

    def __init__(self, nodes, period, topo_file,
                 topo_graph, ospf6d_pwd, sb_interface, nb_interface, secure,
                 key, certificate, grpc_server_ip, grpc_server_port, grpc_client_port,
                 min_interval_between_topo_dumps, vpn_dump, verbose):
        super(OutOfBandSRv6Controller, self).__init__(
            nodes=nodes,
            period=period,
            topo_file=topo_file,
            out_of_band=True,
            topo_graph=topo_graph,
            ospf6d_pwd=ospf6d_pwd,
            sb_interface=sb_interface,
            nb_interface=nb_interface,
            secure=secure,
            key=key,
            certificate=certificate,
            grpc_server_ip=grpc_server_ip,
            grpc_server_port=grpc_server_port,
            grpc_client_port=grpc_client_port,
            min_interval_between_topo_dumps=min_interval_between_topo_dumps,
            vpn_dump=vpn_dump,
            verbose=verbose
        )
        # Check mapping routerid to mgmt ip required by out-of-band control
        if len(ROUTERID_TO_MGMTIP) == 0:
            utils.print_and_die('Error: Set ROUTERID_TO_MGMTIP '
                                'variable in srv6_controller.py '
                                'in order to use Out-of-Band Controller')
        # Mapping router ID to management IP
        self.routerid_to_mgmtip = ROUTERID_TO_MGMTIP

    # Out-of-band controllers use management IPs
    # Get a management address for the router
    def get_router_address(self, routerid):
        return self.routerid_to_mgmtip.get(routerid)


# Parse arguments
def parseArguments():
    # Get parser
    parser = ArgumentParser(description='SRv6 Controller')
    # Node IP-PORTs mapping
    parser.add_argument('--ips', action='store', dest='nodes',
                        required=True, help='IP of the routers from '
                        'which the topology has to be extracted, '
                        'comma-separated IP-PORT maps '
                        '(i.e. 2000::1-2606,2000::2-2606,2000::3-2606')
    # Topology Information Extraction period
    parser.add_argument('-p', '--period', dest='period',
                        type=int, default=DEFAULT_TOPO_EXTRACTION_PERIOD,
                        help='Topology information extraction period')
    # Enable In-Band SRv6 Controller
    parser.add_argument('--in-band', action='store_true', dest='in_band',
                        help='Enable In-Band SRv6 Controller')
    # Path of topology file
    parser.add_argument('--topology', dest='topo_file', action='store',
                        default=DEFAULT_TOPOLOGY_FILE, help='File where '
                        'the topology extracted has to be saved')
    # Path of topology graph
    parser.add_argument('--topo-graph', dest='topo_graph', action='store',
                        default=None, help='File where the topology '
                        'graph image has to be saved')
    # Enable debug logs
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Activate debug logs')
    # Password used to log in to ospf6d daemon
    parser.add_argument('--password', action='store_true',
                        dest='password', default=DEFAULT_OSPF6D_PASSWORD,
                        help='Password used to log in to ospf6d daemon')
    # Verbose mode
    parser.add_argument('-v', '--verbose', action='store_true',
                        dest='verbose', default=False,
                        help='Enable verbose mode')
    # Southbound interface
    parser.add_argument('--sb-interface', action='store',
                        dest='sb_interface', default=DEFAULT_SB_INTERFACE,
                        help='Select a southbound interface ' \
                        'from this list: %s' % SUPPORTED_SB_INTERFACES)
    # Northbound interface
    parser.add_argument('--nb-interface', action='store',
                        dest='nb_interface', default=DEFAULT_NB_INTERFACE,
                        help='Select a northbound interface ' \
                        'from this list: %s' % SUPPORTED_NB_INTERFACES)
    # IP address of the northbound gRPC server
    parser.add_argument('--grpc-server-ip', dest='grpc_server_ip',
                        action='store', default=DEFAULT_GRPC_SERVER_IP,
                        help='IP of the northbound gRPC server')
    # Port of the northbound gRPC server
    parser.add_argument('--grpc-server-port', dest='grpc_server_port',
                        action='store', default=DEFAULT_GRPC_SERVER_PORT,
                        help='Port of the northbound gRPC server')
    # Port of the northbound gRPC client
    parser.add_argument('--grpc-client-port', dest='grpc_client_port',
                        action='store', default=DEFAULT_GRPC_CLIENT_PORT,
                        help='Port of the northbound gRPC client')
    # Enable secure mode
    parser.add_argument('-s', '--secure', action='store_true',
                        default=DEFAULT_SECURE, help='Activate secure mode')
    # Server certificate
    parser.add_argument('--server-cert', dest='server_cert',
                        action='store', default=DEFAULT_CERTIFICATE,
                        help='Server certificate file')
    # Server key
    parser.add_argument('--server-key', dest='server_key',
                        action='store', default=DEFAULT_KEY,
                        help='Server key file')
    # Path of output VPN file
    parser.add_argument('-f', '--vpn-file', dest='vpn_dump', action='store',
                        default=None, help='File where the vpns created have to be saved')
    # Port of the northbound gRPC client
    parser.add_argument('--min-interval-dumps', dest='min_interval_between_topo_dumps',
                        action='store', default=DEFAULT_MIN_INTERVAL_BETWEEN_TOPO_DUMPS,
                        help='Minimum interval between two consecutive dumps')
    # Parse input parameters
    args = parser.parse_args()
    # Done, return
    return args


if __name__ == '__main__':
    # Let's parse input parameters
    args = parseArguments()
    # Get topology filename
    topo_file = args.topo_file
    # Get topology graph image filename
    topo_graph = args.topo_graph
    if topo_graph is not None and \
            not topo_graph.endswith('.svg'):
        # Add file extension
        topo_graph = '%s.%s' % (topo_graph, 'svg')
    # Nodes
    nodes = args.nodes
    nodes = nodes.split(',')
    # Get period between two extractions
    period = args.period
    # self.VERBOSE mode
    verbose = args.verbose
    # ospf6d password
    pwd = args.password
    # Southbound interface
    sb_interface = args.sb_interface
    # Northbound interface
    nb_interface = args.nb_interface
    # Output VPN file
    vpn_dump = args.vpn_dump
    # Setup properly the logger
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    # Setup properly the secure mode
    if args.secure:
        secure = True
    else:
        secure = False
    # gRPC server IP
    grpc_server_ip = args.grpc_server_ip
    # gRPC server port
    grpc_server_port = args.grpc_server_port
    # gRPC client port
    grpc_client_port = args.grpc_client_port
    # Server certificate
    certificate = args.server_cert
    # Server key
    key = args.server_key
    # Minimum interval between two consecutive topology dumps
    min_interval_between_topo_dumps = args.min_interval_between_topo_dumps
    SERVER_DEBUG = logger.getEffectiveLevel() == logging.DEBUG
    logger.info('SERVER_DEBUG:' + str(SERVER_DEBUG))
    # Check interfaces file, dataplane and gRPC client paths
    if sb_interface not in SUPPORTED_SB_INTERFACES:
        utils.print_and_die('Error: %s interface not yet supported or invalid\n'
                      'Supported southbound interfaces: %s' % (sb_interface, SUPPORTED_SB_INTERFACES))
    if nb_interface not in SUPPORTED_NB_INTERFACES:
        utils.print_and_die('Error: %s interface not yet supported or invalid\n'
                      'Supported northbound interfaces: %s' % (nb_interface, SUPPORTED_NB_INTERFACES))
    # Create a new SRv6 controller
    srv6_controller = None
    if args.in_band:
        srv6_controller = InBandSRv6Controller(
            nodes, period, topo_file, topo_graph, pwd, sb_interface,
            nb_interface, secure, key, certificate, grpc_server_ip, grpc_server_port, grpc_client_port,
            min_interval_between_topo_dumps, vpn_dump, verbose
        )
    else:
        srv6_controller = OutOfBandSRv6Controller(
            nodes, period, topo_file, topo_graph, pwd, sb_interface,
            nb_interface, secure, key, certificate, grpc_server_ip, grpc_server_port, grpc_client_port,
            min_interval_between_topo_dumps, vpn_dump, verbose
        )
    # Start the controller
    srv6_controller.run()