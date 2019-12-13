#!/usr/bin/python

class TunnelMode(object):

    def __init__(self, name):
        self.name = name
        self.initiated_tunnels = set()

    def init_tunnel(self):
        raise NotImplementedError

    def destroy_tunnel(self):
        raise NotImplementedError

    def create_tunnel(self):
        raise NotImplementedError

    def remove_tunnel(self):
        raise NotImplementedError

    def get_tunnels(self):
        raise NotImplementedError
