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
# Topology information extraction
# 
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#

import json
import os
import time, threading
import telnetlib
import re 
import networkx as nx
from networkx.drawing.nx_agraph import write_dot
from networkx.readwrite import json_graph
import socket
import sys
from optparse import OptionParser
from ipaddress import IPv6Network

# Folder of the dump
TOPO_FOLDER = "topo_extraction"
# Folder of the information extracted from OSPF database
OSPF_DB_FOLDER = "%s/ospf_db" % (TOPO_FOLDER)
# Topology file
TOPOLOGY_FILE = "%s/topology.json" % (TOPO_FOLDER)
# Semplified topology file, used to export as an image
GRAPH_TOPO_FILE = "%s/topo_graph.json" % (TOPO_FOLDER)
# Dot topology file, an intermediate representation of the topology used to export as an image
DOT_TOPO_FILE = "%s/topology.dot" % (TOPO_FOLDER)
# Topology image file
SVG_TOPO_FILE = "%s/topology.svg" % (TOPO_FOLDER)
# In our experiment we use srv6 as default password
PASSWD = "srv6"

LOOPBACK_PREFIX = 'fdff::/16'


def topology_information_extraction(opts):
	# Let's parse the input
	period = float(opts.period)
	routers = []
	ports = []
	# First create the chunk
	ips_ports = opts.ips_ports.split(",")
	for ip_port in ips_ports:
		# Then parse the chunk
		data = ip_port.split("-")
		routers.append(data[0])
		ports.append(data[1])

	# Check if TOPO_FOLDER exists, if not create it
	if not os.path.exists(TOPO_FOLDER):
		os.makedirs(TOPO_FOLDER)
	# Check if OSPF_DB_FOLDER exists, if not create it
	if not os.path.exists(OSPF_DB_FOLDER):
		os.makedirs(OSPF_DB_FOLDER)

	while (True):
		# Stub networks dictionary: mapping stub networks to sets of routers advertising the networks
		stub_networks = dict()
		# Transit networks dictionary: mapping transit networks to sets of routers advertising the networks
		transit_networks = dict()
		# Mapping network id to network ipv6 prefix
		netid_to_netprefix = dict()
		# Mapping router id to loopback address
		routerid_to_loopbackip = dict()
		# Mapping graph edges to network prefixes
		edge_to_netprefix = dict()
		# Mapping routers to {interface: prefix} dicts
		routerid_to_interfaces = dict()
		# Mapping router id to the management address of the router
		routerid_to_mgmtip = dict()
		# Mapping management address to the corresponding router id
		mgmtip_to_routerid = dict()
		# Mapping (routerid, intf) to ip address
		intf_to_ip = dict()

		# Edges set
		edges = set()
		# Nodes set
		nodes = set()
		# Topology graph
		G = nx.Graph()

		for router, port in zip(routers, ports):
			print "\n********* Connecting to %s-%s *********" %(router, port)
			password = PASSWD
			try:
				tn = telnetlib.Telnet(router, port) # Init telnet
			except socket.error:
				print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
				break
			if password:
				tn.read_until("Password: ")
				tn.write(password + "\r\n")
			# Terminal length set to 0 to not have interruptions
			tn.write("terminal length 0" + "\r\n")
			# Get routing details from ospf6 database
			tn.write("show ipv6 ospf6 route intra-area detail"+ "\r\n")
			# Close
			tn.write("q" + "\r\n")
			# Get results
			route_details = tn.read_all()

			password = PASSWD
			try:
				tn = telnetlib.Telnet(router, port) # Init telnet
			except socket.error:
				print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
				break
			if password:
				tn.read_until("Password: ")
				tn.write(password + "\r\n")
			# Terminal length set to 0 to not have interruptions
			tn.write("terminal length 0" + "\r\n")
			# Get network details from ospf6 database
			tn.write("show ipv6 ospf6 database network detail"+ "\r\n")
			# Close
			tn.write("q" + "\r\n")
			# Get results
			network_details = tn.read_all()

			password = PASSWD
			try:
				tn = telnetlib.Telnet(router, port) # Init telnet
			except socket.error:
				print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
				break
			if password:
				tn.read_until("Password: ")
				tn.write(password + "\r\n")
			# Terminal length set to 0 to not have interruptions
			tn.write("terminal length 0" + "\r\n")
			# Get interface prefixes details from ospf6 database
			tn.write("show ipv6 ospf6 interface prefix"+ "\r\n")
			# Close
			tn.write("q" + "\r\n")
			# Get results
			interface_prefix = tn.read_all()

			password = PASSWD
			try:
				tn = telnetlib.Telnet(router, port) # Init telnet
			except socket.error:
				print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
				break
			if password:
				tn.read_until("Password: ")
				tn.write(password + "\r\n")
			# Terminal length set to 0 to not have interruptions
			tn.write("terminal length 0" + "\r\n")
			# Turn on privileged mode command
			tn.write("enable" + "\r\n")
			# Get running configuration
			tn.write("show running-config" + "\r\n")
			# Close
			tn.write("q" + "\r\n")
			# Get results
			config_details = tn.read_all()

			password = PASSWD
			try:
				tn = telnetlib.Telnet(router, port) # Init telnet
			except socket.error:
				print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
				break
			if password:
				tn.read_until("Password: ")
				tn.write(password + "\r\n")
			# terminal length set to 0 to not have interruptions
			tn.write("terminal length 0" + "\r\n")
			# Get interface informations from ospf6 database
			tn.write("show ipv6 ospf6 interface"+ "\r\n")
			# Close
			tn.write("q" + "\r\n")
			# Get results
			interface_details = tn.read_all()
			# Close telnet
			tn.close()

			with open("%s/route-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as route_file:
				route_file.write(route_details)    # Write route database to a file for post-processing

			with open("%s/network-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as network_file:
				network_file.write(network_details)    # Write network database to a file for post-processing

			with open("%s/interface-prefix-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as interface_prefix_file:
				interface_prefix_file.write(interface_prefix)    # Write interface prefix information to a file for post-processing

			with open("%s/config-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as config_file:
				config_file.write(config_details)    # Write running configuration information to a file for post-processing

			with open("%s/interface-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as interface_file:
				interface_file.write(interface_details)    # Write interface information to a file for post-processing


			# Process running configuration information
			with open("%s/config-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "r") as config_file:
				# Get router id from the configuration
				for line in config_file:
					m = re.search("router-id (\d*.\d*.\d*.\d*)", line)
					if (m):
						router_id = m.group(1)
						# Update mapping
						mgmtip_to_routerid[router] = router_id
						break

			# Process route database
			with open("%s/route-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "r") as route_file:
				# Process infos and get active routers
				for line in route_file:
					# Get a network prefix
					m = re.search('Destination: (\S+)', line)
					if(m):
						net = m.group(1)
						continue
					# Get link-state id and the router advertising the network
					m = re.search('Intra-Prefix Id: (\d*.\d*.\d*.\d*) Adv: (\d*.\d*.\d*.\d*)', line)
					if(m):
						link_state_id = m.group(1)
						adv_router = m.group(2)
						if IPv6Network(unicode(net)).subnet_of(IPv6Network(unicode(LOOPBACK_PREFIX))):
							# Loopback address of adv_router
							routerid_to_loopbackip[adv_router] = net
							continue
						else:
							# Stub network or transit network
							# Get the network id
							# A network is uniquely identified by a pair (link state_id, advertising router)
							network_id = (link_state_id, adv_router)
							# Map network id to net ipv6 prefix
							netid_to_netprefix[network_id] = net
							if stub_networks.get(net) == None:
								# Network is unknown, mark as a stub network
								# Each network starts as a stub network,
								# then it is processed and (eventually) marked as transit network
								stub_networks[net] = set()
							stub_networks[net].add(adv_router)	# Adv router can reach this net
							nodes.add(adv_router)  # Add router to nodes set

			# Process network database
			transit_networks = dict()
			with open("%s/network-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "r") as network_file:
				# Process infos and get active routers
				for line in network_file:
					# Get a link state id
					m = re.search('Link State ID: (\d*.\d*.\d*.\d*)', line)
					if(m):
						link_state_id = m.group(1)
						continue
					# Get the router advertising the network
					m = re.search('Advertising Router: (\d*.\d*.\d*.\d*)', line)
					if(m):
						adv_router = m.group(1)
						continue
					# Get routers directly connected to the network
					m = re.search('Attached Router: (\d*.\d*.\d*.\d*)', line)
					if(m):
						router_id = m.group(1)
						# Get the network id: a network is uniquely identified by a pair (link state_id, advertising router)
						network_id = (link_state_id, adv_router)
						# Get net ipv6 prefix associated to this network
						net = netid_to_netprefix.get(network_id)
						if net == None:
							# This network does not belong to route database
							# This means that the network is no longer reachable 
							# (a router has been disconnected or an interface has been turned off)
							continue
						# Router can reach this net
						stub_networks[net].add(router_id)

			# Process interface prefixes information of the router to which connected
			with open("%s/interface-prefix-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "r") as interface_prefix_file:
				# Get router id of the router to which connected
				router_id = mgmtip_to_routerid[router]
				for line in interface_prefix_file:
					if "show ipv6 ospf6 interface prefix" in line:
						# Skip command passed to the CLI
						continue
					m = re.search("(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", line)
					if (m):
						# Prefix associated to the interface
						prefix = m.group(3)
						# Interface name
						intf = m.group(5)
						# Update mapping
						if routerid_to_interfaces.get(router_id) == None:
							# If not exists create a new mapping
							routerid_to_interfaces[router_id] = dict()
						routerid_to_interfaces[router_id][intf] = prefix

			# Process interface information of the router to which connected
			with open("%s/interface-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "r") as interface_file:
				# Get router id of the router to which connected
				router_id = mgmtip_to_routerid[router]
				for line in interface_file:
					m = re.search('(\S+) is up,', line)
					if(m):
						# Interface name
						intf = m.group(1)
						if intf_to_ip.get(router_id) == None:
							# If not exists create a new mapping
							intf_to_ip[router_id] = dict()
						continue
					m = re.search('inet6: (\S+)', line)
					if(m):
						# Ip address associated to the interface
						ip = m.group(1)
						# Update mapping
						intf_to_ip[router_id][intf] = ip


		# Make separation between stub networks and transit networks
		for net in stub_networks.keys():
			if len(stub_networks[net]) == 2:    
				# Net advertised by two routers: mark as a transit network
				transit_networks[net] = stub_networks[net]
				stub_networks.pop(net)
			elif len(stub_networks[net]) > 2:
				print "Error: inconsistent network list"
				exit(-1)

		# Build edges list
		for net in transit_networks.keys():
			if len(transit_networks[net]) >= 2:
				# Link between two routers
				r1 = transit_networks[net].pop()
				r2 = transit_networks[net].pop()
				edge=(r1, r2)
				edge_to_netprefix[edge] = net
				edges.add(edge)

		for net in stub_networks.keys():
			if len(stub_networks[net]) >= 1:
				# Link between a router and a stub network
				r = stub_networks[net].pop()
				edge=(r, net)
				edge_to_netprefix[edge] = net
				edges.add(edge)

		# Mapping router id to management ip address
		routerid_to_mgmtip = {v: k for k, v in mgmtip_to_routerid.iteritems()}

		# Print results
		print "Stub Networks:", stub_networks.keys()
		print "Transit Networks:", transit_networks.keys()
		print "Nodes:", nodes
		print "Edges:", edges
		print "***************************************"

		# Build NetworkX Topology

		# Add routers to the graph
		for r in nodes:
			interfaces = dict()
			prefixes = dict()
			loopbackip = "N/A"
			mgmtip = "N/A"
			# Get interface prefixes of the router
			if routerid_to_interfaces.get(r) != None:
				prefixes = routerid_to_interfaces[r]
			# Get loopback ip address of the router
			if routerid_to_loopbackip.get(r) != None:
				loopbackip = routerid_to_loopbackip[r]
			# Get management ip address of the router
			if routerid_to_mgmtip.get(r) != None:
				mgmtip = routerid_to_mgmtip[r]
			# Get interface IPs of the router
			if intf_to_ip.get(r) != None:
				interfaces = intf_to_ip[r]
			G.add_node(r, fillcolor="red", style="filled", shape="ellipse", prefixes= prefixes, interfaces=interfaces,
				loopbackip=loopbackip, mgmtip=mgmtip, type="router")

		# Add stub networks to the graph
		for r in stub_networks.keys():
			G.add_node(r, fillcolor="cyan", style="filled", shape="box", type="stub_network")

		# Add core links and edge links to the graph
		for e in edges:
			lhs_intf = "N/A"
			lhs_ip = "N/A"
			rhs_intf = "N/A"
			rhs_ip = "N/A"
			net = "N/A"
			#Get network prefix associated to the link
			if edge_to_netprefix.get(e) != None:
				net = edge_to_netprefix[e]
			# Get the name of the left interface
			if routerid_to_interfaces.get(e[0]) != None:
				lhs_intf = routerid_to_interfaces[e[0]]
				lhs_intf = lhs_intf.keys()[lhs_intf.values().index(net)]
			# Get the ip address of the left interface
			if intf_to_ip.get(e[0]) and intf_to_ip[e[0]].get(lhs_intf):
				lhs_ip = intf_to_ip[e[0]][lhs_intf]
			# Get the name of the right interface
			if routerid_to_interfaces.get(e[1]) != None:
				rhs_intf = routerid_to_interfaces[e[1]]
				rhs_intf = rhs_intf.keys()[rhs_intf.values().index(net)]
			# Get the ip address of the right interface
			if intf_to_ip.get(e[1]) and intf_to_ip[e[1]].get(rhs_intf):
				rhs_ip = intf_to_ip[e[1]][rhs_intf]
			# Add edge to the graph
			if (e[0] in nodes and e[1] in stub_networks.keys()) or (e[1] in nodes and e[0] in stub_networks.keys()):
				# This is a stub network, no label on the edge
				G.add_edge(*e, label="", lhs_intf=lhs_intf, lhs_ip=lhs_ip, rhs_intf=rhs_intf, rhs_ip=rhs_ip, net=net)
			elif (e[0] in nodes and e[1] in nodes):
				# This is a transit network, put a label on the edge
				G.add_edge(*e, label=net, lhs_intf=lhs_intf, lhs_ip=lhs_ip, rhs_intf=rhs_intf, rhs_ip=rhs_ip, net=net)

		# Dump relevant information of the network graph
		dump_topo(G)
		# Export the network graph as an image file
		draw_topo(G)

		# Wait 'period' seconds between two extractions
		time.sleep(period)


# Utility function to export the network graph as an image file
def draw_topo(G):
    write_dot(G, DOT_TOPO_FILE)
    os.system('dot -Tsvg %s -o %s' %(DOT_TOPO_FILE, SVG_TOPO_FILE))


# Utility function to dump relevant information of the topology
def dump_topo(G):
	# Export NetworkX object into a json file
	# Json dump of the topology
	with open(TOPOLOGY_FILE, 'w') as outfile:
		# Get json topology
		json_topology = json_graph.node_link_data(G)
		# Convert links
		json_topology['links'] = [
		    {
		        'source_id': json_topology['nodes'][link['source']]['id'],
		        'target_id': json_topology['nodes'][link['target']]['id'],
		        'source': link['source'],
		        'target': link['target'],
		        'lhs_intf': link['lhs_intf'],
		        'rhs_intf': link['rhs_intf'],
		        'lhs_ip': link['lhs_ip'],
		        'rhs_ip': link['rhs_ip'],
		        'net': link['net']
		    }
		    for link in json_topology['links']]
		# Convert nodes
		json_topology['nodes'] = [
		    {
		        'id': node['id'],
		        'interfaces': node['interfaces'],
		        'prefixes': node['prefixes'],
		        'loopbackip':node['loopbackip'],
		        'mgmtip': node['mgmtip'],
		        'type': node['type']
		    }
		    if node['type'] == 'router'
		    else # stub network
		    {
		        'id': node['id'],
		        'type': node['type']
		    }
		    for node in json_topology['nodes']]
		# Dump the topology
		json.dump(json_topology, outfile, sort_keys = True, indent = 2)


# Parse command line options and dump results
def parseOptions():
	parser = OptionParser()
	# ip:port of the routers
	parser.add_option('--ip_ports', dest='ips_ports', type='string', default="127.0.0.1-2606",
					  help='ip-port,ip-port map ip port of the routers')
	# Topology information extraction period
	parser.add_option('--period', dest='period', type='string', default="10",
					  help='topology information extraction period')
	# Parse input parameters
	(options, args) = parser.parse_args()
	# Done, return
	return options

if __name__ == '__main__':
	# Let's parse input parameters
	opts = parseOptions()
	# Deploy topology
	topology_information_extraction(opts)
