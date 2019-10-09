#!/usr/bin/python


# General imports
import sys
import re
import os
# ipaddress dependencies
from ipaddress import IPv6Interface
from ipaddress import IPv6Network
from ipaddress import IPv4Address


# Return true if the IP address belongs to the network
def IPv6AddrInNet(ipaddr, net):
    return IPv6Interface(str(ipaddr)) in IPv6Network(str(net))


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
