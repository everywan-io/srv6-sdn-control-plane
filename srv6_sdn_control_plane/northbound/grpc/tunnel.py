#!/usr/bin/python

import srv6_utils

tunnel = dict()
tunnel_str = dict()

tunnel_info = dict()

def register_tunnel(name, num, ops):
	tunnel[name] = num
	tunnel_str[num] = name
	tunnel_info[name] = ops

def unregister_tunnel(name):
	num = tunnel[name]
	del tunnel[name]
	del tunnel_str[num]
	del tunnel_info[name]