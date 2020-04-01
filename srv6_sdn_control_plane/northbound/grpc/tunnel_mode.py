#!/usr/bin/python

from srv6_sdn_proto.status_codes_pb2 import NbStatusCode


class TunnelMode(object):

    def __init__(self, name, overlay_type, topo_type,
                 grpc_client_port, srv6_manager, verbose):
        # Name of the tunnel
        self.name = name
        # The type of the overlay handled by the tunnel mode
        self.overlay_type = overlay_type
        # The type of the topology handled by the tunnel mode
        self.topo_type = topo_type
        # Port of the gRPC client
        self.grpc_client_port = grpc_client_port
        # Create SRv6 Manager
        self.srv6_manager = srv6_manager
        # Verbose mode
        self.verbose = verbose

    def init_hub(self, overlayid, overlay_name,
                 tenantid, deviceid, overlay_info):
        return NbStatusCode.STATUS_OK

    def init_overlay_data(self, overlayid, overlay_name,
                          tenantid, overlay_info):
        pass

    def init_tunnel_mode(self, deviceid, tenantid, overlay_info):
        pass

    def init_overlay(self, overlayid, overlay_name,
                     tenantid, routerid, overlay_info):
        pass

    def add_slice_to_overlay(self, overlayid, overlay_name, routerid,
                             interface_name, tenantid, overlay_info):
        pass

    def create_tunnel(self, overlayid, overlay_name,
                      local_site, remote_site, tenantid, overlay_info):
        pass

    def destroy_overlay_data(self, overlayid,
                             overlay_name, tenantid, overlay_info):
        pass

    def destroy_tunnel_mode(self, deviceid, tenantid, overlay_info):
        pass

    def destroy_overlay(self, overlayid, overlay_name,
                        tenantid, routerid, overlay_info):
        pass

    def remove_slice_from_overlay(self, overlayid, overlay_name,
                                  deviceid, interface_name,
                                  tenantid, overlay_info):
        pass

    def remove_tunnel(self, overlayid, overlay_name,
                      local_site, remote_site, tenantid, overlay_info):
        pass

    def destroy_hub(self, overlayid, overlay_name,
                    tenantid, deviceid, overlay_info):
        return NbStatusCode.STATUS_OK

    def get_overlays(self):
        raise NotImplementedError
