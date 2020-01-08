#!/usr/bin/python

from __future__ import absolute_import, division, print_function

# General imports
from six import text_type
from argparse import ArgumentParser
from concurrent import futures
import logging
import time
import grpc
import os
import sys
from socket import AF_UNSPEC
from socket import AF_INET
from socket import AF_INET6
# ipaddress dependencies
from ipaddress import IPv6Interface, IPv4Interface
from ipaddress import IPv6Network, IPv4Network, IPv4Address
# SRv6 dependencies
from srv6_sdn_control_plane.northbound.grpc import tunnel_mode
#from srv6_sdn_control_plane.northbound.grpc import gre_tunnel_utils
from srv6_sdn_control_plane.southbound.grpc import sb_grpc_client
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils
#from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import status_codes_pb2
#from srv6_sdn_proto import gre_interface_pb2

# Global variables definition

# Default gRPC client port
DEFAULT_GRPC_CLIENT_PORT = 12345
# Verbose mode
DEFAULT_VERBOSE = False
# Logger reference
logger = logging.getLogger(__name__)

class VXLANTunnel(tunnel_mode.TunnelMode):
    """gRPC request handler"""

    def __init__(self, grpc_client_port=DEFAULT_GRPC_CLIENT_PORT,
                 controller_state=None, verbose=DEFAULT_VERBOSE):
        # Name of the tunnel mode
        self.name = 'VXLAN'
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Verbose mode
        self.verbose = verbose
        # Create SRv6 Manager
        self.srv6_manager = sb_grpc_client.SRv6Manager()
        # Initialize controller state
        self.controller_state = controller_state
        # Initialize controller state
        self.controller_state_vxlan = vxlan_tunnel_utils.ControllerStateVXLAN(controller_state)

    def add_site_to_overlay(self, vni, vtep_name, vrf_name, tableid, vtep_ip_local_site, vtep_ip_remote_site, local_site, remote_site):
        
        id_local_site = local_site.routerid
        mgmt_ip_local_site = self.controller_state.get_router_mgmtip(local_site.routerid)
        #wan_intf_local_site =  not yet implemented 
        vxlan_port_local_site = 4789 # for the first case the vxlan dport is the default one 
        lan_intf_local_site = local_site.interface_name
        lan_sub_remote_site = remote_site.subnets
        wan_ip_remote_site = self.controller_state.get_interface_ipv4(local_site.routerid, remote_site.interface_name)
        

        if id_local_site not in self.controller_state_vxlan.dev_to_vni:
                self.controller_state_vxlan.dev_to_vni[id_local_site] = dict()

        #site does not belong to the new overlay
        if vni not in self.controller_state_vxlan.dev_to_vni[id_local_site]:
                #crete VTEP interface   
                self.srv6_manager.createVxLAN(
                        mgmt_ip_local_site, self.grpc_client_port,
                        ifname=vtep_name, 
                        vxlan_link=wan_intf_local_site
                        vxlan_id=vni,
                        vxlan_port=vxlan_port_local_site
                    )
                
                #add fdb entry 
                self.srv6_manager.addfdbentries(
                        mgmt_ip_local_site, self.grpc_client_port,
                        ifindex=vtep_name,
                        dst=wan_ip_remote_site
                    )
            
                #set vtep ip address
                self.srv6_manager.create_ipaddr(mgmt_ip_local_site, self.grpc_client_port, ip_addr=vtep_ip_local_site, device=vtep_name, net='')
                #create vrf 
                self.srv6_manager.create_vrf_device(
                        mgmt_ip_local_site, self.grpc_client_port,
                        name=vrf_name, table=tableid, interfaces=[lan_intf_local_site, vtep_name]
                    )
                #set route 
                self.srv6_manager.create_iproute(mgmt_ip_local_site, self.grpc_client_port,
                        destination=lan_sub_remote_site, gateway=vtep_ip_remote_site,
                        table=tableid
                    )
                self.controller_state_vxlan.dev_to_vni[id_local_site][vni] = set()
        # site aleady partecipate to this overlay, necessary just to update fdb and set the route for the new site             
        else: 
                #add new fdb entry
                self.srv6_manager.addfdbentries(
                        mgmt_ip_local_site, self.grpc_client_port,
                        ifindex=vtep_name,
                        dst=wan_ip_remote_site
                    )
                #set new route 
                self.srv6_manager.create_iproute(mgmt_ip_local_site, self.grpc_client_port,
                        destination=lan_sub_remote_site, gateway=vtep_ip_remote_site,
                        table=tableid
                    )
            
    def create_overlay(self, overlay_name, overlay_type, site1, site2, tenantid, overlay_info):
        
        id_site1 = site1.routerid
        id_site2 = site2.routerid

        #get VNI for the overlay 
        vni = self.controller_state_vxlan.get_vni(overlay_name)
        if vni = -1 
            vni = self.controller_state.get_new_vni(overlay_name)
        
        
        if (id_site1, id_site2) not in self.controller_state_vxlan.created_overlay:
            self.controller_state_vxlan.created_overlay[(id_site1, id_site2)] = dict()

        # Check if the tunnel does not already exist 
        if vni not in self.controller_state_vxlan.created_overlay[(id_site1, id_site2)]:

                #generate VTEP name 
                vtep_name = 'vxlan-%s-%s' % (overlay_name, vni)
                #get table ID
                tableid = self.controller_state_vxlan.get_new_tableid(overlay_name)
                #generate vrf name  
                vrf_name = 'vrf-%s-%s' % (overlay_name, tableid)
                
                # get VTEP IP address for local site 
                vtep_ip_site1 = self.controller_state_vxlan.get_vtep_ip(id_site1)
                if vtep_ip_site1 = -1 
                    vtep_ip_site1 = self.controller_state_vxlan.get_new_vtep_ip(id_site1)
                # get VTEP IP address site 
                vtep_ip_site2 = self.controller_state_vxlan.get_vtep_ip(id_site2)
                if vtep_ip_site2 = -1 
                    vtep_ip_site2 = self.controller_state_vxlan.get_new_vtep_ip(id_site2)


                self.add_site_to_overlay(vni, vtep_name, vrf_name, tableid, vtep_ip_site1, vtep_ip_site2, site1, site2)
                self.add_site_to_overlay(vni, vtep_name, vrf_name, tableid, vtep_ip_site2, vtep_ip_site1, site2, site1)
                
                # note that was creaed an overlay with a given vni between two sites 
                self.controller_state_vxlan.created_overlay[(id_site1, id_site2)][vni] = set()
        else:
            print('Already exist a VXLAN tunnel with this VNI between the two sites')

        
    def remove_overlay(self, overlay_name):
        # release VNI
        self.controller_state.release_vni(overlay_name)
        # relese table ID 
        self.controller_state.release_tableid(overlay_name)

        # todo: for each site that are in this overlay call remove_site_from_overlay

    def remove_site_from_overlay(self, overlay_name, vtep_name, vrf_name, tableid, mgmt_ip_local_site, lan_sub_local_site, wan_ip_local_site, mgmt_ip_remote_site):
        # remove vtep 
        self.srv6_manager.delVxLAN(
                mgmt_ip_local_site, self.grpc_client_port, 
                ifname = vtep_name)
        # remove vrf device 
        self.srv6_manager.remove_vrf_device(
                mgmt_ip_local_site, self.grpc_client_port, 
                name=vrf_name)
        
    
        # remove route from the remote site         
        self.srv6_manager.remove_iproute(
                mgmt_ip_remote_site, self.grpc_client_port, 
                destination=lan_sub_local_site
                table=tableid)
        # remove fdb entry from the remote site 
        self.srv6_manager.delfdbentries(
                mgmt_ip_remote_site, self.grpc_client_port,
                ifindex=vtep_name,
                dst=wan_ip_local_site)

        # todo: release vtep ip address if there is no more overlays on the local site 
        

    def get_overlays(self):
        raise NotImplementedError
