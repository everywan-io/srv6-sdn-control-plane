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
from srv6_sdn_control_plane.northbound.grpc import vxlan_tunnel_utils
from srv6_sdn_control_plane.southbound.grpc import sb_grpc_client
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils
#from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import status_codes_pb2
#from srv6_sdn_proto import gre_interface_pb2

# Global variables definition

# Status codes
STATUS_SUCCESS = status_codes_pb2.STATUS_SUCCESS
STATUS_INTERNAL_ERROR = status_codes_pb2.STATUS_INTERNAL_ERROR

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
        

    def add_slice_to_overlay(self, overlay_name, routerid, interface_name, tenantid, overlay_info):
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # retrive table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # retrive VRF name   
        vrf_name = 'vrf-%s' % (tableid)
        # add slice to the VRF
        response = self.srv6_manager.update_vrf_device(
            mgmt_ip_site, self.grpc_client_port,
            name=vrf_name,
            interfaces=[interface_name],
            op='add_interfaces'
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot add interface %s to the VRF %s in %s'
                            % (interface_name, vrf_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR
              
    def create_tunnel(self, overlay_name, overlay_type, local_site, remote_site, tenantid, overlay_info):
        id_remote_site = remote_site.routerid
        id_local_site = local_site.routerid
        # retrive management IP address for local and remote site 
        mgmt_ip_local_site = self.controller_state.get_router_mgmtip(local_site.routerid)
        mgmt_ip_remote_site = self.controller_state.get_router_mgmtip(remote_site.routerid)
        # retrive subnet for local and remote site 
        lan_sub_remote_site = self.controller_state.get_subnets_on_interface(id_remote_site, remote_site.interface_name)[0]
        lan_sub_local_site = self.controller_state.get_subnets_on_interface(id_local_site, local_site.interface_name)[0]
        # retriv table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # retrive VTEP IP remote site and local site 
        vtep_ip_remote_site = self.controller_state_vxlan.get_vtep_ip(id_remote_site, tenantid)
        vtep_ip_local_site = self.controller_state_vxlan.get_vtep_ip(id_local_site, tenantid)
        # retrive VNI 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid)
        # retrive VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        # retrive WAN IP address for loal site and remote site 
        wan_intf_local_site = self.controller_state.get_wan_interface(id_local_site)
        #wan_ip_local_site = self.controller_state.get_interface_ipv4(id_local_site, wan_intf_local_site)[0].split('/')[0]
        wan_intf_remote_site = self.controller_state.get_wan_interface(id_remote_site)
        #wan_ip_remote_site = self.controller_state.get_interface_ipv4(id_remote_site, wan_intf_remote_site)[0].split('/')[0]
        
        wan_ip_local_site = self.controller_state.get_external_ipv4(id_local_site, wan_intf_local_site)[0].split("/")[0]
        wan_ip_remote_site = self.controller_state.get_external_ipv4(id_remote_site, wan_intf_remote_site)[0].split("/")[0]
         
        if (id_local_site, id_remote_site) not in self.controller_state_vxlan.slice_in_overlay:
            self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)] = dict()

        if (id_remote_site, id_local_site) not in self.controller_state_vxlan.slice_in_overlay:
            self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)] = dict()
        
        if vni not in self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)]:
            # add FDB entry in local site 
            response = self.srv6_manager.addfdbentries(
                    mgmt_ip_local_site, self.grpc_client_port,
                    ifindex=vtep_name,
                    dst=wan_ip_remote_site
                )
            if response != STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot add FDB entry %s for VTEP %s in %s'
                               % (wan_ip_remote_site, vtep_name, mgmt_ip_local_site))
                return STATUS_INTERNAL_ERROR

            self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)][vni] = set()

        if vni not in self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)]:    
            # add FDB entry in remote site 
            response = self.srv6_manager.addfdbentries(
                    mgmt_ip_remote_site, self.grpc_client_port,
                    ifindex=vtep_name,
                    dst=wan_ip_local_site
                )
            if response != STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot add FDB entry %s for VTEP %s in %s'
                               % (wan_ip_local_site, vtep_name, mgmt_ip_remote_site))
                return STATUS_INTERNAL_ERROR

            self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)][vni] = set()

        if lan_sub_remote_site not in self.controller_state_vxlan.slice_in_overlay[(id_local_site,id_remote_site)][vni]:
            # set route in local site  
            response = self.srv6_manager.create_iproute(
                    mgmt_ip_local_site, self.grpc_client_port,
                    destination=lan_sub_remote_site, gateway=vtep_ip_remote_site.split("/")[0],
                    table=tableid
                )
            if response != STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot set route for %s in %s '
                               % (wan_ip_remote_site, mgmt_ip_local_site))
                return STATUS_INTERNAL_ERROR
            
            self.controller_state_vxlan.slice_in_overlay[(id_local_site,id_remote_site)][vni].add(lan_sub_remote_site)

        if lan_sub_local_site not in self.controller_state_vxlan.slice_in_overlay[(id_remote_site,id_local_site)][vni]:
            # set route in remote site 
            response = self.srv6_manager.create_iproute(
                    mgmt_ip_remote_site, self.grpc_client_port,
                    destination=lan_sub_local_site, gateway=vtep_ip_local_site.split("/")[0],
                    table=tableid
                )  
            if response != STATUS_SUCCESS:
                # If the operation has failed, report an error message
                logger.warning('Cannot set route for %s in %s '
                               % (lan_sub_local_site, mgmt_ip_remote_site))
                return STATUS_INTERNAL_ERROR          
            self.controller_state_vxlan.slice_in_overlay[(id_remote_site,id_local_site)][vni].add(lan_sub_local_site)

    def init_overlay(self, overlay_name, overlay_type, tenantid, routerid, overlay_info):
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # for the first case the vxlan dport is the default one 
        vxlan_port_site = 4789 
        # retrive table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # retrive VRF name   
        vrf_name = 'vrf-%s' % (tableid)
        # get WAN interface 
        wan_intf_site = self.controller_state.get_wan_interface(routerid)
        # retrive VNI for the overlay 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid) 
        # retrive VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        # retrive VTEP IP address
        vtep_ip_site = self.controller_state_vxlan.get_vtep_ip(routerid, tenantid)
        
        # crete VTEP interface
        response = self.srv6_manager.createVxLAN(
                mgmt_ip_site, self.grpc_client_port,
                ifname=vtep_name, 
                vxlan_link=wan_intf_site,
                vxlan_id=vni,
                vxlan_port=vxlan_port_site
            )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot create VTEP %s in %s'
                            % (vtep_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR

        # set VTEP IP address
        response = self.srv6_manager.create_ipaddr(mgmt_ip_site, self.grpc_client_port, ip_addr=vtep_ip_site, device=vtep_name, net='')
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot set IP %s for VTEP %s in %s'
                            % (vtep_ip_site, vtep_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR
        # create VRF and add the VTEP interface 
        response = self.srv6_manager.create_vrf_device(
                mgmt_ip_site, self.grpc_client_port,
                name=vrf_name, table=tableid, interfaces=[vtep_name]
                )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot create VRF %s in %s'
                            % (vrf_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR
        
    def init_overlay_data(self, overlay_name, tenantid, overlay_info):
        #get VNI for the overlay 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid) 
        if vni == -1: 
            vni = self.controller_state_vxlan.get_new_vni(overlay_name, tenantid)

        #get table ID
        tableid = self.controller_state_vxlan.get_new_tableid(overlay_name, tenantid)
        if tableid == -1:
            tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)

    def init_tunnel_mode(self, routerid, tenantid, overlay_info):
        # get VTEP IP address for site1
        vtep_ip_site = self.controller_state_vxlan.get_vtep_ip(routerid, tenantid)
        if vtep_ip_site == -1: 
            vtep_ip_site = self.controller_state_vxlan.get_new_vtep_ip(routerid, tenantid)

    def remove_slice_from_overlay(self, overlay_name, routerid, interface_name, tenantid, overlay_info):
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # retrive table ID
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # retrive VRF name  
        vrf_name = 'vrf-%s' % (tableid) 
        
        response = self.srv6_manager.update_vrf_device(
                mgmt_ip_site, self.grpc_client_port,
                name=vrf_name,
                interfaces=[interface_name],
                op = 'del_interfaces'
            ) 
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot remove interface %s from VRF %s in %s'
                            % (interface_name, vrf_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR
        
    def remove_tunnel(self, overlay_name, overlay_type, local_site, remote_site, tenantid, overlay_info):
        id_local_site = local_site.routerid
        id_remote_site = remote_site.routerid
        # retrive VNI
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid)
        # retrive management IP local and remote site 
        mgmt_ip_remote_site = self.controller_state.get_router_mgmtip(id_remote_site)
        mgmt_ip_local_site = self.controller_state.get_router_mgmtip(id_local_site)
        # retrive wan IP local and remote site 
        wan_intf_local_site = self.controller_state.get_wan_interface(id_local_site)
        #wan_ip_local_site = self.controller_state.get_interface_ipv4(id_local_site, wan_intf_local_site)[0].split('/')[0]
        wan_intf_remote_site = self.controller_state.get_wan_interface(id_remote_site)
        #wan_ip_remote_site = self.controller_state.get_interface_ipv4(id_remote_site, wan_intf_remote_site)[0].split('/')[0]

        wan_ip_local_site = self.controller_state.get_external_ipv4(id_local_site, wan_intf_local_site)[0].split("/")[0]
        wan_ip_remote_site = self.controller_state.get_external_ipv4(id_remote_site, wan_intf_remote_site)[0].split("/")[0]
              
        # retrive subnet local and remote site  
        lan_sub_local_site = self.controller_state.get_subnets_on_interface(id_local_site, local_site.interface_name)[0]
        lan_sub_remote_site = self.controller_state.get_subnets_on_interface(id_remote_site, remote_site.interface_name)[0]
        # retrive table ID
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # retrive VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)

        if vni in self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)]:
            if lan_sub_local_site in self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)][vni]:
                # remove route in remote site         
                response = self.srv6_manager.remove_iproute(
                        mgmt_ip_remote_site, self.grpc_client_port, 
                        destination=lan_sub_local_site,
                        table=tableid
                    )
                if response != STATUS_SUCCESS:
                    # If the operation has failed, report an error message
                    logger.warning('Cannot remove route to %s in %s'
                                % (lan_sub_local_site, mgmt_ip_remote_site))
                    return STATUS_INTERNAL_ERROR

                self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)][vni].remove(lan_sub_local_site) 
                
            # The slice removed is the last slice in the considered overlay in the local site 
            if len(self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)][vni]) == 0:
            
                if lan_sub_remote_site in self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)][vni]:
                    # remove route in local site 
                    response = self.srv6_manager.remove_iproute(
                            mgmt_ip_local_site, self.grpc_client_port,
                            destination=lan_sub_remote_site,
                            table=tableid
                        )
                    if response != STATUS_SUCCESS:
                        # If the operation has failed, report an error message
                        logger.warning('Cannot remove route to %s in %s'
                                    % (lan_sub_remote_site, mgmt_ip_local_site))
                        return STATUS_INTERNAL_ERROR

                    self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)][vni].remove(lan_sub_remote_site)
            
                if vni in self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)]:
                    # remove FDB entry in local site 
                    response = self.srv6_manager.delfdbentries(
                            mgmt_ip_local_site, self.grpc_client_port,
                            ifindex=vtep_name,
                            dst=wan_ip_remote_site
                        )
                    if response != STATUS_SUCCESS:
                        # If the operation has failed, report an error message
                        logger.warning('Cannot remove FDB entry %s in %s'
                                    % (wan_ip_remote_site, mgmt_ip_local_site))
                        return STATUS_INTERNAL_ERROR

                    del self.controller_state_vxlan.slice_in_overlay[(id_local_site, id_remote_site)][vni]

                if vni in self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)]:
                # remove FDB entry in remote site 
                    response = self.srv6_manager.delfdbentries(
                            mgmt_ip_remote_site, self.grpc_client_port,
                            ifindex=vtep_name,
                            dst=wan_ip_local_site
                        )
                    if response != STATUS_SUCCESS:
                        # If the operation has failed, report an error message
                        logger.warning('Cannot remove FDB entry %s in %s'
                                    % (wan_ip_local_site, mgmt_ip_remote_site))
                        return STATUS_INTERNAL_ERROR

                    del self.controller_state_vxlan.slice_in_overlay[(id_remote_site, id_local_site)][vni]

    def destroy_overlay(self, overlay_name, overlay_type, tenantid, routerid, overlay_info):
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # retrive VNI 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid)
        # retrive table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # retrive VRF name   
        vrf_name = 'vrf-%s' % (tableid)
        # retrive VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        
        # remove VTEP 
        response = self.srv6_manager.delVxLAN(
                mgmt_ip_site, self.grpc_client_port, 
                ifname = vtep_name
            )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot remove VTEP %s in %s'
                        % (vtep_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR

        # remove VRF device 
        response = self.srv6_manager.remove_vrf_device(
                mgmt_ip_site, self.grpc_client_port, 
                name=vrf_name
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot remove VRF %s in %s'
                        % (vrf_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR
 
    def destroy_overlay_data(self, overlay_name, tenantid, overlay_info):
        # release VNI 
        self.controller_state_vxlan.release_vni(overlay_name, tenantid)
        # release tableid 
        self.controller_state_vxlan.release_tableid(overlay_name, tenantid )
    
    def destroy_tunnel_mode(self, routerid, tenantid, overlay_info):
        # release VTEP IP address if no more VTEP on the EDGE device 
        self.controller_state_vxlan.release_vtep_ip(routerid, tenantid)

    def get_overlays(self):
        raise NotImplementedError

