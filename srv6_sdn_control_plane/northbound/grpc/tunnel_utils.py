#!/usr/bin/python

from srv6_sdn_control_plane.northbound.grpc import srv6_tunnel
from srv6_sdn_control_plane.northbound.grpc import gre_tunnel
from srv6_sdn_control_plane.northbound.grpc import vxlan_tunnel

tunnel = dict()
tunnel_str = dict()

tunnel_info = dict()


class TunnelState:

    def __init__(self, srv6_manager, grpc_client_port, verbose):
        self.tunnel_modes = dict()
        self.srv6_manager = srv6_manager
        self.init_tunnel_modes(grpc_client_port, verbose)

    def register_tunnel_mode(self, tunnel_mode):
        name = tunnel_mode.name
        overlay_type = tunnel_mode.overlay_type
        topo_type = tunnel_mode.topo_type
        if name not in self.tunnel_modes:
            self.tunnel_modes[name] = dict()
        if overlay_type not in self.tunnel_modes[name]:
            self.tunnel_modes[name][overlay_type] = dict()
        self.tunnel_modes[name][overlay_type][topo_type] = tunnel_mode

    def unregister_tunnel_mode(self, name):
        del self.tunnel_modes[name]

    def init_tunnel_modes(self, grpc_client_port, verbose):
        self.register_tunnel_mode(srv6_tunnel.IPv4SRv6TunnelFM(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        self.register_tunnel_mode(srv6_tunnel.IPv6SRv6TunnelFM(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        # self.register_tunnel_mode(gre_tunnel.GRETunnel(
        #     srv6_manager=self.srv6_manager,
        #     grpc_client_port=grpc_client_port,
        #     verbose=verbose)
        # )
        # VXLAN modules registration
        #
        # L2 Full-Mesh VXLAN tunnel
        self.register_tunnel_mode(vxlan_tunnel.L2VXLANTunnelFM(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        # IPv4 Full-Mesh VXLAN tunnel
        self.register_tunnel_mode(vxlan_tunnel.IPv4VXLANTunnelFM(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        # IPv6 Full-Mesh VXLAN tunnel
        self.register_tunnel_mode(vxlan_tunnel.IPv6VXLANTunnelFM(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        # L2 Hub-and-Spoke VXLAN tunnel
        self.register_tunnel_mode(vxlan_tunnel.L2VXLANTunnelHS(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        # IPv4 Hub-and-Spoke VXLAN tunnel
        self.register_tunnel_mode(vxlan_tunnel.IPv4VXLANTunnelHS(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
        # IPv6 Hub-and-Spoke VXLAN tunnel
        self.register_tunnel_mode(vxlan_tunnel.IPv6VXLANTunnelHS(
            srv6_manager=self.srv6_manager,
            grpc_client_port=grpc_client_port,
            verbose=verbose)
        )
