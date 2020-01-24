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
# ipaddress dependencies
from ipaddress import IPv4Interface
from ipaddress import IPv6Interface
from ipaddress import AddressValueError
from ipaddress import IPv4Network
# NetworkX dependencies
import networkx as nx
from networkx.readwrite import json_graph

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

# SRv6 dependencies
from srv6_generators import SIDAllocator

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
        # Slice in overlay per site  
        self.slice_in_overlay = dict()
       
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
        # Mapping overlay name to VNI 
        self.overlay_to_vni = dict()
        # Set of reusable VNI
        self.reusable_vni = dict()
        # Last used VNI 
        self.last_allocated_vni = dict()

    # Allocate and return a new VNI for the overlay
    def get_new_vni(self, overlay_name, tenantid):
        if tenantid not in self.overlay_to_vni:
            # Inizialize structure 
            self.overlay_to_vni[tenantid] = dict()
            self.reusable_vni[tenantid] = set()
            self.last_allocated_vni[tenantid] = -1 
        # Get new VNI
        if self.overlay_to_vni[tenantid].get(overlay_name):
            # The overlay for that tenant already has an associeted VNI  
            return -1 
        else:
            # Check if a reusable VNI is available
            if self.reusable_vni[tenantid]:
                vni = self.reusable_vni[tenantid].pop()
            else:
                # If not, get a new VNI
                self.last_allocated_vni[tenantid] += 1
                while self.last_allocated_vni[tenantid] in RESERVED_VNI:
                    # Skip reserved VNI
                    self.last_allocated_vni[tenantid] += 1
                vni = self.last_allocated_vni[tenantid]
            # Assign the VNI to the overlay name 
            self.overlay_to_vni[tenantid][overlay_name] = vni
            # And return
            return vni


    # Return the VNI assigned to the VPN
    # If the VPN has no assigned VNI, return -1
    def get_vni(self, overlay_name, tenantid):
        if tenantid not in self.overlay_to_vni:
            return -1
        return self.overlay_to_vni[tenantid].get(overlay_name, -1)

    # Release VNI and mark it as reusable
    def release_vni(self, overlay_name, tenantid):
        # Check if the overlay has an associated VNI
        if self.overlay_to_vni[tenantid].get((overlay_name)):
            # The overlay has an associated VNI
            vni = self.overlay_to_vni[tenantid][overlay_name]
            # Unassign the VNI
            del self.overlay_to_vni[tenantid][overlay_name]
            # Mark the VNI as reusable
            self.reusable_vni[tenantid].add(vni)
            # If the tenant has no overlays,
            # destory data structures
            if len(self.overlay_to_vni[tenantid]) == 0:
                del self.overlay_to_vni[tenantid]
                del self.reusable_vni[tenantid]
                del self.last_allocated_vni[tenantid]
            # Return the VNI
            return vni
        else:
            # The overlay has not associated VNI
            return -1

class VTEPIPAllocator:
    def __init__(self):
        # Mapping ID dev to VTEP ip 
        self.dev_to_ip = dict()
        # Set of reusable IP address 
        self.reusable_ip = dict()
        # Last used VNI 
        self.last_allocated_ip = dict()
        #ip address availale 
        self.ip = IPv4Network('198.18.0.0/16')
    
    def get_new_vtep_ip(self, dev_id, tenantid):
        if tenantid not in self.dev_to_ip:
            # Inizialize data sructures 
            self.dev_to_ip[tenantid] = dict()
            self.reusable_ip[tenantid] = set()
            self.last_allocated_ip[tenantid] = -1
        if self.dev_to_ip[tenantid].get(dev_id):
            # The device of the considered tenant already has an associated VTEP IP
            return -1
        else:
            # Check if a reusable VTEP IP is available
            if self.reusable_ip[tenantid]:
                vtep_ip = self.reusable_ip[tenantid].pop()
            else:
                # If not, get a VTEP IP
                self.last_allocated_ip[tenantid] += 1
                while self.last_allocated_ip[tenantid] in RESERVED_VTEP_IP:
                    # Skip reserved VTEP IP
                    self.last_allocated_ip[tenantid] += 1
                vtep_ip = "%s/%s" % (self.ip[self.last_allocated_ip[tenantid]], 16) 
            # Assign the VTEP IP to the device 
            self.dev_to_ip[tenantid][dev_id] = vtep_ip
            # And return
            return vtep_ip

    # Return VTEP IP adress assigned to the device 
    # If device has no VTEP IP address return -1
    def get_vtep_ip(self, dev_id, tenantid):
        if tenantid not in self.dev_to_ip:
            return -1
        return self.dev_to_ip[tenantid].get(dev_id, -1)

    # Release VTEP IP and mark it as reusable
    def release_vtep_ip(self, dev_id, tenantid):
        # Check if the device has an associated VTEP IP 
        if self.dev_to_ip[tenantid].get(dev_id):
            # The device has an associated VTEP IP
            vtep_ip = self.dev_to_ip[tenantid][dev_id]
            # Unassign the VTEP IP
            del self.dev_to_ip[tenantid][dev_id]
            # Mark the VTEP IP as reusable
            self.reusable_ip[tenantid].add(vtep_ip)
            # If the tenant has no VTEPs
            # destroy data structues
            if len(self.dev_to_ip[tenantid]) == 0:
                del self.dev_to_ip[tenantid]
                del self.reusable_ip[tenantid]
                del self.last_allocated_ip[tenantid]
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

    #VNIAllocator = VNIAllocator()
    #VNIAllocator.get_new_vni('ov1', 10)
    #VNIAllocator.get_new_vni('ov4', 11)

    #print('%s' % VNIAllocator.get_vni('ov4', 11))

    '''VTEPIPAllocator = VTEPIPAllocator()
    VTEPIPAllocator.get_new_vtep_ip(1, 10)
    VTEPIPAllocator.get_new_vtep_ip(2, 11)
    VTEPIPAllocator.release_vtep_ip(1, 10)
    VTEPIPAllocator.get_new_vtep_ip(2, 11)

    print('%s' % VTEPIPAllocator.get_new_vtep_ip(2, 11))'''
    