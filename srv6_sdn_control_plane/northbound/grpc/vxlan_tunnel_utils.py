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

from srv6_sdn_control_plane import srv6_controller_utils
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
        self.tableid_allocator = srv6_controller_utils.SDWANControllerState(
            '', '', '', '')
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
        return self.tableid_allocator.tableid_allocator.get_new_tableid(overlay_name, tenantid)

    # Get table ID
    def get_tableid(self, overlay_name, tenantid):
        return self.tableid_allocator.tableid_allocator.get_tableid(overlay_name, tenantid)

    # Release table ID
    def release_tableid(self, overlay_name, tenantid):
        return self.tableid_allocator.tableid_allocator.release_tableid(overlay_name, tenantid)

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
        # Get overlays collection
        self.overlays = db.overlays
        # Get tenants collection
        self.tenants = db.tenants

    # Allocate and return a new VNI for the overlay
    def get_new_vni(self, overlay_name, tenantid):
        # The overlay of the considered tenant already has a VNI
        if self.overlays.find_one({'name': overlay_name, 'tenantid': tenantid}, {'vni': 1})['vni'] != None:
            return -1
        # Overlay does not have a VNI
        else:
            # Check if a reusable VNI is available
            if not self.tenants.find_one({'tenantid': tenantid, 'reu_vni': {'$size': 0}}):
                # Pop vni from the array
                vnis = self.tenants.find_one({
                    'tenantid': tenantid})['reu_vni']
                vni = vnis.pop()
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$set': {'reu_vni': vnis}})
            else:
                # If not, get a new VNI
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$inc': {'vni_index': +1}})
                while self.tenants.find_one({'tenantid': tenantid}, {'vni_index': 1})['vni_index'] in RESERVED_VNI:
                    # Skip reserved VNI
                    self.tenants.find_one_and_update({
                        'tenantid': tenantid}, {'$inc': {'vni_index': +1}})
                # Get VNI
                vni = self.tenants.find_one({
                    'tenantid': tenantid}, {'vni_index': 1})['vni_index']
            # Assign the VNI to the overlay
            self.overlays.find_one_and_update({
                'tenantid': tenantid,
                'name': overlay_name}, {
                '$set': {'vni': vni}
            }
            )
            # Increase assigned VNIs counter
            self.tenants.find_one_and_update({
                'tenantid': tenantid}, {'$inc': {'assigned_vni': +1}})
            # And return
            return vni

    # Return the VNI assigned to the Overlay
    # If the Overlay has no assigned VNI, return -1
    def get_vni(self, overlay_name, tenantid):
        vni = self.overlays.find_one({
            'name': overlay_name, 'tenantid': tenantid}, {'vni': 1})['vni']
        if vni == None:
            return -1
        else:
            return vni

    # Release VNI and mark it as reusable
    def release_vni(self, overlay_name, tenantid):
        # Check if the overlay has an associated VNI
        vni = self.overlays.find_one({
            'name': overlay_name, 'tenantid': tenantid}, {'vni': 1})['vni']
        # If VNI is valid
        if vni != None:
            # Unassign the VNI
            self.overlays.find_one_and_update({
                'tenantid': tenantid,
                'name': overlay_name}, {
                '$set': {'vni': None}
            }
            )
            # Decrease assigned VNIs counter
            self.tenants.find_one_and_update({
                'tenantid': tenantid}, {'$inc': {'assigned_vni': -1}})
            # Mark the VNI as reusable
            self.tenants.update_one({
                'tenantid': tenantid}, {'$push': {'reu_vni': vni}})
            # If the tenant has no overlays
            if self.tenants.find_one({'tenantid': tenantid}, {'assigned_vni': 1})['assigned_vni'] == 0:
                # reset counter
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$set': {'vni_index': -1}})
                # empty reusable VNI list
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$set': {'reu_vni': []}})
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
        # Devices collection
        self.devices = db.devices
        # Tenants collection
        self.tenants = db.tenants
        # ip address availale
        self.ip = IPv4Network('198.18.0.0/16')
        self.network_mask = 16

    def get_new_vtep_ip(self, dev_id, tenantid):
        # The device of the considered tenant already has an associated VTEP IP
        if self.devices.find_one({'deviceid': dev_id, 'tenantid': tenantid}, {'vtep_ip_addr': 1})['vtep_ip_addr'] != None:
            return -1
        # The device does not have a VTEP IP address
        else:
            # Check if a reusable VTEP IP is available
            if not self.tenants.find_one({'tenantid': tenantid, 'reu_vtep_ip_addr': {'$size': 0}}):
                # Pop VTEP IP adress from the array
                vtep_ips = self.tenants.find_one({
                    'tenantid': tenantid})['reu_vtep_ip_addr']
                vtep_ip = vtep_ips.pop()
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$set': {'reu_vtep_ip_addr': vtep_ips}})
            else:
                # If not, get a VTEP IP address
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$inc': {'vtep_ip_index': +1}})
                while self.tenants.find_one({'tenantid': tenantid}, {'vtep_ip_index': 1})['vtep_ip_index'] in RESERVED_VTEP_IP:
                    # Skip reserved VTEP IP address
                    self.tenants.find_one_and_update({
                        'tenantid': tenantid}, {'$inc': {'vtep_ip_index': +1}})
                # Get IP address
                ip_index = self.tenants.find_one({
                    'tenantid': tenantid}, {'vtep_ip_index': 1})['vtep_ip_index']
                vtep_ip = "%s/%s" % (self.ip[ip_index], self.network_mask)
            # Assign the VTEP IP address to the device
            self.devices.find_one_and_update({
                'tenantid': tenantid,
                'deviceid': dev_id}, {
                '$set': {'vtep_ip_addr': vtep_ip}
            }
            )
            # Increase assigned VTEP IP addr counter
            self.tenants.find_one_and_update({
                'tenantid': tenantid}, {'$inc': {'assigned_vtep_ip_addr': +1}})
            # And return
            return vtep_ip

    # Return VTEP IP adress assigned to the device
    # If device has no VTEP IP address return -1
    def get_vtep_ip(self, dev_id, tenantid):
        # if not self.dev_to_ip.count_documents({'tenantid': tenantid, 'dev_id': dev_id}, limit=1):
        vtep_ip = self.devices.find_one({
            'deviceid': dev_id, 'tenantid': tenantid}, {'vtep_ip_addr': 1})['vtep_ip_addr']
        if vtep_ip == None:
            return -1
        else:
            return vtep_ip

    # Release VTEP IP and mark it as reusable
    def release_vtep_ip(self, dev_id, tenantid):
        # Get device VTEP IP address
        vtep_ip = self.devices.find_one({
            'deviceid': dev_id, 'tenantid': tenantid}, {'vtep_ip_addr': 1})['vtep_ip_addr']
        # If IP address is valid
        if vtep_ip != None:
            # Unassign the VTEP IP addr
            self.devices.find_one_and_update({
                'tenantid': tenantid,
                'deviceid': dev_id}, {
                '$set': {'vtep_ip_addr': None}
            }
            )
            # Decrease assigned VTEP IP addr counter
            self.tenants.find_one_and_update({
                'tenantid': tenantid}, {'$inc': {'assigned_vtep_ip_addr': -1}})
            # Mark the VTEP IP addr as reusable
            self.tenants.update_one({
                'tenantid': tenantid}, {'$push': {'reu_vtep_ip_addr': vtep_ip}})
            # If all addresses have been released
            if self.tenants.find_one({'tenantid': tenantid}, {'assigned_vtep_ip_addr': 1})['assigned_vtep_ip_addr'] == 0:
                # reset the counter
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$set': {'vtep_ip_index': -1}})
                # empty reusable address list
                self.tenants.find_one_and_update({
                    'tenantid': tenantid}, {'$set': {'reu_vtep_ip_addr': []}})
            # Return the VTEP IP
            return vtep_ip
        else:
            # The device has no associeted VTEP IP
            return -1
