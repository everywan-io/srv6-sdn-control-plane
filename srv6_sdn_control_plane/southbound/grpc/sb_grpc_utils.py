#!/usr/bin/python

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