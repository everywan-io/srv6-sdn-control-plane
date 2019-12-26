#!/usr/bin/python

class TunnelMode(object):

    def __init__(self, name):
        self.name = name

    def create_overlay_net(self, overlay_name, overlay_type, sites, tenantid, overlay_info):
        raise NotImplementedError

    def remove_overlay_net(self, overlay_name, tenantid, overlay_info):
        raise NotImplementedError

    def add_site_to_overlay(self, overlay_name, tenantid, site, overlay_info):
        raise NotImplementedError

    def remove_site_from_overlay(self, overlay_name, tenantid, site, overlay_info):
        raise NotImplementedError

    def get_overlays(self):
        raise NotImplementedError