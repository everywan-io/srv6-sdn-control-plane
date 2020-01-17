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
# SRv6 dependencies
from srv6_sdn_control_plane.northbound.grpc import nb_grpc_utils

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

RESERVED_VNI = [0, 1, 2, 3, 4, 5]
RESERVED_VTEP_IP = [0, 65536]

class ControllerStateVXLAN:
    """This class maintains the state of the SRv6 controller and provides some
       methods to handle it
    """

    def __init__(self, controller_state):
        # Create Table IDs allocator
        self.tableid_allocator = TableIDAllocator()
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
    def get_new_tableid(self, overlay_name):
        return self.tableid_allocator.get_new_tableid(overlay_name)

    # Get table ID
    def get_tableid(self, overlay_name):
        return self.tableid_allocator.get_tableid(overlay_name)

    # Release table ID
    def release_tableid(self, overlay_name):
        return self.tableid_allocator.release_tableid(overlay_name)

    # Get a new VNI
    def get_new_vni(self, overlay_name):
        return self.vni_allocator.get_new_vni(overlay_name)

    # Get a VNI
    def get_vni(self, overlay_name):
        return self.vni_allocator.get_vni(overlay_name)
    
    # Release VNI
    def release_vni(self, overlay_name):
        return self.vni_allocator.release_vni(overlay_name)

    # Get a new VTEP IP 
    def get_new_vtep_ip(self, dev_id):
        return self.vtep_ip_allocator.get_new_vtep_ip(dev_id)
    
    # Get VTEP IP 
    def get_vtep_ip(self, dev_id):
        return self.vtep_ip_allocator.get_vtep_ip(dev_id)

    # Release VTEP IP 
    def release_vtep_ip(self, dev_id):
        return self.vtep_ip_allocator.release_vtep_ip(dev_id)

    

# VNI Allocator
class VNIAllocator:
    def __init__(self):
        # Mapping overlay name to VNI 
        self.overlay_to_vni = dict()
        # Set of reusable VNI
        self.reusable_vni = set()
        # Last used VNI 
        self.last_allocated_vni = -1

    # Allocate and return a new VNI for the overlay
    def get_new_vni(self, overlay_name):
        if self.overlay_to_vni.get((overlay_name)):
            # The VPN already has an associated VNI
            return -1
        else:
            # Check if a reusable VNI is available
            if self.reusable_vni:
                vni = self.reusable_vni.pop()
            else:
                # If not, get a new VNI
                self.last_allocated_vni += 1
                while self.last_allocated_vni in RESERVED_VNI:
                    # Skip reserved VNI
                    self.last_allocated_vni += 1
                vni = self.last_allocated_vni
            # Assign the VNI to the overlay name 
            self.overlay_to_vni[(overlay_name)] = vni
            # And return
            return vni


    # Return the VNI assigned to the VPN
    # If the VPN has no assigned VNI, return -1
    def get_vni(self, overlay_name):
        return self.overlay_to_vni.get((overlay_name), -1)

    # Release VNI and mark it as reusable
    def release_vni(self, overlay_name):
        # Check if the overlay has an associated VNI
        if self.overlay_to_vni.get((overlay_name)):
            # The overlay has an associated VNI
            vni = self.overlay_to_vni[(overlay_name)]
            # Unassign the VNI
            del self.overlay_to_vni[(overlay_name)]
            # Mark the VNI as reusable
            self.reusable_vni.add(vni)
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
        self.reusable_ip = set()
        # Last used VNI 
        self.last_allocated_ip = -1
        #ip address availale 
        self.ip = IPv4Network('198.18.0.0/16')
    
    def get_new_vtep_ip(self, dev_id):

        if self.dev_to_ip.get((dev_id)):
            # The device already has an associated VTEP IP
            return -1
        else:
            # Check if a reusable VTEP IP is available
            if self.reusable_ip:
                vtep_ip = self.reusable_ip.pop()
            else:
                # If not, get a VTEP IP
                self.last_allocated_ip += 1
                while self.last_allocated_ip in RESERVED_VTEP_IP:
                    # Skip reserved VTEP IP
                    self.last_allocated_ip += 1
                vtep_ip = "%s/%s" %(self.ip[self.last_allocated_ip], 16) 
            # Assign the VTEP IP to the device 
            self.dev_to_ip[(dev_id)] = vtep_ip
            # And return
            return vtep_ip

    # Return VTEP IP adress assigned to the device 
    def get_vtep_ip(self, dev_id):
        return self.dev_to_ip.get((dev_id), -1)

    # Release VTEP IP and mark it as reusable
    def release_vtep_ip(self, dev_id):
        # Check if the device has an associated VTEP IP 
        if self.dev_to_ip.get((dev_id)):
            # The device has an associated VTEP IP
            vtep_ip = self.dev_to_ip[(dev_id)]
            # Unassign the VTEP IP
            del self.dev_to_ip[(dev_id)]
            # Mark the VTEP IP as reusable
            self.reusable_ip.add(vtep_ip)
            # Return the VTEP IP 
            return vtep_ip
        else:
            # The device has no associeted VTEP IP
            return -1

# todo: assigne table ID based on the overlay name and on the device ID
# Table ID Allocator
class TableIDAllocator:
    def __init__(self):
        # Mapping overaly name and device ID to table ID
        self.overaly_deviceid_to_tableid = dict()
        # Set of reusable table IDs
        self.reusable_tableids = set()
        # Last used table ID
        self.last_allocated_tableid = -1

    # Allocate and return a new table ID for a VPN
    def get_new_tableid(self, overlay_name):
        if self.overaly_deviceid_to_tableid.get((overlay_name)):
            # The VPN already has an associated table ID
            return -1
        else:
            
            # Check if a reusable table ID is available
            if self.reusable_tableids:
                tableid = self.reusable_tableids.pop()
            else:
                # If not, get a new table ID
                self.last_allocated_tableid += 1
                while self.last_allocated_tableid in RESERVED_TABLEIDS:
                    # Skip reserved table IDs
                    self.last_allocated_tableid += 1
                tableid = self.last_allocated_tableid
            # Assign the table ID to the overlay name and device id 
            self.overaly_deviceid_to_tableid[(overlay_name)] = tableid
            # And return
            return tableid

    # Return the table ID 
    # If no table ID associeted, return -1
    def get_tableid(self, overlay_name):
        return self.overaly_deviceid_to_tableid.get((overlay_name), -1)

    # Release a table ID and mark it as reusable
    def release_tableid(self, overlay_name):
        # Check if the overlay name and table id have an associeted table ID
        if self.overaly_deviceid_to_tableid.get((overlay_name)):
            # There is associated table ID
            tableid = self.overaly_deviceid_to_tableid[(overlay_name)]
            # Unassign the table ID
            del self.overaly_deviceid_to_tableid[(overlay_name)]
            # Mark the table ID as reusable
            self.reusable_tableids.add(tableid)
            # Return the table ID
            return tableid
        else:
            # The VPN has not an associated table ID
            return -1
       

if __name__ == "__main__":
    ''''TableIDAllocator = TableIDAllocator()
    TableIDAllocator.get_new_tableid('ov3', 11)
    TableIDAllocator.get_new_tableid('ov3', 12)
    print('%s' %TableIDAllocator.get_tableid('ov3', 12))'''

    '''VNIAllocator = VNIAllocator()
    VNIAllocator.get_new_vni('ov1')
    VNIAllocator.get_new_vni('ov2')
    VNIAllocator.release_vni('ov1')
    VNIAllocator.get_new_vni('ov3')'''
    
    '''VTEPIPAllocator = VTEPIPAllocator()
    VTEPIPAllocator.get_new_vtep_ip(1)
    VTEPIPAllocator.get_new_vtep_ip(2)
    VTEPIPAllocator.release_vtep_ip(1)
    VTEPIPAllocator.get_new_vtep_ip(3)
    VTEPIPAllocator.get_new_vtep_ip(4)
    print('%s' %VTEPIPAllocator.get_vtep_ip(2))'''
    