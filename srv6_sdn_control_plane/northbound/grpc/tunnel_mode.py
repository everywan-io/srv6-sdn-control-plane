#!/usr/bin/python


class TunnelMode(object):

    def __init__(self, name):
        self.name = name

    def init_overlay_data(self, overlay_name, tenantid, overlay_info):
        pass

    def init_tunnel_mode(self, deviceid, overlay_info):
        pass

    def init_overlay(self, overlay_name, overlay_type, deviceid, overlay_info):
        pass

    def add_slice_to_overlay(self, overlay_name,
                             deviceid, interface_name, overlay_info):
        pass

    def create_tunnel(self, overlay_name, overlay_type,
                      l_slice, r_slice, tenantid, overlay_info):
        pass

    def destroy_overlay_data(self, overlay_name, tenantid, overlay_info):
        pass

    def destroy_tunnel_mode(self, deviceid, overlay_info):
        pass

    def destroy_overlay(self, overlay_name,
                        overlay_type, deviceid, overlay_info):
        pass

    def remove_slice_from_overlay(self, overlay_name,
                                  deviceid, interface_name, overlay_info):
        pass

    def remove_tunnel(self, overlay_name, overlay_type,
                      l_slice, r_slice, tenantid, overlay_info):
        pass

    def get_overlays(self):
        raise NotImplementedError
