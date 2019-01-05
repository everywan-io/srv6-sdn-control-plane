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


if __name__ == '__main__':
     # Create VPNs for testing purposes

    name = 'research'
    interfaces = [('0.0.0.1', 'ads1-eth3', 'fc00::10:0:1/96'),('0.0.0.2', 'ads2-eth3', 'fc00::30:0:1/96')]
    tenant_id = 10
    intent = VPNIntent(name, interfaces, tenant_id)
    create_vpn(intent)

    name = 'research'
    interfaces = [('0.0.0.1', 'ads1-eth4', 'fc00::20:0:1/96'),('0.0.0.3', 'sur1-eth3', 'fc00::40:0:1/96'), ('0.0.0.3', 'sur1-eth4', 'fc00::50:0:1/96')]
    tenant_id = 20
    intent = VPNIntent(name, interfaces, tenant_id)
    create_vpn(intent)

    '''
    remove_vpn('research', 20)

    name = 'research'
    interfaces = [('0.0.0.1', 'ads1-eth4', '3111::1/64'),('0.0.0.2', 'ads2-eth4', '3211::1/64'), ('0.0.0.3', 'sur1-eth4', '3311::1/64')]
    tenant_id = 20
    intent = VPNIntent(name, interfaces, tenant_id)
    create_vpn(intent)
    '''

    print_vpns()
