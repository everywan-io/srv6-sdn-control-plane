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

import errno

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
		routerid_to_loopbacknet = dict()
		# Mapping graph edges to network prefixes
		edge_to_netprefix = dict()

		# Edges set
		edges = set()
		# Nodes set
		nodes = set()
		# Topology graph
		G = nx.Graph()

		for router, port in zip(routers, ports):
			print "\n********* Connecting to %s-%s *********" %(router, port)
			password = PASSWD
			while True:  # or some amount of retries
				try:
					tn = telnetlib.Telnet(router, port, 3) # Init telnet
					break
				except socket.timeout:
					print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
					tn = None
					break
				except socket.error as (code, msg):
					if code != errno.EINTR:
						print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
						tn = None
						break
			if tn == None:
				continue
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
			while True:  # or some amount of retries
				try:
					tn = telnetlib.Telnet(router, port, 3) # Init telnet
					break
				except socket.timeout:
					print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
					tn = None
					break
				except socket.error as (code, msg):
					if code != errno.EINTR:
						print "Error: cannot establish a connection to " + str(router) + " on port " + str(port) + "\n"
						tn = None
						break
			if tn == None:
				continue
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

			with open("%s/route-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as route_file:
				route_file.write(route_details)    # Write route database to a file for post-processing

			with open("%s/network-detail-%s-%s.txt" %(OSPF_DB_FOLDER , router, port), "w") as network_file:
				network_file.write(network_details)    # Write network database to a file for post-processing

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
						nodes.add(adv_router)  # Add router to nodes set
						if IPv6Network(unicode(net)).subnet_of(IPv6Network(unicode(LOOPBACK_PREFIX))):
							# Loopback address of adv_router
							routerid_to_loopbacknet[adv_router] = net
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
						nodes.add(adv_router)  # Add router to nodes set
						nodes.add(router_id)  # Add router to nodes set


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

		# Print results
		print "Stub Networks:", stub_networks.keys()
		print "Transit Networks:", transit_networks.keys()
		print "Nodes:", nodes
		print "Edges:", edges
		print "***************************************\n\n"

		# Build NetworkX Topology

		# Add routers to the graph
		for r in nodes:
			loopbacknet = ""
			# Get loopback ip address of the router
			if routerid_to_loopbacknet.get(r) != None:
				loopbacknet = routerid_to_loopbacknet[r]
				loopbackip = str(next(IPv6Network(unicode(loopbacknet)).hosts()))
				G.add_node(r, fillcolor="red", style="filled", shape="ellipse", loopbacknet=loopbacknet, loopbackip=loopbackip, type="router")

		# Add stub networks to the graph
		for r in stub_networks.keys():
			G.add_node(r, fillcolor="cyan", style="filled", shape="box", type="stub_network")

		# Add core links and edge links to the graph
		for e in edges:
			net = ""
			# Get network prefix associated to the link
			if edge_to_netprefix.get(e) != None:
				net = edge_to_netprefix[e]
			# Add edge to the graph
			if (e[0] in nodes and e[1] in stub_networks.keys()) or (e[1] in nodes and e[0] in stub_networks.keys()):
				# This is a stub network, no label on the edge
				G.add_edge(*e, label="", fontsize=9, net=net)
			elif (e[0] in nodes and e[1] in nodes):
				# This is a transit network, put a label on the edge
				G.add_edge(*e, label=net, fontsize=9, net=net)

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
	print TOPOLOGY_FILE
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
		        'net': link['net']
		    }
		    for link in json_topology['links']]
		# Convert nodes
		json_topology['nodes'] = [
		    {
		        'id': node['id'],
		        'loopbacknet':node['loopbacknet'],
		        'loopbackip':node['loopbackip'],
		        'type': node.get('type', "")
		    }
		    if node.get('type') == 'router'
		    else # stub network
		    {
		        'id': node['id'],
		        'type': node.get('type', "")
		    }
		    for node in json_topology['nodes']]
		# Dump the topology
		json.dump(json_topology, outfile, sort_keys = True, indent = 2)

# Parse command line options and dump results
def parseOptions():
	global TOPO_FOLDER, OSPF_DB_FOLDER, TOPOLOGY_FILE, GRAPH_TOPO_FILE, DOT_TOPO_FILE, SVG_TOPO_FILE
	parser = OptionParser()
	# ip:port of the routers
	parser.add_option('--ip_ports', dest='ips_ports', type='string', default="127.0.0.1-2606",
					  help='ip-port,ip-port map ip port of the routers')
	# Output directory
	parser.add_option('--out_dir', dest='out_dir', type='string', default=".",
					  help='output directory')
	# Topology information extraction period
	parser.add_option('--period', dest='period', type='string', default="10",
					  help='topology information extraction period')
	# Parse input parameters
	(options, args) = parser.parse_args()
	TOPO_FOLDER = "%s/%s" % (options.out_dir, TOPO_FOLDER)
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
	# Done, return
	return options

if __name__ == '__main__':
	# Let's parse input parameters
	opts = parseOptions()
	# Deploy topology
	topology_information_extraction(opts)
