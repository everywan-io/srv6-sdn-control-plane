#!/usr/bin/python

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
from srv6_sdn_controller_state import srv6_sdn_controller_state
# ipaddress dependencies
from ipaddress import IPv4Interface
from ipaddress import IPv6Interface
from ipaddress import AddressValueError
from ipaddress import IPv4Network
# NetworkX dependencies
import networkx as nx
from networkx.readwrite import json_graph
# SRv6 dependencies
from srv6_generators import SIDAllocator

ZEBRA_PORT = 2601
SSH_PORT = 22
MIN_TABLE_ID = 2
# Linux kernel supports up to 255 different tables
MAX_TABLE_ID = 255
# Table for local routes 
LOCAL_SID_TABLE = 1
# Reserved table IDs
RESERVED_TABLEIDS = [0, 253, 254, 255]
RESERVED_TABLEIDS.append(LOCAL_SID_TABLE)

WAIT_TOPOLOGY_INTERVAL = 1

# Logger reference
logger = logging.getLogger(__name__)

RESERVED_VNI = [0, 1]
RESERVED_VTEP_IP = [0, 65536]

class ControllerStateVXLAN:
    """This class maintains the state of the SRv6 controller and provides some
       methods to handle it
    """

    def __init__(self, controller_state):
        # Create Table IDs allocator
        self.tableid_allocator = controller_state.tableid_allocator
        # Create VNI allocator
        self.vni_allocator = VNIAllocator()
        # Create VTEP IP allocator 
        self.vtep_ip_allocator = VTEPIPAllocator()
        # Controller state
        self.controller_state = controller_state
        # Overlay types
        self.overlay_type = dict()

       
    # Get a new table ID
    def get_new_tableid(self, overlay_name, tenantid):
        return self.tableid_allocator.get_new_tableid(overlay_name, tenantid)

    # Get table ID
    def get_tableid(self, overlay_name, tenantid):
        return self.tableid_allocator.get_tableid(overlay_name, tenantid)

    # Release table ID
    def release_tableid(self, overlay_name, tenantid):
        return self.tableid_allocator.release_tableid(overlay_name, tenantid)

    # Get a new VNI
    def get_new_vni(self, overlay_name, tenantid):
        return self.vni_allocator.get_new_vni(overlay_name, tenantid)

    # Get a VNI
    def get_vni(self, overlay_name, tenantid):
        return self.vni_allocator.get_vni(overlay_name, tenantid)
    
    # Release VNI
    def release_vni(self, overlay_name, tenantid):
        return self.vni_allocator.release_vni(overlay_name, tenantid)

    # Get a new VTEP IP 
    def get_new_vtep_ip(self, dev_id, tenantid):
        return self.vtep_ip_allocator.get_new_vtep_ip(dev_id, tenantid)
    
    # Get VTEP IP 
    def get_vtep_ip(self, dev_id, tenantid):
        return self.vtep_ip_allocator.get_vtep_ip(dev_id, tenantid)

    # Release VTEP IP 
    def release_vtep_ip(self, dev_id, tenantid):
        return self.vtep_ip_allocator.release_vtep_ip(dev_id, tenantid)

    

# VNI Allocator
class VNIAllocator:
    def __init__(self):
        client = srv6_sdn_controller_state.get_mongodb_session()
        # Get the database
        db = client.EveryWan
        # Get the collections
        # Mapping overlay name to VNI 
        self.overlay_to_vni = db.overlay_to_vni
        # Set of reusable VNI
        self.reusable_vni = db.reusable_vni
        # Last used VNI 
        self.last_allocated_vni = db.last_allocated_vni

    # Allocate and return a new VNI for the overlay
    def get_new_vni(self, overlay_name, tenantid):
        if not self.overlay_to_vni.count_documents({'tenantid': tenantid}, limit=1):
            # Inizialize structure 
            self.reusable_vni.insert_one({'tenantid': tenantid, 'vni': []})
            self.last_allocated_vni.insert_one({'tenantid': tenantid, 'vni': -1})

        # Get new VNI
        if self.overlay_to_vni.count_documents({'tenantid': tenantid, 'overlay_name':overlay_name}, limit=1):
            # The overlay for that tenant already has an associeted VNI  
            return -1 
        else:
            # Check if a reusable VNI is available
            if not self.reusable_vni.find_one( { 'tenantid': tenantid, 'vni': { '$size': 0 } } ):
                #Pop vni from the array 
                vnis = self.reusable_vni.find_one({'tenantid': tenantid})['vni']
                vni = vnis.pop()
                self.reusable_vni.find_one_and_update({'tenantid': tenantid},{'$set': {'vni': vnis}})
            else:
                # If not, get a new VNI
                self.last_allocated_vni.update({ 'tenantid': tenantid }, {'$inc': {'vni': +1}})
                while self.last_allocated_vni.find_one({ 'tenantid': tenantid }, {'vni': 1})['vni'] in RESERVED_VNI:
                    # Skip reserved VNI
                    self.last_allocated_vni.update ({ 'tenantid': tenantid }, { '$inc': { 'vni': +1 }})
                
                vni = self.last_allocated_vni.find_one( { 'tenantid': tenantid }, { 'vni': 1 } )['vni']
            # Assign the VNI to the overlay name 
            self.overlay_to_vni.insert_one({
                'tenantid': tenantid,
                'overlay_name': overlay_name,
                'vni': vni   
                } 
            )
            # And return
            return vni

    # Return the VNI assigned to the VPN
    # If the VPN has no assigned VNI, return -1
    def get_vni(self, overlay_name, tenantid):
        if not self.overlay_to_vni.count_documents({'tenantid': tenantid, 'overlay_name': overlay_name}, limit=1):
            return -1
        else:
            return self.overlay_to_vni.find_one({ 'tenantid': tenantid, 'overlay_name': overlay_name }, {'vni': 1})['vni']

    # Release VNI and mark it as reusable
    def release_vni(self, overlay_name, tenantid):
        # Check if the overlay has an associated VNI
        if self.overlay_to_vni.count_documents({'tenantid': tenantid, 'overlay_name': overlay_name}, limit=1):
            # The overlay has an associated VNI
            vni = self.overlay_to_vni.find_one({ 'tenantid': tenantid, 'overlay_name': overlay_name }, {'vni': 1})['vni']
            # Unassign the VNI
            self.overlay_to_vni.delete_one({ 'tenantid': tenantid, 'overlay_name': overlay_name })
            # Mark the VNI as reusable
            self.reusable_vni.update_one({'tenantid': tenantid}, {'$push':{'vni': vni}})
            # If the tenant has no overlays,
            # destory data structures
            if self.overlay_to_vni.count_documents({'tenantid': tenantid}) == 0:
                self.last_allocated_vni.delete_one({'tenantid': tenantid})
                self.reusable_vni.delete_one({'tenantid': tenantid})
            # Return the VNI
            return vni
        else:
            # The overlay has not associated VNI
            return -1

class VTEPIPAllocator:
    def __init__(self):
        # Get the collections
        client = srv6_sdn_controller_state.get_mongodb_session()
        # Get the database
        db = client.EveryWan
        # Mapping ID dev to VTEP ip 
        self.dev_to_ip = db.dev_to_ip
        # Set of reusable IP address 
        self.reusable_ip = db.reusable_ip
        # Last used VNI 
        self.last_allocated_ip = db.last_allocated_ip
        
        #ip address availale 
        self.ip = IPv4Network('198.18.0.0/16')
        self.network_mask = 16

    def get_new_vtep_ip(self, dev_id, tenantid):
        # check if the device does not already have a VTEP IP adress
        if not self.dev_to_ip.count_documents({'tenantid': tenantid}, limit=1):
            # Inizialize data sructures 
            self.reusable_ip.insert_one({'tenantid': tenantid, 'vtep_ips': []})
            self.last_allocated_ip.insert_one({'tenantid': tenantid, 'ip_index': -1})

        if self.dev_to_ip.count_documents({'tenantid': tenantid, 'dev_id': dev_id}, limit=1):
            # The device of the considered tenant already has an associated VTEP IP
            return -1
        else:
            # Check if a reusable VTEP IP is available
            if not self.reusable_ip.find_one({ 'tenantid': tenantid, 'vtep_ips': { '$size': 0 }}):
                #Pop VTEP IP adress from the array 
                vtep_ips = self.reusable_ip.find_one({'tenantid': tenantid})['vtep_ips']
                vtep_ip = vtep_ips.pop()
                self.reusable_ip.find_one_and_update({'tenantid': tenantid},{'$set': {'vtep_ips': vtep_ips}})
            else:
                # If not, get a VTEP IP address
                self.last_allocated_ip.update({ 'tenantid': tenantid }, {'$inc':{'ip_index': +1}})
                while self.last_allocated_ip.find_one({ 'tenantid': tenantid }, {'ip_index': 1})['ip_index'] in RESERVED_VTEP_IP:
                    # Skip reserved VTEP IP address
                    self.last_allocated_ip.update({ 'tenantid': tenantid }, {'$inc':{'ip_index': +1}})

                ip_index = self.last_allocated_ip.find_one( { 'tenantid': tenantid }, { 'ip_index': 1 } )['ip_index']
                vtep_ip = "%s/%s" % (self.ip[ip_index], self.network_mask) 
            # Assign the VTEP IP to the device 
            self.dev_to_ip.insert_one({
                'tenantid': tenantid,
                'dev_id': dev_id,
                'vtep_ip': vtep_ip   
                } 
            )
            # And return
            return vtep_ip

    # Return VTEP IP adress assigned to the device 
    # If device has no VTEP IP address return -1
    def get_vtep_ip(self, dev_id, tenantid):
        if not self.dev_to_ip.count_documents({'tenantid': tenantid, 'dev_id': dev_id}, limit=1):
            return -1
        else:
            return self.dev_to_ip.find_one({ 'tenantid': tenantid, 'dev_id': dev_id }, {'vtep_ip': 1})['vtep_ip']

    # Release VTEP IP and mark it as reusable
    def release_vtep_ip(self, dev_id, tenantid):
        # Check if the device has an associated VTEP IP 
        if self.dev_to_ip.count_documents({'tenantid': tenantid, 'dev_id': dev_id}, limit=1):
            # The device has an associated VTEP IP
            vtep_ip = self.dev_to_ip.find_one({ 'tenantid': tenantid, 'dev_id': dev_id }, {'vtep_ip': 1})['vtep_ip']
            # Unassign the VTEP IP
            self.dev_to_ip.delete_one({ 'tenantid': tenantid, 'dev_id': dev_id })
            # Mark the VTEP IP as reusable
            self.reusable_ip.update_one({'tenantid': tenantid}, {'$push':{'vtep_ips': vtep_ip}})
            # If the tenant has no VTEPs
            # destroy data structues
            if self.dev_to_ip.count_documents({'tenantid': tenantid}) == 0:
                self.last_allocated_ip.delete_one({'tenantid': tenantid})
                self.reusable_ip.delete_one({'tenantid': tenantid})
            # Return the VTEP IP 
            return vtep_ip
        else:
            # The device has no associeted VTEP IP
            return -1       

if __name__ == "__main__":

    #TableIDAllocator = ControllerStateVXLAN()
    #TableIDAllocator.get_new_tableid('ov3', 11)
    #TableIDAllocator.get_new_tableid('ov3', 12)
    #print('%s' %TableIDAllocator.get_tableid('ov3', 12))

    '''VNIAllocator = VNIAllocator()
    VNIAllocator.get_new_vni('ov1', 10)
    VNIAllocator.get_new_vni('ov2', 10)
    VNIAllocator.release_vni('ov1', 10)
    VNIAllocator.get_new_vni('ov3', 10)
    
    VNIAllocator.release_vni('ov2', 10)
    VNIAllocator.get_new_vni('ov4', 10)
 
    print('%s' % VNIAllocator.get_vni('ov3', 11))
    print('%s' % VNIAllocator.get_vni('ov3', 12))'''


    #print('%s' % VNIAllocator.get_new_vni('ov4', 11))
    #print('%s' % VNIAllocator.get_new_vni('ov2', 11))
    #print('%s' % VNIAllocator.get_new_vni('ov5', 10))

    '''VTEPIPAllocator = VTEPIPAllocator()
    VTEPIPAllocator.get_new_vtep_ip(1, 10)
    VTEPIPAllocator.get_new_vtep_ip(2, 10)
    VTEPIPAllocator.release_vtep_ip(1, 10)
    VTEPIPAllocator.get_new_vtep_ip(3, 10)

    VTEPIPAllocator.get_new_vtep_ip(1, 11)
    VTEPIPAllocator.get_new_vtep_ip(2, 11)
    VTEPIPAllocator.release_vtep_ip(1, 11)
    VTEPIPAllocator.get_new_vtep_ip(3, 11)

    print('%s' % VTEPIPAllocator.get_vtep_ip(3, 11))
    print('%s' % VTEPIPAllocator.get_vtep_ip(4, 11))'''

    #print('%s' % VTEPIPAllocator.get_new_vtep_ip(2, 11))
    