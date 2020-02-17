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
from srv6_sdn_controller_state import srv6_sdn_controller_state

from srv6_sdn_control_plane import srv6_controller_utils
#from srv6_sdn_proto import srv6_vpn_pb2
from srv6_sdn_proto import status_codes_pb2
#from srv6_sdn_proto import gre_interface_pb2

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
        # Initialize vxlan controller state
        self.controller_state_vxlan = vxlan_tunnel_utils.ControllerStateVXLAN(controller_state)
        # Initialize controller state 
        self.controller_state = srv6_sdn_controller_state
        # Get connection to MongoDB
        client = self.controller_state.get_mongodb_session()
        # Get the database
        db = client.EveryWan
        # Get collection
        self.slices_in_overlay = db.slices_in_overlay
        # Oldo controller state 
        self.SDWANControllerState = controller_state

    def add_slice_to_overlay(self, overlay_name, routerid, interface_name, tenantid, overlay_info):
        # Get device management IP address
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # get table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # get VRF name   
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
        # get devices ID
        id_remote_site = remote_site[0]
        id_local_site = local_site[0]
        # get management IP address for local and remote site 
        mgmt_ip_local_site = self.controller_state.get_router_mgmtip(local_site[0])
        mgmt_ip_remote_site = self.controller_state.get_router_mgmtip(remote_site[0])
        # get subnet for local and remote site 
        lan_sub_remote_site = self.controller_state.get_ip_subnets(id_remote_site, remote_site[1])[0]
        lan_sub_local_site = self.controller_state.get_ip_subnets(id_local_site, local_site[1])[0]
        # get table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # get VTEP IP remote site and local site 
        vtep_ip_remote_site = self.controller_state_vxlan.get_vtep_ip(id_remote_site, tenantid)
        vtep_ip_local_site = self.controller_state_vxlan.get_vtep_ip(id_local_site, tenantid)
        # get VNI 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid)
        # get VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        # get WAN interface name for local site and remote site 
        wan_intf_local_site = self.controller_state.get_wan_interfaces(id_local_site)[0]
        wan_intf_remote_site = self.controller_state.get_wan_interfaces(id_remote_site)[0]
        # get external IP address for loal site and remote site 
        wan_ip_local_site = self.controller_state.get_ext_ipv4_addresses(id_local_site, wan_intf_local_site)[0].split("/")[0]
        wan_ip_remote_site = self.controller_state.get_ext_ipv4_addresses(id_remote_site, wan_intf_remote_site)[0].split("/")[0]
        # DB key creation, one per tunnel direction  
        key_local_to_remote = '%s-%s' % (id_local_site, id_remote_site)
        key_remote_to_local = '%s-%s' % (id_remote_site, id_local_site)
        # get tunnel dictionary from DB 
        slices_in_overlay_local = self.slices_in_overlay.find_one({'tunnel_key': key_local_to_remote})
        slices_in_overlay_remote = self.slices_in_overlay.find_one({'tunnel_key': key_remote_to_local})
        # Create VNI key 
        vni_key = 'vni_%s' % (vni)
        # If it's the first overlay for the devices, create dictionaries   
        if slices_in_overlay_local == None:
            slices_in_overlay_local = {
                'tunnel_key': key_local_to_remote, 
                'vnis': {}
            }     
        if slices_in_overlay_remote == None:
            slices_in_overlay_remote = {
                'tunnel_key': key_remote_to_local, 
                'vnis': {}
            }
        # If the local device is not yet part of this overlay 
        if vni_key not in slices_in_overlay_local['vnis']:
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
            # update local dictionary with the new VNI
            slices_in_overlay_local['vnis'][vni_key] = {'vni':vni, 'interfaces': [] }
        # If the remote device is not yet part of this overlay 
        if vni_key not in slices_in_overlay_remote['vnis']:
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
            # update local dictionary with the new VNI
            slices_in_overlay_remote['vnis'][vni_key] = {'vni':vni, 'interfaces': [] } 
        # set route in local site for the remote subnet, if not present  
        if lan_sub_remote_site not in slices_in_overlay_local['vnis'].get(vni_key).get('interfaces'):
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
            # update local dictionary with the new subnet in overlay 
            slices_in_overlay_local['vnis'].get(vni_key).get('interfaces').append(lan_sub_remote_site)
        # set route in remote site for the local subnet, if not present 
        if lan_sub_local_site not in slices_in_overlay_remote['vnis'].get(vni_key).get('interfaces'): 
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
            # update local dictionary with the new subnet in overlay 
            slices_in_overlay_remote['vnis'].get(vni_key).get('interfaces').append(lan_sub_local_site)
        # Insert the device overlay state in MongodB, if there isn already a state update it 
        self.slices_in_overlay.update({'tunnel_key': key_local_to_remote}, {'$set': slices_in_overlay_local}, upsert=True)
        self.slices_in_overlay.update({'tunnel_key': key_remote_to_local}, {'$set': slices_in_overlay_remote}, upsert=True)

    def init_overlay(self, overlay_name, overlay_type, tenantid, routerid, overlay_info):
        # get device management IP address
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # Get vxlan port set by user 
        vxlan_port_site = self.SDWANControllerState.tenant_info[tenantid].get('port')
        # get table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # get VRF name   
        vrf_name = 'vrf-%s' % (tableid)
        # get WAN interface 
        wan_intf_site = self.controller_state.get_wan_interfaces(routerid)[0]
        # get VNI for the overlay 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid) 
        # get VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        # get VTEP IP address
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
        # get VNI  
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid) 
        if vni == -1: 
            vni = self.controller_state_vxlan.get_new_vni(overlay_name, tenantid)
        # get table ID
        tableid = self.controller_state_vxlan.get_new_tableid(overlay_name, tenantid)
        if tableid == -1:
            tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)

    def init_tunnel_mode(self, routerid, tenantid, overlay_info):
        # get VTEP IP address 
        vtep_ip_site = self.controller_state_vxlan.get_vtep_ip(routerid, tenantid)
        if vtep_ip_site == -1: 
            vtep_ip_site = self.controller_state_vxlan.get_new_vtep_ip(routerid, tenantid)

    def remove_slice_from_overlay(self, overlay_name, routerid, interface_name, tenantid, overlay_info):
        # get device management IP address 
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # get table ID
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # get VRF name  
        vrf_name = 'vrf-%s' % (tableid) 
        # Remove slice from VRF
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
        # get devices ID 
        id_local_site = local_site[0]
        id_remote_site = remote_site[0]
        # get VNI
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid)
        # get management IP local and remote site 
        mgmt_ip_remote_site = self.controller_state.get_router_mgmtip(id_remote_site)
        mgmt_ip_local_site = self.controller_state.get_router_mgmtip(id_local_site)
        # get WAN interface name for local site and remote site
        wan_intf_local_site = self.controller_state.get_wan_interfaces(id_local_site)[0]
        wan_intf_remote_site = self.controller_state.get_wan_interfaces(id_remote_site)[0]
        # get external IP address for local site and remote site
        wan_ip_local_site = self.controller_state.get_ext_ipv4_addresses(id_local_site, wan_intf_local_site)[0].split("/")[0]
        wan_ip_remote_site = self.controller_state.get_ext_ipv4_addresses(id_remote_site, wan_intf_remote_site)[0].split("/")[0]  
        # get local and remote subnet   
        lan_sub_local_site = self.controller_state.get_ip_subnets(id_local_site, local_site[1])[0]
        lan_sub_remote_site = self.controller_state.get_ip_subnets(id_remote_site, remote_site[1])[0]
        # get table ID
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # get VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        # DB key creation, one per tunnel direction  
        key_local_to_remote = '%s-%s' % (id_local_site, id_remote_site)
        key_remote_to_local = '%s-%s' % (id_remote_site, id_local_site)
        # get tunnel dictionary from DB 
        slices_in_overlay_local = self.slices_in_overlay.find_one({'tunnel_key': key_local_to_remote})
        slices_in_overlay_remote = self.slices_in_overlay.find_one({'tunnel_key': key_remote_to_local})
        # Create VNI key 
        vni_key = 'vni_%s' % (vni)
        # Check if the remote device has not yet been removed from the overlay
        if vni_key in slices_in_overlay_remote['vnis']:
            # Check if there is the route for the local subnet in the remote device 
            if lan_sub_local_site in slices_in_overlay_remote['vnis'].get(vni_key).get('interfaces'):
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
                # update local dictionary
                slices_in_overlay_remote['vnis'].get(vni_key).get('interfaces').remove(lan_sub_local_site)
        # Check if the subnet removed is the last subnet in the considered overlay in the local site 
        if vni_key not in slices_in_overlay_remote['vnis'] or len(slices_in_overlay_remote['vnis'].get(vni_key).get('interfaces')) == 0:
            # Check if there is the route for remote subnet in the local device 
            if lan_sub_remote_site in slices_in_overlay_local['vnis'].get(vni_key).get('interfaces'):
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
                # update local dictionary 
                slices_in_overlay_local['vnis'].get(vni_key).get('interfaces').remove(lan_sub_remote_site)
            # Check if the remote device has not yet been removed from the overlay
            if vni_key in slices_in_overlay_remote['vnis']:
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
                # update local dictionary 
                del slices_in_overlay_remote['vnis'][vni_key]
            # Check if there are no more remote subnets reachable from the local site 
            if len(slices_in_overlay_local['vnis'].get(vni_key).get('interfaces')) == 0:
                # Check if the local device partecipate in the overlay 
                if vni_key in slices_in_overlay_local['vnis']:
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
                    # update local dictionary 
                    del slices_in_overlay_local['vnis'][vni_key]
        # If there are no more overlay on the devices destroy data structure, else update it  
        if slices_in_overlay_local['vnis'] == {} and slices_in_overlay_remote['vnis'] == {}:
            self.slices_in_overlay.remove({'tunnel_key': key_local_to_remote})
            self.slices_in_overlay.remove({'tunnel_key': key_remote_to_local})
        else:
            self.slices_in_overlay.update({'tunnel_key': key_local_to_remote}, {'$set': slices_in_overlay_local}, upsert=True)
            self.slices_in_overlay.update({'tunnel_key': key_remote_to_local}, {'$set': slices_in_overlay_remote}, upsert=True)    

    def destroy_overlay(self, overlay_name, overlay_type, tenantid, routerid, overlay_info):
        # get device management IP address
        mgmt_ip_site = self.controller_state.get_router_mgmtip(routerid)
        # get VNI 
        vni = self.controller_state_vxlan.get_vni(overlay_name, tenantid)
        # get table ID 
        tableid = self.controller_state_vxlan.get_tableid(overlay_name, tenantid)
        # get VRF name   
        vrf_name = 'vrf-%s' % (tableid)
        # get VTEP name 
        vtep_name = 'vxlan-%s' %  (vni)
        # get VTEP IP address
        vtep_ip_site = self.controller_state_vxlan.get_vtep_ip(routerid, tenantid)
        # get VTEP IP address 
        response = self.srv6_manager.remove_ipaddr(
            mgmt_ip_site, self.grpc_client_port,
            ip_addr = vtep_ip_site,
            device = vtep_name
        )
        if response != STATUS_SUCCESS:
            # If the operation has failed, report an error message
            logger.warning('Cannot remove the address %s of VTEP %s in %s'
                        % (vtep_ip_site, vtep_name, mgmt_ip_site))
            return STATUS_INTERNAL_ERROR
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

