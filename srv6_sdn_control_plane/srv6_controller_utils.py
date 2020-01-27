#!/usr/bin/python



# General imports
from __future__ import absolute_import, division, print_function
from srv6_generators import SIDAllocator
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
from ipaddress import IPv4Interface, IPv6Interface
from ipaddress import IPv4Network, IPv6Network
from ipaddress import IPv4Address
from ipaddress import AddressValueError
# NetworkX dependencies
import networkx as nx
from networkx.readwrite import json_graph
# ipaddress dependencies
from ipaddress import IPv6Interface
from ipaddress import IPv6Network
from ipaddress import IPv4Address




ZEBRA_PORT = 2601
SSH_PORT = 22

MIN_TABLE_ID = 2
# Linux kernel supports up to 255 different tables
MAX_TABLE_ID = 255
# Table where we store our seg6local routes
LOCAL_SID_TABLE = 1
# Reserved table IDs
RESERVED_TABLEIDS = [0, 253, 254, 255]
RESERVED_TABLEIDS.append(LOCAL_SID_TABLE)

RESERVED_TENANTIDS = [0]

WAIT_TOPOLOGY_INTERVAL = 1


# Logger reference
logger = logging.getLogger(__name__)


# Initialize random seed
random.seed(time.time())


class InterfaceType:
    UNKNOWN = 'unknown'
    WAN = 'wan'
    LAN = 'lan'


class DeviceStatus:
    NOT_CONNECTED = 'Not Connected'
    CONNECTED = 'Connected'
    RUNNING = 'Running'


class SDWANControllerState:

    def __init__(self, topology, devices, vpn_dict, vpn_file):
        # Topology graph
        self.topology = topology
        # Devices
        self.devices = devices
        # VPN file
        self.vpn_file = vpn_file
        # VPNs dict
        self.vpns = vpn_dict
        # Map tokne to tenant ID
        self.tenant_info = dict()
        
        # Keep track of how many VPNs are installed in each router
        #self.num_vpn_installed_on_router = dict()
        # Number of tunneled interfaces
        #self.num_tunneled_interfaces = dict()
        # Table ID allocator
        self.tableid_allocator = TableIDAllocator()
        # Tenant ID allocator
        self.tenantid_allocator = TenantIDAllocator()

        self.interfaces_in_overlay = dict()
        # Mapping tenant ID to overlays
        self.tenantid_to_overlays = dict()
        # Mapping tenant ID to devices
        self.tenantid_to_devices = dict()
        # Initiated tunnels
        #self.initiated_tunnels = dict()

        # If VPN dumping is enabled, import the VPNs from the dump
        '''
        if vpn_file is not None:
            try:
                self.import_vpns_from_dump()
            except:
                print('Corrupted VPN file')
        '''

    # Get new tenant ID
    def get_new_tenantid(self, token):
        tenantid = self.tenantid_allocator.get_new_tenantid(token)
        self.tenantid_to_devices[tenantid] = set()
        self.tenantid_to_overlays[tenantid] = set()
        return tenantid

    # Get tenant ID
    def get_tenantid(self, token):
        return self.tenantid_allocator.get_tenantid(token)

    # Release tenant ID
    def release_tenantid(self, token):
        tenantid = self.tenantid_allocator.release_tenantid(token)
        del self.tenantid_to_devices[tenantid]
        del self.tenantid_to_overlays[tenantid]
        return tenantid

    # Return the tenant ID
    def deviceid_to_tenantid(self, deviceid):
        return self.devices[deviceid]['tenantid']

    # Return the devices belonging a tenant
    def tenantid_to_devices(self, tenantid):
        return self.tenantid_to_devices[tenantid]

    # Return the overlays belonging a tenant
    def tenantid_to_overlays(self, tenantid):
        return self.tenantid_to_overlays[tenantid]

    # Return True if the VPN exists, False otherwise
    def vpn_exists(self, vpn_name):
        if self.vpns.get(vpn_name) is not None:
            # The VPN exists
            return True
        else:
            # The VPN does not exist
            return False
    '''
    # Return True if the router exists, False otherwise
    def router_exists(self, routerid):
        if self.topology.has_node(routerid):
            # Found router ID
            return True
        else:
            # The router ID has not been found
            return False
    '''

    # Return True if the router exists, False otherwise
    def router_exists(self, routerid):
        #routerid = int(IPv4Address(routerid))
        if routerid in self.devices:
            # Found router ID
            return True
        else:
            # The router ID has not been found
            return False

    '''
    # Return True if the specified interface exists
    def interface_exists(self, interface_name, routerid):
        router = self.topology.node[routerid]
        if router is None or router['interfaces'] is None:
            return False
        interface_names = []
        for interface in router['interfaces'].values():
            interface_names.append(interface['ifname'])
        if interface_name in interface_names:
            # The interface exists
            return True
        else:
            # The interface does not exist
            return False
    '''

    # Return True if the specified interface exists
    def interface_exists(self, interface_name, routerid):
        #routerid = int(IPv4Address(routerid))
        if routerid not in self.devices or self.devices[routerid].get('interfaces') is None:
            return False
        if interface_name in self.devices[routerid]['interfaces']:
            # The interface exists
            return True
        else:
            # The interface does not exist
            return False

    # Return True if the VPN is installed on the specified router,
    # False otherwise
    def is_vpn_installed_on_router(self, vpn_name, routerid):
        if self.vpn_exists(vpn_name):
            if routerid in self.vpns[vpn_name].interfaces:
                # The VPN is configured in the router
                return True
        # The VPN is not configured in the router
        return False

    # Return the number of the VPNs installed in the router
    def get_num_vpn_installed_on_router(self, routerid):
        return self.num_vpn_installed_on_router.get(routerid, 0)

    # Return True if the interface is assigned to the VPN, False otherwise
    def interface_in_vpn(self, routerid, interface_name, vpn_name):
        if self.vpns.get(vpn_name) is not None:
            for interface in self.vpns[vpn_name].interfaces:
                if interface.routerid == routerid and interface.interface_name == interface_name:
                    # The interface is assigned to the VPN
                    return True
        # The interface is not assigned to the VPN
        return False

    # Return True if the interface is assigned to any VPN, False otherwise
    def interface_in_any_vpn(self, routerid, ifname):
        for vpn_name in self.vpns:
            for interface in self.vpns[vpn_name].interfaces:
                if interface.routerid == routerid and interface.interface_name == ifname:
                    # The interface is assigned to the VPN
                    return True
        # The interface is not assigned to the VPN
        return False

    # Get router's loopback IP address
    def get_loopbackip_ipv4(self, routerid):
        return self.devices[routerid]['interfaces']['lo']['ipv4_addrs'][0]

    # Get router's loopback IP address
    def get_loopbacknet_ipv4(self, routerid):
        loopbackip = self.devices[routerid]['interfaces']['lo']['ipv4_addrs'][0]
        return IPv4Interface(loopbackip).network.__str__()

    # Get router's loopback IP address
    def get_loopbackip_ipv6(self, routerid):
        return self.devices[routerid]['interfaces']['lo']['ipv6_addrs'][0]

    # Get router's loopback IP address
    def get_loopbacknet_ipv6(self, routerid):
        loopbackip = self.devices[routerid]['interfaces']['lo']['ipv6_addrs'][0]
        return IPv6Interface(loopbackip).network.__str__()

    '''
    # Get router's loopback IP address
    def get_loopbackip(self, routerid):
        return self.topology.node[routerid]['loopbackip']

    # Get router's management IP address
    def get_managementip(self, routerid):
        return self.topology.node[routerid]['managementip']
    '''

    # Get router's management IP address
    def get_router_mgmtip(self, routerid):
        #routerid = int(IPv4Address(routerid))
        return self.devices[routerid]['mgmtip']

    '''
    # Get router address
    def get_router_address(self, routerid):
        if self.use_mgmt_ip:
            return self.get_managementip(routerid)
        else:
            return self.get_loopbackip(routerid)
    '''

    '''
    # Get random router interface
    def get_random_interface(self, routerid):
        router_info = self.topology.node[routerid]
        return random.choice(list(router_info['interfaces'].values()))['ifname']

    # Get first router interface
    def get_first_interface(self, routerid):
        interfaces = list()
        router_info = self.topology.node[routerid]
        for interface in router_info['interfaces'].values():
            interfaces.append(interface['ifname'])
        interfaces.sort()
        return interfaces[0]
    '''

    def get_loopback_ip(self, routerid):
        #routerid = int(IPv4Address(routerid))
        return self.devices[routerid]['interfaces']['lo']['addr']

    # Get random router interface
    def get_wan_interface(self, routerid):
        #routerid = int(IPv4Address(routerid))
        interfaces = self.devices[routerid]['interfaces']
        for ifname, ifinfo in interfaces.items():
            # Skip loopback interfaces
            if ifinfo['type'] == InterfaceType.WAN:
                return ifname
        # No non-loopback interfaces
        return None

    # Get random router interface
    def get_non_loopback_interface(self, routerid):
        #routerid = int(IPv4Address(routerid))
        interfaces = self.devices[routerid]['interfaces']
        for interface in interfaces.values():
            # Skip loopback interfaces
            if interface['name'] != 'lo':
                return interface['name']
        # No non-loopback interfaces
        return None

    # Add a router to a VPN and increase the number of VPNs installed on a
    # router
    def add_router_to_vpn(self, routerid, vpn_name):
        # If the VPN does not exist, return False
        if vpn_name not in self.vpns:
            return False
        # Increase the number of VPNs installed on the router
        num_of_vpns = self.get_num_vpn_installed_on_router(routerid)
        self.num_vpn_installed_on_router[routerid] = num_of_vpns + 1
        # Add the router to the VPN
        self.vpns[vpn_name].interfaces[routerid] = dict()
        return True

    # Remove a VPN from a router and
    # decrease the number of VPNs installed on a router
    def remove_vpn_from_router(self, vpn_name, routerid):
        # Remove the VPN from the VPNs dict, if it has no more interfaces
        if len(self.vpns[vpn_name].interfaces[routerid]) == 0:
            del self.vpns[vpn_name].interfaces[routerid]
            # Update the number of VPNs installed on the router
            num_of_vpns = self.get_num_vpn_installed_on_router(routerid)
            self.num_vpn_installed_on_router[routerid] = num_of_vpns - 1
            return True
        return False

    # Remove a VPN
    def remove_vpn(self, vpn_name):
        # Remove the VPN from the VPNs dict
        if vpn_name not in self.vpns:
            return False
        del self.vpns[vpn_name]
        return True

    # Return VPN type
    def get_vpn_type(self, vpn_name):
        if vpn_name not in self.vpns:
            return None
        return self.vpns[vpn_name].vpn_type

    # Return VPN type
    # def get_vpn_tableid(self, vpn_name):
    #    print(self.vpns)
    #    if vpn_name not in self.vpns:
    #        return None
    #    return self.vpns[vpn_name].tableid

    # Return SID
    # def get_sid(self, routerid, tableid):
    #    return self.sid_allocator.getSID(routerid, tableid)

    # Return SID
    # def get_sid_family(self, routerid):
    #    return self.sid_allocator.getSIDFamily(routerid)

    # Return VPN interfaces
    def get_vpn_interfaces(self, vpn_name, routerid=None):
        if self.vpns.get(vpn_name) is None:
            return None
        interfaces = list()
        for _interfaces in self.vpns[vpn_name].interfaces.values():
            for _interface in _interfaces.values():
                if routerid is not None and _interface.routerid != routerid:
                    continue
                interfaces.append(_interface)
        return interfaces

    # Return VPN interfaces
    def get_vpn_interface_names(self, vpn_name, routerid=None):
        # if self.vpns.get(vpn_name) is None:
        #    return None
        interfaces = set()
        if self.vpns.get(vpn_name) is None:
            return interfaces
        for _interfaces in self.vpns[vpn_name].interfaces.values():
            for _interface in _interfaces.values():
                if routerid is not None and _interface.routerid != routerid:
                    continue
                interfaces.add(_interface.interface_name)
        return interfaces

    # Add an interface to a VPN
    # def add_interface_to_vpn(self, vpn_name, routerid, interface_name,
    #                         interface_ip, vpn_prefix):
    #    self.vpns[vpn_name].interfaces[routerid][interface_name] = Interface(
    #        routerid, interface_name, interface_ip, vpn_prefix
    #    )

    # Return VPN prefix assigned to an interface
    # def get_vpn_prefix(self, vpn_name, routerid, interface_name):
    #    return self.vpns[vpn_name].interfaces[routerid][interface_name].vpn_prefix

    # Return VPN prefix assigned to an interface
    # def get_vpn_interface_ip(self, vpn_name, routerid, interface_name):
    #    return self.vpns[vpn_name].interfaces[routerid][interface_name].interface_ip

    # Remove an interface from a VPN
    def remove_interface_from_vpn(self, routerid, interface_name, vpn_name):
        return self.vpns[vpn_name].removeInterface(routerid, interface_name)

    # Return the number of the interface in the VPN
    def get_number_of_interfaces(self, vpn_name, routerid):
        return self.vpns[vpn_name].numberOfInterfaces(routerid)

    '''
    # Return the IP addresses associated to an interface
    def get_interface_ips(self, routerid, interface_name):
        for interface in self.topology.node[routerid]['interfaces'].values():
            if interface['ifname'] == interface_name:
                return interface['ipaddr']
        return None
    '''

    # Return true if the router is running
    def is_device_running(self, routerid):
        return self.devices[routerid]['status'] == DeviceStatus.RUNNING

    # Return the IP addresses associated to an interface
    def get_interface_ipv4(self, routerid, interface_name):
        return self.devices[routerid]['interfaces'][interface_name]['ipv4_addrs']

    # Return the IP addresses associated to an interface
    def get_interface_ipv6(self, routerid, interface_name):
        return self.devices[routerid]['interfaces'][interface_name]['ipv6_addrs']

    # Return the external IP addresses associated to an interface
    def get_external_ipv4(self, routerid, interface_name):
        addrs = self.devices[routerid]['interfaces'][interface_name]['ext_ipv4_addrs']
        if len(addrs) == 0:
            addrs = self.devices[routerid]['interfaces'][interface_name]['ipv4_addrs']
        return addrs

    # Return the external IP addresses associated to an interface
    def get_external_ipv6(self, routerid, interface_name):
        addrs = self.devices[routerid]['interfaces'][interface_name]['ext_ipv6_addrs']
        if len(addrs) == 0:
            addrs = self.devices[routerid]['interfaces'][interface_name]['ipv6_addrs']
        return addrs

    def get_ipv6_subnets_on_interface(self, routerid, interface_name):
        return self.devices[routerid]['interfaces'][interface_name]['ipv6_subnets']

    def get_ipv4_subnets_on_interface(self, routerid, interface_name):
        return self.devices[routerid]['interfaces'][interface_name]['ipv4_subnets']

    def get_subnets_on_interface(self, routerid, interface_name):
        return self.get_ipv6_subnets_on_interface(routerid, interface_name) + \
            self.get_ipv4_subnets_on_interface(routerid, interface_name)

    # Return the IP addresses associated to an interface
    def get_interface_ips(self, routerid, interface_name):
        return self.get_interface_ipv4(routerid, interface_name) + \
            self.get_interface_ipv6(routerid, interface_name)

    # Return the VPNs
    def get_vpns(self):
        return self.vpns.values()

    def get_routers_in_vpn(self, vpn_name):
        routers = set()
        for routerid in self.vpns[vpn_name].interfaces:
            routers.add(routerid)
        return routers

    def get_interfaces_in_vpn(self, vpn_name):
        return self.vpns[vpn_name].interfaces

    def add_tunnel_mode(self, tunnel_mode):
        self.interfaces_in_overlay[tunnel_mode] = dict()

    def init_tunnel_mode_on_device(self, tunnel_mode, deviceid):
        self.interfaces_in_overlay[tunnel_mode][deviceid] = dict()

    # def destroy_tunnel_mode_on_device(self, tunnel_mode, deviceid):
    #    self.interfaces_in_overlay[tunnel_mode].pop(deviceid, None)

    def is_tunnel_mode_initiated_on_device(self, tunnel_mode, deviceid):
        return deviceid in self.interfaces_in_overlay[tunnel_mode]

    def init_overlay_on_device(self, tunnel_mode, deviceid, overlay_name):
        self.interfaces_in_overlay[tunnel_mode][deviceid][overlay_name] = set()

    def destroy_overlay_on_device(self, tunnel_mode, deviceid, overlay_name):
        #self.interfaces_in_overlay[tunnel_mode][deviceid].pop(overlay_name, None)
        if len(self.interfaces_in_overlay[tunnel_mode][deviceid]) == 0:
            del self.interfaces_in_overlay[tunnel_mode][deviceid]

    def is_overlay_initiated_on_device(self, tunnel_mode, deviceid, overlay_name):
        return overlay_name in self.interfaces_in_overlay[tunnel_mode][deviceid]

    def add_interface_to_overlay(self, tunnel_mode, deviceid, overlay_name, interface):
        self.interfaces_in_overlay[tunnel_mode][deviceid][overlay_name].add(
            interface)

    def remove_interface_from_overlay(self, tunnel_mode, deviceid, overlay_name, interface):
        self.interfaces_in_overlay[tunnel_mode][deviceid][overlay_name].remove(
            interface)
        if len(self.interfaces_in_overlay[tunnel_mode][deviceid][overlay_name]) == 0:
            del self.interfaces_in_overlay[tunnel_mode][deviceid][overlay_name]

    def is_interface_in_overlay(self, tunnel_mode, deviceid, overlay_name, interface):
        return interface in self.interfaces_in_overlay[tunnel_mode][deviceid][overlay_name]

    # Add a VPN to the controller state
    # , tableid):
    def add_vpn(self, tunnel_id, vpn_name, vpn_type, interfaces, tenantid, tunnel_mode):
        # If the VPN already exists, return False
        if vpn_name in self.vpns:
            return False
        # Add the VPN to the VPNs dict
        self.vpns[vpn_name] = VPN(
            tunnel_id, vpn_name, vpn_type, interfaces, tenantid, tunnel_mode)  # , tableid)
        # Success, return True
        return True

    # Add an interface to a VPN
    def add_interface_to_vpn(self, vpn_name, interface):
        self.vpns[vpn_name].interfaces.add(interface)

    def remove_interface_from_vpn(self, vpn_name, interface):
        for _interface in self.vpns[vpn_name].interfaces.copy():
            if interface.routerid == _interface.routerid and interface.interface_name == _interface.interface_name:
                self.vpns[vpn_name].interfaces.remove(_interface)

    def remove_vpn(self, vpn_name):
        del self.vpns[vpn_name]

    # Create a dump of the VPNs
    def save_vpns_dump(self):
        # Build VPN dump dict
        """The dict has the following structure
           #
           vpn_dump_dict = dict({
                'vpns': dict(),
                'reusable_tableids': list(),
                'tableid_to_tenantid': dict(),
                'last_allocated_tableid': -1
        })
        """
        vpn_dump_dict = dict()
        # Parse VPN dump and fill data structures
        #
        # Process VPNs information
        vpn_dump_dict['vpns'] = dict()
        for vpn in self.vpns.values():
            # Build the list of the interfaces
            interfaces = list()
            # Iterate on all interfaces
            for _interfaces in vpn.interfaces.values():
                for _interface in _interfaces.values():
                    # Add a new interface to the list
                    interfaces.append({
                        'routerid': _interface.routerid,
                        'interface_name': _interface.interface_name,
                        'interface_ip': _interface.interface_ip,
                        'vpn_prefix': _interface.vpn_prefix
                    })
            # Add VPN to the mapping
            vpn_dump_dict['vpns'][vpn.vpn_name] = {
                'vpn_name': vpn.vpn_name,
                'tableid': vpn.tableid,
                'tenantid': vpn.tenantid,
                'interfaces': interfaces
            }
        # Process reusable table IDs set
        #reusable_tableids = list(self.tableid_allocator.reusable_tableids)
        #vpn_dump_dict['reusable_tableids'] = reusable_tableids
        # Process table IDs
        #tableid_to_tenantid = self.tableid_allocator.tableid_to_tenantid
        #vpn_dump_dict['tableid_to_tenantid'] = tableid_to_tenantid
        # Process last table ID
        #last_allocated_tableid = self.tableid_allocator.last_allocated_tableid
        #vpn_dump_dict['last_allocated_tableid'] = last_allocated_tableid
        # Write the dump to file
        with open(self.vpn_file, 'w') as outfile:
            json.dump(vpn_dump_dict, outfile, sort_keys=True, indent=2)

    # Import VPNs from dump
    def import_vpns_from_dump(self):
        try:
            # Open VPN dump file
            with open(self.vpn_file) as json_file:
                vpn_dump_dict = json.load(json_file)
            # Parse VPN dump and fill data structures
            #
            # Process VPNs information
            for vpn in vpn_dump_dict['vpns'].values():
                # table ID
                #vpn_to_tableid[vpn] = int(vpn['tableid'])
                # Interfaces
                interfaces = set()
                for interface in vpn['interfaces']:
                    interface = Interface(
                        interface['routerid'],
                        interface['interface_name'],
                        interface['interface_ip'],
                        interface['vpn_prefix']
                    )
                    interfaces.add(interface)
                # Tenant ID
                tenantid = vpn['tenantid']
                # VPN type
                vpn_type = vpn['vpn_type']
                # VPN name
                vpn_name = vpn['vpn_name']
                # Table ID
                tableid = vpn['tableid']
                # Build VPN and add the VPN to the VPNs dict
                self.vpns[vpn.vpn_name] = VPN(
                    vpn_name, vpn_type, interfaces, tenantid)  # , tableid)
            # Process reusable table IDs
            # for _id in vpn_dump_dict['reusable_tableids']:
            #    self.tableid_allocator.reusable_tableids.add(int(_id))
            # Process table IDs
            #tableid_to_tenantid = vpn_dump_dict['tableid_to_tenantid']
            # for tableid, tenantid in tableid_to_tenantid.items():
            #    tableid = int(tableid)
            #    tenantid = int(tenantid)
            #    self.tableid_allocator.tableid_to_tenantid[tableid] = tenantid
            # Process last table ID
            #last_tableid = int(vpn_dump_dict['last_allocated_tableid'])
            #self.tableid_allocator.last_allocated_tableid = last_tableid
        except IOError:
            print('VPN file not found')            

    # Get router's management IP address

    #def get_router_mgmtip(self, routerid):
    #    routerid = int(IPv4Address(routerid))
    #    return self.devices[routerid]['mgmtip']


# Generate a random token used to authenticate the tenant
def generate_token():
    # Example of token: J4Ie2QKOHz3IVSQs8yA1ahAKfl1ySrtVxGVuT6NkuElGfC8cm55rFhyzkc79pjSLOsr7zKOu7rkMgNMyEHlze4iXVNoX1AtifuieNrrW4rrCroScpGdQqHMETJU46okS
    seq = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
    token = ''
    for _ in range(0, 128):
        token += random.choice(seq)
    # Return the token
    return token


# Return true if the IP address belongs to the network
def IPv6AddrInNet(ipaddr, net):
    # return IPv6Interface(unicode(ipaddr)) in IPv6Network(unicode(net))
    return IPv6Interface(ipaddr) in IPv6Network(net)


# Find a IPv6 address contained in the net
def findIPv6AddrInNet(ipaddrs, net):
    for ipaddr in ipaddrs:
        if IPv6AddrInNet(ipaddr, net):
            return ipaddr
    return None


def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z


def print_and_die(msg, code=-2):
    print(msg)
    exit(code)


class TenantIDAllocator:
    def __init__(self):
        # Set of reusable tenant ID
        self.reusable_tenantids = set()
        # Last used tenant ID
        self.last_allocated_tenantid = -1
        # Mapping token to tenant ID
        self.token_to_tenantid = dict()
       
    # Allocate and return a new tenant ID for a token
    def get_new_tenantid(self, token):
        if self.token_to_tenantid.get(token):
            # The token already has a tenant ID
            return -1
        else:
            # Check if a reusable tenant ID is available
            if self.reusable_tenantids:
                tenantid = self.reusable_tenantids.pop()
            else:
                # Get new tenant ID
                self.last_allocated_tenantid += 1
                while self.last_allocated_tenantid in RESERVED_TENANTIDS:
                    # Skip reserved tenant ID
                    self.last_allocated_tenantid += 1
                tenantid = self.last_allocated_tenantid

            # If tenant ID is valid
            if validate_tenantid(tenantid) == True:
                # Assigne tenant ID to the token
                self.token_to_tenantid[token] = tenantid
                return tenantid
            # Return -1 if tenant IDs are finished
            else:
                return -1

    # Return tenant ID, if no tenant ID assigned to the token return -1
    def get_tenantid(self, token):
        return self.token_to_tenantid.get(token, -1)

    # Release tenant ID and mark it as reusable
    def release_tenantid(self, token):
        # Check if the token has an associated tenantid
        if token in self.token_to_tenantid:
            tenantid = self.token_to_tenantid[token]
            # Unassigne the tenant ID
            del self.token_to_tenantid[token]
            # Mark the tenant ID as reusable
            self.reusable_tenantids.add(tenantid)

            return tenantid
        else:
            # The token has not an associated tenant ID
            return -1

# Table ID Allocator


class TableIDAllocator:

    def __init__(self):
        # Mapping VPN name to table ID, indexed by tenant ID
        self.vpn_to_tableid = dict()
        # Set of reusable table IDs, indexed by tenant ID
        self.reusable_tableids = dict()
        # Last used table ID, indexed by tenant ID
        self.last_allocated_tableid = dict()

    # Allocate and return a new table ID for a VPN
    def get_new_tableid(self, vpn_name, tenantid):
        if tenantid not in self.vpn_to_tableid:
            # Initialize data structures
            self.vpn_to_tableid[tenantid] = dict()
            self.reusable_tableids[tenantid] = set()
            self.last_allocated_tableid[tenantid] = -1
        # Get the new table ID
        if self.vpn_to_tableid[tenantid].get(vpn_name):
            # The VPN already has an associated table ID
            return -1
        else:
            # Check if a reusable table ID is available
            if self.reusable_tableids[tenantid]:
                tableid = self.reusable_tableids[tenantid].pop()
            else:
                # If not, get a new table ID
                self.last_allocated_tableid[tenantid] += 1
                while self.last_allocated_tableid[tenantid] in RESERVED_TABLEIDS:
                    # Skip reserved table IDs
                    self.last_allocated_tableid[tenantid] += 1
                tableid = self.last_allocated_tableid[tenantid]
            # Assign the table ID to the VPN name
            self.vpn_to_tableid[tenantid][vpn_name] = tableid
            # And return
            return tableid

    # Return the table ID assigned to the VPN
    # If the VPN has no assigned table IDs, return -1
    def get_tableid(self, vpn_name, tenantid):
        if tenantid not in self.vpn_to_tableid:
            return -1
        return self.vpn_to_tableid[tenantid].get(vpn_name, -1)

    # Release a table ID and mark it as reusable
    def release_tableid(self, vpn_name, tenantid):
        # Check if the VPN has an associated table ID
        if self.vpn_to_tableid[tenantid].get(vpn_name):
            # The VPN has an associated table ID
            tableid = self.vpn_to_tableid[tenantid][vpn_name]
            # Unassign the table ID
            del self.vpn_to_tableid[tenantid][vpn_name]
            # Mark the table ID as reusable
            self.reusable_tableids[tenantid].add(tableid)
            # If the tenant has no VPNs,
            # destory data structures
            if len(self.vpn_to_tableid[tenantid]) == 0:
                del self.vpn_to_tableid[tenantid]
                del self.reusable_tableids[tenantid]
                del self.last_allocated_tableid[tenantid]
            # Return the table ID
            return tableid
        else:
            # The VPN has not an associated table ID
            return -1


class VTEPIPv6NetAllocator:

    bit = 16
    net = u"fcfb::/%d" % bit
    prefix = 64

    def __init__(self):
        print("*** Calculating Available Mgmt Addresses")
        self.hosts = (IPv6Network(self.net)).hosts()

    def nextVTEPAddress(self):
        n_host = next(self.hosts)
        return n_host.__str__()


class VTEPIPv4NetAllocator:

    bit = 8
    net = u"10.0.0.0/%d" % bit
    prefix = 16

    def __init__(self):
        print("*** Calculating Available Mgmt Addresses")
        self.vtepnet = (IPv4Network(self.net)).hosts()

    def nextVTEPAddress(self):
        n_host = next(self.vtepnet)
        return n_host.__str__()


# Utiliy function to check if the provided table ID is valid
def validate_table_id(tableid):
    return tableid >= MIN_TABLE_ID and tableid <= MAX_TABLE_ID


def validate_tenantid(tenantid):
    return tenantid >= 0 and tenantid <= 2**32-1


def validate_vpn_type(vpn_type):
    return True     # TODO


# Utiliy function to check if the IP
# is a valid IPv6 address
def validate_ipv6_address(ip):
    if ip is None:
        return False
    try:
        IPv6Interface(ip)
        return True
    except AddressValueError:
        return False


# Utiliy function to check if the IP
# is a valid IPv4 address
def validate_ipv4_address(ip):
    if ip is None:
        return False
    try:
        IPv4Interface(ip)
        return True
    except AddressValueError:
        return False


# Utiliy function to check if the IP
# is a valid address
def validate_ip_address(ip):
    return validate_ipv4_address(ip) or validate_ipv6_address(ip)


# Utiliy function to get the IP address family
def getAddressFamily(ip):
    if validate_ipv6_address(ip):
        # IPv6 address
        return AF_INET6
    elif validate_ipv4_address(ip):
        # IPv4 address
        return AF_INET
    else:
        # Invalid address
        return None


class VPNType:
    IPv4VPN = 1
    IPv6VPN = 2


class VPN:
    # tableid=-1):
    def __init__(self, tunnel_id, vpn_name, vpn_type, interfaces, tenantid, tunnel_mode):
        # Tunnel ID
        self.id = tunnel_id
        # VPN name
        self.vpn_name = vpn_name
        # VPN type
        self.vpn_type = vpn_type
        # Interfaces belonging to the VPN
        self.interfaces = set(interfaces)
        #self.interfaces = dict()
        # for interface in interfaces:
        #    routerid = interface.routerid
        #    interface_name = interface.interface_name
        #    if self.interfaces.get(routerid) is None:
        #        self.interfaces[routerid] = dict()
        #    self.interfaces[routerid][interface_name] = interface
        # Tenant ID
        self.tenantid = tenantid
        # Table ID
        #self.tableid = tableid
        #self.tunnel_specific_data = dict()
        self.tunnel_mode = tunnel_mode

    def removeInterface(self, routerid, interface_name):
        for interface in self.interfaces.copy():
            if interface.routerid == routerid and interface.interface_name == interface_name:
                self.interfaces.remove(interface)
                return True
        return False

    def numberOfInterfaces(self, routerid):
        num = 0
        for interface in self.interfaces:
            if interface.routerid == routerid:
                num += 1
        return num

    def getInterface(self, routerid, interface_name):
        for interface in self.interfaces:
            if interface.routerid == routerid and interface.interface_name == interface_name:
                return interface
        return None


class Interface:
    def __init__(self, routerid, interface_name):
        # Router ID
        self.routerid = routerid
        # Interface name
        self.interface_name = interface_name


# IPv6 utility functions

def del_ipv6_nd_prefix_quagga(router, intf, prefix):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    prefix = str(prefix)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Remove old IPv6 prefix
        tn.write(b'no ipv6 nd prefix %s\r\n' % prefix)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection '
              'to %s on port %s' % (str(router), str(port)))


def add_ipv6_nd_prefix_quagga(router, intf, prefix):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    prefix = str(prefix)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Remove old IPv6 prefix
        tn.write(b'ipv6 nd prefix %s\r\n' % prefix.encode())
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection '
              'to %s on port %s' % (str(router), str(port)))


def add_ipv6_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IPv6 address
        tn.write(b'ipv6 address %s\r\n' % ip.encode())
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection '
              'to %s on port %s' % (str(router), str(port)))


def del_ipv6_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IPv6 address
        tn.write(b'no ipv6 address %s\r\n' % ip)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection '
              'to %s on port %s' % (str(router), str(port)))


def flush_ipv6_addresses_ssh(router, intf):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Flush addresses
    cmd = 'ip -6 addr flush dev %s scope global' % intf
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def add_ipv6_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip -6 addr add %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def del_ipv6_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip -6 addr del %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


# IPv4 utility functions

def add_ipv4_default_via(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the default via
    cmd = 'ip route add default via %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def del_ipv4_default_via(router):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the default via
    cmd = 'ip route del default'
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def add_ipv4_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IP address
        tn.write(b'ip address %s\r\n' % ip)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection '
              'to %s on port %s' % (str(router), str(port)))


def del_ipv4_address_quagga(router, intf, ip):
    # Establish a telnet connection with the zebra daemon
    # and try to reconfigure the addressing plan of the router
    router = str(router)
    port = ZEBRA_PORT
    intf = str(intf)
    ip = str(ip)
    try:
        print('%s - Trying to reconfigure addressing plan' % router)
        password = 'srv6'
        # Init telnet
        tn = telnetlib.Telnet(router, port)
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Terminal length set to 0 to not have interruptions
        tn.write(b'terminal length 0\r\n')
        # Enable
        tn.write(b'enable\r\n')
        # Password
        tn.read_until(b'Password: ')
        tn.write(b'%s\r\n' % password.encode())
        # Configure terminal
        tn.write(b'configure terminal\r\n')
        # Interface configuration
        tn.write(b'interface %s\r\n' % intf.encode())
        # Add the new IP address
        tn.write(b'no ip address %s\r\n' % ip)
        # Close interface configuration
        tn.write(b'q\r\n')
        # Close configuration mode
        tn.write(b'q\r\n')
        # Close privileged mode
        tn.write(b'q\r\n')
        # Close telnet
        tn.close()
    except socket.error:
        print('Error: cannot establish a connection '
              'to %s on port %s' % (str(router), str(port)))


def flush_ipv4_addresses_ssh(router, intf):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Flush addresses
    cmd = 'ip addr flush dev %s' % intf
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def add_ipv4_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip addr add %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


def del_ipv4_address_ssh(router, intf, ip):
    # Utility to close a ssh session
    def close_ssh_session(session):
        # Close the session
        remoteCmd.close()
        # Flush the cache
        remoteCmd.cache.flush()
    # Add the address
    cmd = 'ip addr del %s dev %s' % (ip, intf)
    remoteCmd = SSHCommand(cmd, router, SSH_PORT, 'root', 'root')
    remoteCmd.run_status_stderr()
    # Close the session
    close_ssh_session(remoteCmd)


# Read topology JSON and return the topology graph
def json_file_to_graph(topo_file):
    # Read JSON file
    with open(topo_file) as f:
        topo_json = json.load(f)
    # Return graph from JSON file
    return json_graph.node_link_graph(topo_json)
