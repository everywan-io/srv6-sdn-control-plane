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
# Utils for VPN use case
#
# @author Carmine Scarpitta <carmine.scarpitta.94@gmail.com>
# @author Pier Luigi Ventre <pier.luigi.ventre@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#


class VPNIntent:
    def __init__(self, vpn_name, interfaces, tenantid):
        # VPN name
        self.vpn_name = vpn_name
        # Interfaces belonging to the VPN
        self.interfaces = interfaces
        # Tenant ID
        self.tenantid = tenantid

    def dump(self):
        intent = dict()
        intent['vpn_name'] = self.vpn_name
        intent['interfaces'] = [intf.dump() for intf in self.interfaces]
        intent['tenantid'] = self.tenantid
        return intent


class Interface:
    def __init__(self, router, ifname, ipaddrs=()):
        # Router ID
        self.router = router
        # Interface name
        self.ifname = ifname
        # IP addresses
        self.ipaddrs = ipaddrs

    def dump(self):
        intf = dict()
        intf['router'] = self.router
        intf['ifname'] = self.ifname
        intf['ipaddrs'] = [ipaddr.dump() for ipaddr in self.ipaddrs]
        return intf


class IPAddress:
    def __init__(self, ip, net):
        # IP address
        self.ip = ip
        # Net
        self.net = net

    def dump(self):
        ipaddr = dict()
        ipaddr['ip'] = self.ip
        ipaddr['net'] = self.net
        return ipaddr
