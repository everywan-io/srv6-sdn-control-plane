#!/bin/bash


sudo kill $(ps ax | grep -m 1 'python ./srv6_mininet_extension.py' | awk '{print $1}') &> /dev/null
sudo kill $(ps ax | grep -m 1 'python ./ti_extraction.py' | awk '{print $1}') &> /dev/null
sudo kill $(ps ax | grep -m 1 'python ./nb_grpc_server.py' | awk '{print $1}') &> /dev/null


SRV6_SDN_CONTROL_PLANE_PATH="/home/user/repos/srv6-sdn-control-plane/"
SRV6_SDN_DATA_PLANE_PATH="/home/user/repos/srv6-sdn-data-plane/"
SRV6_SDN_MININET_PATH="/home/user/repos/srv6-sdn-mininet/"
TOPOLOGY="topology/"
NB_GRPC="northbound/grpc/"

xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -e "sudo python ./srv6_mininet_extension.py --stop-all"

sleep 4

xfce4-terminal --working-directory=$(echo $SRV6_SDN_MININET_PATH) -T MININET -e "sudo python ./srv6_mininet_extension.py --topo topo/example_srv6_topology_with_hosts.json"

sleep 6

xfce4-terminal --working-directory=$(echo $SRV6_SDN_CONTROL_PLANE_PATH$TOPOLOGY) -T "TOPOLOGY INFORMATION EXTRACTION" -e "python ./ti_extraction.py --ip_ports 2000::1-2606,2000::2-2606,2000::3-2606 --period 3"

sleep 4

xfce4-terminal --working-directory=$(echo $SRV6_SDN_CONTROL_PLANE_PATH$NB_GRPC) -T "NORTHBOUND GRPC SERVER" -e "python ./nb_grpc_server.py"

