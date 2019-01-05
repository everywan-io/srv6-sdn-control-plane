#!/usr/bin/python

import grpc
import json


# Folders
CONTROL_PLANE_FOLDER = "~/repos/srv6-sdn-control-plane/"
PROTO_FOLDER = CONTROL_PLANE_FOLDER + "~/repos/srv6-sdn-proto/"

import sys
# Add path of proto files
sys.path.append(PROTO_FOLDER)

import srv6_explicit_path_pb2_grpc
import srv6_explicit_path_pb2

import srv6_vpn_pb2_grpc
import srv6_vpn_pb2

from threading import Thread
from time import sleep

# Define wheter to use SSL or not
SECURE = False
# SSL cerificate for server validation
CERTIFICATE = 'cert_client.pem'


class SRv6ExplicitPathHandler:

  # Build a grpc stub
  def get_grpc_session(self, ip_address, port, secure):
      # If secure we need to establish a channel with the secure endpoint
      if secure:
          # Open the certificate file
          with open(CERTIFICATE) as f:
              certificate = f.read()
          # Then create the SSL credentials and establish the channel
          grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
          channel = grpc.secure_channel("%s:%s" %(ip_address, port), grpc_client_credentials)
      else:
         channel = grpc.insecure_channel("%s:%s" %(ip_address, port))
      return srv6_explicit_path_pb2_grpc.SRv6ExplicitPathStub(channel), channel


  def add(self, destination, device, segments):
      # Get the reference of the stub
      srv6_stub,channel = self.get_grpc_session("localhost", 12345, SECURE)
      # Create message request
      path_request = srv6_explicit_path_pb2.SRv6EPRequest()
      # Create a new path
      path = path_request.path.add()
      # Set destination, device, encapmode
      path.destination = destination
      path.device = device
      path.encapmode = "inline"
      for segment in segments:
          # Create a new segment
          srv6_segment = path.sr_path.add()
          srv6_segment.segment = segment
      # Add
      response = srv6_stub.Create(path_request)
      print response
      # Let's close the session
      channel.close()


  def addFromJson(self, data):
      json_data = json.loads(data)
      # Iterate over the array and delete one by one all the paths
      for data in json_data:
          # Each time we create a new session
          srv6_stub,channel = self.get_grpc_session("localhost", 12345, SECURE)
          path_request = srv6_explicit_path_pb2.SRv6EPRequest()
          for jpath in data['paths']:
              path = path_request.path.add()
              path.destination = jpath['destination']
              path.device = jpath['device']
              path.encapmode = jpath['encapmode']
              for segment in jpath['segments']:
                  srv6_segment = path.sr_path.add()
                  srv6_segment.segment = segment
              response = srv6_stub.Create(path_request)
              print response
              channel.close()


  def delete(self, destination, device, segments):
      # Get the reference of the stub
      srv6_stub,channel = self.get_grpc_session("localhost", 12345, SECURE)
      # Create message request
      path_request = srv6_explicit_path_pb2.SRv6EPRequest()
      # Create a new path
      path = path_request.path.add()
      # Set destination, device, encapmode
      path.destination = destination
      path.device = device
      path.encapmode = "inline"
      for segment in segments:
          # Create a new segment
          srv6_segment = path.sr_path.add()
          srv6_segment.segment = segment
      # Remove
      response = srv6_stub.Remove(path_request)
      print response
      # Let's close the session
      channel.close()


  def deleteFromJson(self, data):
      json_data = json.loads(data)
      # Iterate over the array and delete one by one all the paths
      for data in json_data:
          # Each time we create a new session
          srv6_stub,channel = self.get_grpc_session("localhost", 12345, SECURE)
          path_request = srv6_explicit_path_pb2.SRv6EPRequest()
          for jpath in data['paths']:
              path = path_request.path.add()
              # Set destination, device, encapmode
              path.destination = jpath['destination']
              path.device = jpath['device']
              path.encapmode = jpath['encapmode']
              for segment in jpath['segments']:
                  # Create a new segment
                  srv6_segment = path.sr_path.add()
                  srv6_segment.segment = segment
              # Remove
              response = srv6_stub.Remove(path_request)
              print response
              # Let's close the session
              channel.close()


class SRv6VPNHandler:

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(CERTIFICATE) as f:
                certificate = f.read()
            # Then create the SSL credentials and establish the channel
            grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
            channel = grpc.secure_channel("ipv6:[%s]:%s" %(ip_address, port), grpc_client_credentials)
        else:
            channel = grpc.insecure_channel("ipv6:[%s]:%s" %(ip_address, port))
        return srv6_vpn_pb2_grpc.SRv6VPNHandlerStub(channel), channel

    def get_vpns(self, ip_address):
        # Create the request
        request = srv6_vpn_pb2.EmptyRequest()
        try:
            # Get the reference of the stub
            srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
            # Get VPNs
            response = srv6_stub.GetVPNs(request)
            # Parse response and retrieve VPNs information
            vpns = dict()
            for vpn in response.vpns:
              vpn_name = vpn.name
              table_id = vpn.table_id
              sid = vpn.sid
              #interfaces = vpn.interfaces
              interfaces = list()
              for intf in vpn.interfaces:
                interfaces.append(intf)
              vpns[vpn_name] = {
                "table_id": table_id,
                "sid": sid,
                "interfaces": interfaces
              }
            # Let's close the session
            channel.close()
            return vpns
        except grpc.RpcError as e:
          status_code = e.code()
          if status_code.value[0] == 14:  # Unavailable
              print "Cannot establish a connection with gRPC server %s-%s" % (ip_address, 12345)
              print "%s: %s" % (status_code.name, e.details())
              return None


    def create_vpn(self, ip_address, name, table_id, sid):
        # Create the request
        request = srv6_vpn_pb2.CreateVPNRequest()
        request.name = name
        request.table_id = str(table_id)
        request.sid = str(sid)
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Create the VPN
            response = srv6_stub.CreateVPN(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"


    def add_local_interface_to_vpn(self, ip_address, name, interface):
        # Create the request
        request = srv6_vpn_pb2.AddLocalInterfaceToVPNRequest()
        request.name = name
        request.interface = interface
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Add local interface to the VPN
            response = srv6_stub.AddLocalInterfaceToVPN(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"


    def remove_local_interface_from_vpn(self, ip_address, interface):
        # Create the request
        request = srv6_vpn_pb2.RemoveLocalInterfaceFromVPNRequest()
        request.interface = interface
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Remove local interface from the VPN
            response = srv6_stub.RemoveLocalInterfaceFromVPN(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"


    def add_remote_interface_to_vpn(self, ip_address, interface, table_id, sid):
        # Create the request
        request = srv6_vpn_pb2.AddRemoteInterfaceToVPNRequest()
        request.interface = interface
        request.table_id = str(table_id)
        request.sid = str(sid)
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Add remote interface to the VPN
            response = srv6_stub.AddRemoteInterfaceToVPN(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"


    def remove_remote_interface_from_vpn(self, ip_address, interface, table_id):
        # Create the request
        request = srv6_vpn_pb2.RemoveRemoteInterfaceFromVPNRequest()
        request.interface = interface
        request.table_id = str(table_id)
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Remote remote interface to the VPN
            response = srv6_stub.RemoveRemoteInterfaceFromVPN(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"


    def remove_vpn(self, ip_address, name, table_id, sid):
        # Create the request
        request = srv6_vpn_pb2.RemoveVPNRequest()
        request.name = name
        request.table_id = str(table_id)
        request.sid = str(sid)
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Remove the VPN
            response = srv6_stub.RemoveVPN(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"


    def flush_vpns(self, ip_address):
        # Create the request
        request = srv6_vpn_pb2.EmptyRequest()
        # Get the reference of the stub
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        try:
            # Remove the VPNs
            response = srv6_stub.FlushVPNs(request)
        except grpc.RpcError as e:
            print e.details()
            return False
        # Let's close the session
        channel.close()
        return response.message == "OK"

    def subscribe_netlink_notifications(self, ip_address):
        request = srv6_vpn_pb2.EmptyRequest()
        srv6_stub,channel = self.get_grpc_session(ip_address, 12345, SECURE)
        for response in srv6_stub.SubscribeNetlinkNotifications(request):
            print response


# Test features
if __name__ == "__main__":
    # Test Netlink messages
    srv6VPNHandler = SRv6VPNHandler()
    #srv6VPNHandler.subscribe_netlink_notifications(r)
    routers = ["2000::1", "2000::2", "2000::3"]
    thread_pool = []
    for router in routers:
        thread = Thread(target = srv6VPNHandler.subscribe_netlink_notifications, args = (router, ))
        thread.start()
        thread_pool.append(thread)
    for thread in thread_pool:
        thread.join()

    '''
    srv6VPNHandler = SRv6VPNHandler()
    srv6VPNHandler.createVPN("2000::1", "vpn_a", "2", "1111::")
    srv6VPNHandler.addLocalInterfaceToVPN("2000::1", "vpn_a", ["ads1-eth1", "ads1-eth2"])
    srv6VPNHandler.addRemoteInterfaceToVPN("2000::1", ["fdf0:0:0:4::/64"], "2", "fdff::2", "1111::")
    srv6VPNHandler.removeLocalInterfaceFromVPN("2000::1", ["ads1-eth1", "ads1-eth2"])
    srv6VPNHandler.removeRemoteInterfaceFromVPN("2000::1", ["fdf0:0:0:4::/64"], "2")
    srv6VPNHandler.removeVPN("2000::1", "vpn_a", "2", "1111::")
    '''


    '''
    srv6ExplicitPathHandler = SRv6ExplicitPathHandler()
    srv6ExplicitPathHandler.add("1111:4::2/128", "eth0", ["1111:3::2"])
    srv6ExplicitPathHandler.add("2222:4::2/128", "eth0", ["2222:3::2"])
    srv6ExplicitPathHandler.add("3333:4::2/128", "eth0", ["3333:3::2", "3333:2::2", "3333:1::2"])

    # Delete all the routes created before
    data = """
    [
      {
        "paths": [
          {
            "device": "eth0",
            "destination": "1111:4::2/128",
            "encapmode": "inline",
            "segments": [
              "1111:3::2"
            ]
          }
        ]
      },
      {
        "paths": [
          {
            "device": "eth0",
            "destination": "2222:4::2/128",
            "encapmode": "inline",
            "segments": [
              "2222:3::2"
            ]
          }
        ]
      },
      {
        "paths": [
          {
            "device": "eth0",
            "destination": "3333:4::2/128",
            "encapmode": "encap",
            "segments": [
              "3333:3::2",
              "3333:2::2",
              "3333:1::2"
            ]
          }
        ]
      }
    ]
    """

    srv6ExplicitPathHandler.deleteFromJson(data)
    '''