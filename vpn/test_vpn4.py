#!/usr/bin/python

# Copyright (C) 2018 Carmine Scarpitta, Pier Luigi Ventre, Stefano Salsano - (CNIT and University of Rome "Tor Vergata")
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Utils for VPN management
#
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#


import sys
from optparse import OptionParser

NB_GRPC_CLIENT_PATH =  \
    '/home/user/repos/srv6-sdn-control-plane/northbound/grpc/'
sys.path.append(NB_GRPC_CLIENT_PATH)

from nb_grpc_client import print_vpns
from nb_grpc_client import create_vpn
from nb_grpc_client import add_interface_to_vpn
from nb_grpc_client import remove_interface_from_vpn, remove_vpn

from vpn_utils import IPAddress, Interface, VPNIntent
from vpn4_utils import add_address_quagga
from vpn4_utils import add_address_ssh
from vpn4_utils import flush_addresses_ssh
from vpn4_utils import add_default_via
from vpn4_utils import del_default_via


INBAND = False


# Parse options
def parse_options():
    global SECURE, INBAND
    parser = OptionParser()
    parser.add_option("--inband", action="store_true",
                      default=False, help="Enable in-band management")
    # Parse input parameters
    (options, args) = parser.parse_args()
    INBAND = options.inband
    # Parse input parameters
    (options, args) = parser.parse_args()


def inband_test_create_vpn_1():
    # Create VPN 10-research
    name = 'research'
    # Create interfaces
    # IP addresses used by tests
    # First interface
    ipaddr1 = IPAddress('172.16.1.1/24', '172.16.1.0/24')
    if1 = Interface('fdff::1', 'ads1-eth3', (ipaddr1,))
    # Second interface
    ipaddr2 = IPAddress('172.16.3.1/24', '172.16.3.0/24')
    if2 = Interface('fdff:0:0:100::1', 'ads2-eth3', (ipaddr2,))
    # List of interfaces
    interfaces = [
        if1,
        if2
    ]
    # Tenant ID
    tenantid = 10
    # Create the intent
    intent = VPNIntent(name, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)


def inband_test_create_vpn_2():
    # Create VPN 20-reserch
    name = 'research'
    # Create interfaces
    # First interface
    ipaddr1 = IPAddress('172.16.2.1/24', '172.16.2.0/24')
    if1 = Interface('fdff::1', 'ads1-eth4', (ipaddr1,))
    # Second interface
    ipaddr2 = IPAddress('172.16.4.1/24', '172.16.4.0/24')
    if2 = Interface('fdff:0:0:200::1', 'sur1-eth3', (ipaddr2,))
    # Third interface
    ipaddr3 = IPAddress('172.16.5.1/24', '172.16.5.0/24')
    if3 = Interface('fdff:0:0:200::1', 'sur1-eth4', (ipaddr3,))
    # List of interfaces
    interfaces = [
        if1,
        if2,
        if3
    ]
    # Tenant ID
    tenantid = 20
    # Create the intent
    intent = VPNIntent(name, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)


def inband_test_remove_vpn():
    # Remove VPN 20-research
    remove_vpn('research', 20)
    # Add the public addresses to the interfaces in the hosts
    add_address_quagga('fdff::1', 'ads1-eth4', '10.3.0.1/16')
    add_address_quagga('fdff:0:0:200::1', 'sur1-eth3', '10.2.0.1/24')
    add_address_quagga('fdff:0:0:200::1', 'sur1-eth4', '10.5.0.1/24')


def inband_test_create_vpn_3():
    # Create VPN 20-research
    name = 'research'
    # Create interfaces
    # First interface
    ipaddr1 = IPAddress('172.16.10.1/24', '172.16.10.0/24')
    if1 = Interface('fdff::1', 'ads1-eth4', (ipaddr1,))
    # Second interface
    ipaddr2 = IPAddress('172.16.20.1/24', '172.16.20.0/24')
    if2 = Interface('fdff:0:0:100::1', 'ads2-eth4', (ipaddr2,))
    # Third interface
    ipaddr3 = IPAddress('172.16.30.1/24', '172.16.30.0/24')
    if3 = Interface('fdff:0:0:200::1', 'sur1-eth4', (ipaddr3,))
    interfaces = [
        if1,
        if2,
        if3
    ]
    # Tenant ID
    tenantid = 20
    # Create the intent
    intent = VPNIntent(name, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)


def inband_test_remove_interface():
    # Remove interface
    name = 'research'
    # Create the interface
    if1 = Interface('fdff::1', 'ads1-eth4')
    # Tenant ID
    tenantid = 20
    # Run remove interface command
    remove_interface_from_vpn(name, tenantid, if1)
    # Add the public addresses to the interfaces in the routers
    add_address_quagga('fdff::1', 'ads1-eth4', '10.3.0.1/16')


def inband_test_add_interface():
    # Add interface
    name = 'research'
    # Create the IP address
    ipaddr = IPAddress('172.16.40.1/24', '172.16.40.0/24')
    # Create the interface
    if1 = Interface('fdff::1', 'ads1-eth4', (ipaddr,))
    tenantid = 10
    add_interface_to_vpn(name, tenantid, if1)


def outofband_test_create_vpn_1():
    # Create VPN 10-research
    name = 'research'
    # Create interfaces
    # IP addresses used by tests
    # First interface
    ipaddr1 = IPAddress('172.16.1.1/24', '172.16.1.0/24')
    if1 = Interface('2000::1', 'ads1-eth3', (ipaddr1,))
    # Second interface
    ipaddr2 = IPAddress('172.16.3.1/24', '172.16.3.0/24')
    if2 = Interface('2000::2', 'ads2-eth3', (ipaddr2,))
    # List of interfaces
    interfaces = [
        if1,
        if2
    ]
    # Tenant ID
    tenantid = 10
    # Create the intent
    intent = VPNIntent(name, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)
    # Remove all addresses in the hosts
    flush_addresses_ssh('2000::4', 'hads11-eth1')
    flush_addresses_ssh('2000::6', 'hads21-eth1')
    # Add the private addresses to the interfaces in the hosts
    add_address_ssh('2000::4', 'hads11-eth1', '172.16.1.2/24')
    add_address_ssh('2000::6', 'hads21-eth1', '172.16.3.2/24')
    # Remove old default route
    del_default_via('2000::4')
    del_default_via('2000::6')
    # Add the default via
    add_default_via('2000::4', 'hads11-eth1', '172.16.1.1')
    add_default_via('2000::6', 'hads21-eth1', '172.16.3.1')


def outofband_test_create_vpn_2():
    # Create VPN 20-reserch
    name = 'research'
    # Create interfaces
    # First interface
    ipaddr1 = IPAddress('172.16.2.1/24', '172.16.2.0/24')
    if1 = Interface('2000::1', 'ads1-eth4', (ipaddr1,))
    # Second interface
    ipaddr2 = IPAddress('172.16.4.1/24', '172.16.4.0/24')
    if2 = Interface('2000::3', 'sur1-eth3', (ipaddr2,))
    # Third interface
    ipaddr3 = IPAddress('172.16.5.1/24', '172.16.5.0/24')
    if3 = Interface('2000::3', 'sur1-eth4', (ipaddr3,))
    # List of interfaces
    interfaces = [
        if1,
        if2,
        if3
    ]
    # Tenant ID
    tenantid = 20
    # Create the intent
    intent = VPNIntent(name, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)
    # Remove all addresses in the hosts
    flush_addresses_ssh('2000::5', 'hads12-eth1')
    flush_addresses_ssh('2000::8', 'hsur11-eth1')
    flush_addresses_ssh('2000::9', 'hsur12-eth1')
    # Add the private addresses to the interfaces in the hosts
    add_address_ssh('2000::5', 'hads12-eth1', '172.16.2.2/24')
    add_address_ssh('2000::8', 'hsur11-eth1', '172.16.4.2/24')
    add_address_ssh('2000::9', 'hsur12-eth1', '172.16.5.2/24')
    # Remove old default route
    del_default_via('2000::5')
    del_default_via('2000::8')
    del_default_via('2000::9')
    # Add the default via
    add_default_via('2000::5', 'hads12-eth1', '172.16.2.1')
    add_default_via('2000::8', 'hsur11-eth1', '172.16.4.1')
    add_default_via('2000::9', 'hsur12-eth1', '172.16.5.1')


def outofband_test_remove_vpn():
    # Remove VPN 20-research
    remove_vpn('research', 20)
    # Add the public addresses to the interfaces in the hosts
    add_address_quagga('2000::1', 'ads1-eth4', '10.3.0.1/24')
    add_address_quagga('2000::3', 'sur1-eth3', '10.0.0.1/24')
    add_address_quagga('2000::3', 'sur1-eth4', '10.5.0.1/24')
    # Remove all addresses in the hosts
    flush_addresses_ssh('2000::5', 'hads12-eth1')
    flush_addresses_ssh('2000::8', 'hsur11-eth1')
    flush_addresses_ssh('2000::9', 'hsur12-eth1')
    # Add the public addresses to the interfaces in the hosts
    add_address_ssh('2000::5', 'hads12-eth1', '10.3.0.2/16')
    add_address_ssh('2000::8', 'hsur11-eth1', '10.0.0.2/16')
    add_address_ssh('2000::9', 'hsur12-eth1', '10.5.0.2/16')
    # Remove old default route
    del_default_via('2000::5')
    del_default_via('2000::8')
    del_default_via('2000::9')
    # Add the default via
    add_default_via('2000::5', 'hads12-eth1', '10.3.0.1')
    add_default_via('2000::8', 'hsur11-eth1', '10.0.0.1')
    add_default_via('2000::9', 'hsur12-eth1', '10.5.0.1')


def outofband_test_create_vpn_3():
    # Create VPN 20-research
    name = 'research'
    # Create interfaces
    # First interface
    ipaddr1 = IPAddress('172.16.10.1/24', '172.16.10.0/24')
    if1 = Interface('2000::1', 'ads1-eth4', (ipaddr1,))
    # Second interface
    ipaddr2 = IPAddress('172.16.20.1/24', '172.16.20.0/24')
    if2 = Interface('2000::2', 'ads2-eth4', (ipaddr2,))
    # Third interface
    ipaddr3 = IPAddress('172.16.30.1/24', '172.16.30.0/24')
    if3 = Interface('2000::3', 'sur1-eth4', (ipaddr3,))
    interfaces = [
        if1,
        if2,
        if3
    ]
    # Tenant ID
    tenantid = 20
    # Create the intent
    intent = VPNIntent(name, interfaces, tenantid)
    # Send creation command through the northbound API
    create_vpn(intent)
    # Remove all addresses in the hosts
    flush_addresses_ssh('2000::5', 'hads12-eth1')
    flush_addresses_ssh('2000::7', 'hads22-eth1')
    flush_addresses_ssh('2000::9', 'hsur12-eth1')
    # Add the private addresses to the interfaces in the hosts
    add_address_ssh('2000::5', 'hads12-eth1', '172.16.10.2/24')
    add_address_ssh('2000::7', 'hads22-eth1', '172.16.20.2/24')
    add_address_ssh('2000::9', 'hsur12-eth1', '172.16.30.2/24')
    # Remove old default route
    del_default_via('2000::5')
    del_default_via('2000::7')
    del_default_via('2000::9')
    # Add the default via
    add_default_via('2000::5', 'hads12-eth1', '172.16.10.1')
    add_default_via('2000::7', 'hads22-eth1', '172.16.20.1')
    add_default_via('2000::9', 'hsur12-eth1', '172.16.30.1')


def outofband_test_remove_interface():
    # Remove interface
    name = 'research'
    # Create the interface
    if1 = Interface('2000::1', 'ads1-eth4')
    # Tenant ID
    tenantid = 20
    # Run remove interface command
    remove_interface_from_vpn(name, tenantid, if1)
    # Add the public addresses to the interfaces in the routers
    add_address_quagga('2000::1', 'ads1-eth4', '10.3.0.1/24')
    # Remove all addresses in the hosts
    flush_addresses_ssh('2000::5', 'hads12-eth1')
    # Add the public addresses to the interfaces in the hosts
    add_address_ssh('2000::5', 'hads12-eth1', '10.3.0.2/16')
    # Remove old default route
    del_default_via('2000::5')
    # Add the default via
    add_default_via('2000::5', 'hads12-eth1', '10.3.0.1')


def outofband_test_add_interface():
    # Add interface
    name = 'research'
    # Create the IP address
    ipaddr = IPAddress('172.16.40.1/24', '172.16.40.0/24')
    # Create the interface
    if1 = Interface('2000::1', 'ads1-eth4', (ipaddr,))
    # Tenant ID
    tenantid = 10
    # Execute add interface command
    add_interface_to_vpn(name, tenantid, if1)
    # Remove all addresses in the hosts
    flush_addresses_ssh('2000::5', 'hads12-eth1')
    # Add the private prefixes to the interfaces in the routers
    add_address_ssh('2000::5', 'hads12-eth1', '172.16.40.2/24')
    # Remove old default route
    del_default_via('2000::5')
    # Add the default via
    add_default_via('2000::5', 'hads12-eth1', '172.16.40.1')


# Test for VPN use case
def run_tests():
    global INBAND
    if INBAND:
        # Run tests
        inband_test_create_vpn_1()
        inband_test_create_vpn_2()
        inband_test_remove_vpn()
        inband_test_create_vpn_3()
        inband_test_remove_interface()
        inband_test_add_interface()
        # Print the VPNs
        print_vpns()
    else:
        # Run tests
        outofband_test_create_vpn_1()
        outofband_test_create_vpn_2()
        outofband_test_remove_vpn()
        outofband_test_create_vpn_3()
        outofband_test_remove_interface()
        outofband_test_add_interface()
        # Print the VPNs
        print_vpns()


if __name__ == '__main__':
    parse_options()
    run_tests()
