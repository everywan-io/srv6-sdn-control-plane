#!/bin/bash


sudo kill $(ps ax | grep -m 1 'python ./srv6_mininet_extension.py' | awk '{print $1}') &> /dev/null
sudo kill $(ps ax | grep -m 1 'python ./ti_extraction.py' | awk '{print $1}') &> /dev/null
sudo kill $(ps ax | grep -m 1 'python ./nb_grpc_server.py' | awk '{print $1}') &> /dev/null


SRV6_SDN_CONTROL_PLANE_PATH="/home/user/repos/srv6-sdn-control-plane/"
SRV6_SDN_DATA_PLANE_PATH="/home/user/repos/srv6-sdn-data-plane/"
SRV6_SDN_MININET_PATH="/home/user/repos/srv6-sdn-mininet/"
TOPOLOGY="topology/"
INTERFACE_DISCOVERY="interface_discovery/"
NB_GRPC="northbound/grpc/"

INBAND=false
IPv6_EMULATION=true

if [ "$INBAND" = false ] ; then
	xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -e "sudo python ./srv6_mininet_extension.py --stop-all"
	sleep 4
	if [ "$IPv6_EMULATION" = true ] ; then
		xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -T MININET -e "sudo python ./srv6_mininet_extension.py --topo topo/example_srv6_topology_with_hosts_ipv6.json"
	else
		xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -T MININET -e "sudo python ./srv6_mininet_extension.py --topo topo/example_srv6_topology_with_hosts_ipv4.json"
	fi
	sleep 6
	xfce4-terminal --working-directory=$(echo $SRV6_SDN_CONTROL_PLANE_PATH$TOPOLOGY) -T "TOPOLOGY INFORMATION EXTRACTION" -e "sudo python ./ti_extraction.py --verbose --ip_ports 2000::1-2606,2000::2-2606,2000::3-2606 --period 3"
	sleep 6
	xfce4-terminal --working-directory=$(echo $SRV6_SDN_CONTROL_PLANE_PATH$INTERFACE_DISCOVERY) -T "INTERFACE DISCOVERY" -e "sudo python ./interface_discovery.py --verbose --ips 2000::1,2000::2,2000::3"
	sleep 4
	xfce4-terminal --working-directory=$(echo $SRV6_SDN_CONTROL_PLANE_PATH$NB_GRPC) -T "NORTHBOUND GRPC SERVER" -e "sudo python ./nb_grpc_server.py --ips 2000::1,2000::2,2000::3"
else
	xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -e "sudo python ./srv6_mininet_extension.py --stop-all"
	sleep 4
	if [ "$IPv6_EMULATION" = true ] ; then
		xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -T MININET -e "sudo python ./srv6_mininet_extension.py --topo topo/example_srv6_topology_with_hosts_and_controller_ipv6.json"
	else
		xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -T MININET -e "sudo python ./srv6_mininet_extension.py --topo topo/example_srv6_topology_with_hosts_and_controller_ipv4.json"
	fi
fi