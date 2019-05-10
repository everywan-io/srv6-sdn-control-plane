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
NB_GRPC_CLIENT_PATH = '/home/user/repos/srv6-sdn-control-plane/northbound/grpc/'
sys.path.append(NB_GRPC_CLIENT_PATH)
from nb_grpc_client import *
from vpn_utils import *
from vpn4_utils import *


INBAND = False

# Parse options
def parse_options():
    global SECURE, INBAND
    parser = OptionParser()
    parser.add_option("--inband", action="store_true", default=False, help="Enable in-band management")
    # Parse input parameters
    (options, args) = parser.parse_args()
    INBAND = options.inband
    # Parse input parameters
    (options, args) = parser.parse_args()

# Test for VPN use case
def run_tests():
    global INBAND
    if INBAND:
        # Create VPN
        name = 'research'
        interfaces = [
            ('fdff::1', 'ads1-eth3', '172.16.1.0/24', '172.16.1.1/24'),
            ('fdff:0:0:100::1', 'ads2-eth3', '172.16.3.0/24', '172.16.3.1/24')
        ]
        tenantid = 10
        intent = VPNIntent(name, interfaces, tenantid)
        create_vpn(intent)
        # Remove all addresses in the hosts
        #flush_addresses_ssh('2000::4', 'hads11-eth1')
        #flush_addresses_ssh('2000::6', 'hads21-eth1')
        # Add the private addresses to the interfaces in the hosts
        #add_address_ssh('2000::4', 'hads11-eth1', 'fc00::10:0:2/96')
        #add_address_ssh('2000::6', 'hads21-eth1', 'fc00::30:0:2/96')

        name = 'research'
        interfaces = [
            ('fdff::1', 'ads1-eth4', '172.16.2.0/24', '172.16.2.1/24'),
            ('fdff:0:0:200::1', 'sur1-eth3', '172.16.4.0/24', '172.16.4.1/24'),
            ('fdff:0:0:200::1', 'sur1-eth4', '172.16.5.0/24', '172.16.5.1/24')
        ]
        tenantid = 20
        intent = VPNIntent(name, interfaces, tenantid)
        create_vpn(intent)
        # Remove all addresses in the hosts
        #flush_addresses_ssh('2000::5', 'hads12-eth1')
        #flush_addresses_ssh('2000::8', 'hsur11-eth1')
        #flush_addresses_ssh('2000::8', 'hsur12-eth1')
        # Add the private addresses to the interfaces in the hosts
        #add_address_ssh('2000::5', 'hads12-eth1', 'fc00::20:0:2/96')
        #add_address_ssh('2000::8', 'hsur11-eth1', 'fc00::40:0:2/96')
        #add_address_ssh('2000::8', 'hsur12-eth1', 'fc00::50:0:2/96')

        # Remove VPN
        remove_vpn('research', 20)
        # Remove all addresses in the hosts
        #flush_addresses_ssh('2000::5', 'hads12-eth1')
        #flush_addresses_ssh('2000::8', 'hsur11-eth1')
        #flush_addresses_ssh('2000::8', 'hsur12-eth1')
        # Add the public addresses to the interfaces in the hosts
        #add_address_ssh('2000::5', 'hads12-eth1', 'fdf0:0:0:6::2/64')
        #add_address_ssh('2000::8', 'hsur11-eth1', 'fdf0:0:0:5::2/64')
        #add_address_ssh('2000::8', 'hsur12-eth1', 'fdf0:0:0:8::2/64')
        # Add the public prefixes addresses to the interfaces in the routers
        #add_nd_prefix_quagga('fdff::1', 2601, 'ads1-eth4', 'fdf0:0:0:6::/64')
        #add_nd_prefix_quagga('fdff:0:0:200::1', 2601, 'sur1-eth3', 'fdf0:0:0:5::/64')
        #add_nd_prefix_quagga('fdff:0:0:200::1', 2601, 'sur1-eth4', 'fdf0:0:0:8::/64')
        # Add the public addresses to the interfaces in the hosts
        add_address_quagga('fdff::1', 2601, 'ads1-eth4', '10.3.0.1/16')
        add_address_quagga('fdff:0:0:200::1', 2601, 'sur1-eth3', '10.2.0.1/24')
        add_address_quagga('fdff:0:0:200::1', 2601, 'sur1-eth4', '10.5.0.1/24')


        name = 'research'
        interfaces = [
            ('fdff::1', 'ads1-eth4', '172.16.10.0/24', '172.16.10.1/24'),
            ('fdff:0:0:100::1', 'ads2-eth4', '172.16.20.0/24', '172.16.20.1/24'),
            ('fdff:0:0:200::1', 'sur1-eth4', '172.16.30.0/24', '172.16.30.1/24')
        ]
        tenantid = 20
        intent = VPNIntent(name, interfaces, tenantid)
        create_vpn(intent)
        # Remove all addresses in the hosts
        #flush_addresses_ssh('2000::4', 'hads12-eth1')
        #flush_addresses_ssh('2000::7', 'hads22-eth1')
        #flush_addresses_ssh('2000::9', 'hsur12-eth1')
        # Add the private addresses to the interfaces in the hosts
        #add_address_ssh('2000::4', 'hads12-eth1', 'fc00::100:0:2/96')
        #add_address_ssh('2000::7', 'hads22-eth1', 'fc00::200:0:2/96')
        #add_address_ssh('2000::9', 'hsur12-eth1', 'fc00::300:0:2/96')


        # Remove interface
        name = 'research'
        router_id = 'fdff::1'
        interface = 'ads1-eth4'
        tenantid = 20
        remove_interface_from_vpn(name, tenantid, router_id, interface)
        # Remove all addresses in the hosts
        #flush_addresses_ssh('2000::4', 'hads12-eth1')
        # Add the public addresses to the interfaces in the hosts
        #add_address_ssh('2000::4', 'hads12-eth1', 'fdf0:0:0:6::2/64')
        # Add the public prefixes to the interfaces in the routers
        #add_nd_prefix_quagga('fdff::1', 2601, 'ads1-eth4', 'fdf0:0:0:6::/64')
        # Add the public addresses to the interfaces in the routers
        add_address_quagga('fdff::1', 2601, 'ads1-eth4', '10.3.0.1/16')


        # Add interface
        name = 'research'
        interface = ('fdff::1', 'ads1-eth4', '172.16.40.0/24', '172.16.40.1/24')
        tenantid = 10
        add_interface_to_vpn(name, tenantid, interface)
        # Remove all addresses in the hosts
        #flush_addresses_ssh('2000::5', 'hads12-eth1')
        # Add the private prefixes to the interfaces in the routers
        #add_address_ssh('2000::5', 'hads12-eth1', 'fc00::400:0:2/96')


        # Print the VPNs
        print_vpns()

    else:
        # Create VPN
        name = 'research'
        interfaces = [
            ('2000::1', 'ads1-eth3', '172.16.1.0/24', '172.16.1.1/24'),
            ('2000::2', 'ads2-eth3', '172.16.3.0/24', '172.16.3.1/24')
        ]
        tenantid = 10
        intent = VPNIntent(name, interfaces, tenantid)
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

        name = 'research'
        interfaces = [
            ('2000::1', 'ads1-eth4', '172.16.2.0/24', '172.16.2.1/24'),
            ('2000::3', 'sur1-eth3', '172.16.4.0/24', '172.16.4.1/24'),
            ('2000::3', 'sur1-eth4', '172.16.5.0/24', '172.16.5.1/24')
        ]
        tenantid = 20
        intent = VPNIntent(name, interfaces, tenantid)
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

        # Remove VPN
        remove_vpn('research', 20)
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
        # Add the public prefixes addresses to the interfaces in the routers
        #add_nd_prefix_quagga('2000::1', 2601, 'ads1-eth4', 'fdf0:0:0:6::/64')
        #add_nd_prefix_quagga('2000::3', 2601, 'sur1-eth3', 'fdf0:0:0:5::/64')
        #add_nd_prefix_quagga('2000::3', 2601, 'sur1-eth4', 'fdf0:0:0:8::/64')
        # Add the public addresses to the interfaces in the hosts
        add_address_quagga('2000::1', 2601, 'ads1-eth4', '10.3.0.1/24')
        add_address_quagga('2000::3', 2601, 'sur1-eth3', '10.2.0.1/24')
        add_address_quagga('2000::3', 2601, 'sur1-eth4', '10.5.0.1/24')


        name = 'research'
        interfaces = [
            ('2000::1', 'ads1-eth4', '172.16.10.0/24', '172.16.10.1/24'),
            ('2000::2', 'ads2-eth4', '172.16.20.0/24', '172.16.20.1/24'),
            ('2000::3', 'sur1-eth4', '172.16.30.0/24', '172.16.30.1/24')
        ]
        tenantid = 20
        intent = VPNIntent(name, interfaces, tenantid)
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


        # Remove interface
        name = 'research'
        router_id = '2000::1'
        interface = 'ads1-eth4'
        tenantid = 20
        remove_interface_from_vpn(name, tenantid, router_id, interface)
        # Remove all addresses in the hosts
        flush_addresses_ssh('2000::5', 'hads12-eth1')
        # Add the public addresses to the interfaces in the hosts
        add_address_ssh('2000::5', 'hads12-eth1', '10.3.0.2/16')
        # Remove old default route
        del_default_via('2000::5')
        # Add the default via
        add_default_via('2000::5', 'hads12-eth1', '10.3.0.1')
        # Add the public prefixes to the interfaces in the routers
        #add_nd_prefix_quagga('2000::1', 2601, 'ads1-eth4', 'fdf0:0:0:6::/64')
        # Add the public addresses to the interfaces in the routers
        add_address_quagga('2000::1', 2601, 'ads1-eth4', '10.3.0.1/24')


        # Add interface
        name = 'research'
        interface = ('2000::1', 'ads1-eth4', '172.16.40.0/24', '172.16.40.1/24')
        tenantid = 10
        add_interface_to_vpn(name, tenantid, interface)
        # Remove all addresses in the hosts
        flush_addresses_ssh('2000::5', 'hads12-eth1')
        # Add the private prefixes to the interfaces in the routers
        add_address_ssh('2000::5', 'hads12-eth1', '172.16.40.2/24')
        # Remove old default route
        del_default_via('2000::5')
        # Add the default via
        add_default_via('2000::5', 'hads12-eth1', '172.16.40.1')


        # Print the VPNs
        print_vpns()


if __name__ == '__main__':
    parse_options()
    run_tests()