#!/usr/bin/python


# General imports
import grpc
import json
import sys
import os
from socket import AF_INET
from threading import Thread


# Define wheter to use SSL or not
SECURE = False
# SSL cerificate for server validation
CERTIFICATE = 'cert_client.pem'
# Folders
CONTROL_PLANE_FOLDER = "/home/user/repos/srv6-sdn-control-plane/"
PROTO_FOLDER = "/home/user/repos/srv6-sdn-proto/"


if CONTROL_PLANE_FOLDER == '':
    print('Error: Set CONTROL_PLANE_FOLDER variable '
          'in sb_grpc_client.py')
    sys.exit(-2)
if not os.path.exists(CONTROL_PLANE_FOLDER):
    print('Error: CONTROL_PLANE_FOLDER variable in sb_grpc_client.py '
          'points to a non existing folder\n')
    sys.exit(-2)
# Add path of proto files
sys.path.append(PROTO_FOLDER)
# SRv6 dependencies
import srv6_manager_pb2_grpc
import srv6_manager_pb2
import network_events_listener_pb2
import network_events_listener_pb2_grpc
import empty_req_pb2
import empty_req_pb2_grpc

class SRv6Manager:

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(CERTIFICATE) as f:
                certificate = f.read()
            # Then create the SSL credentials and establish the channel
            grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
            channel = grpc.secure_channel("ipv6:[%s]:%s" % (ip_address, port),
                                          grpc_client_credentials)
        else:
            #channel = grpc.insecure_channel("ipv6:[%s]:%s"
            #                                % (ip_address, port))
            channel = grpc.insecure_channel("ipv4:%s:%s"
                                            % (ip_address, port))
        return (srv6_manager_pb2_grpc
                .SRv6ManagerStub(channel), channel)

    # CRUD SRv6 Explicit Path

    def createSRv6ExplicitPath(self, router, destination,
                               device, segments, encapmode="encap", table=-1):
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(router, 12345, SECURE)
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.SRv6ExplicitPath
        # Create a new SRv6 explicit path request
        path_request = srv6_request.srv6_ep_request
        # Create a new path
        path = path_request.paths.add()
        # Set destination, device, encapmode, table and segments
        path.destination = destination
        path.device = device
        path.encapmode = encapmode
        path.table = table
        for segment in segments:
            # Create a new segment
            srv6_segment = path.sr_path.add()
            srv6_segment.segment = segment
        # Add the SRv6 path
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def createSRv6ExplicitPathFromJson(self, router, data):
        json_data = json.loads(data)
        # Iterate over the array and delete one by one all the paths
        for data in json_data:
            # Each time we create a new session
            srv6_stub, channel = self.get_grpc_session(router,
                                                       12345, SECURE)
            # Create message request
            srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
            # Set the type of the carried entity
            srv6_request.entity_type = srv6_manager_pb2.SRv6ExplicitPath
            # Create a new SRv6 explicit path request
            path_request = srv6_request.srv6_ep_request
            # Process JSON file
            for jpath in data['paths']:
                # Create a new path
                path = path_request.paths.add()
                # Set destination, device, encapmode,
                # table and segments
                path.destination = jpath['destination']
                path.device = jpath['device']
                path.encapmode = jpath['encapmode']
                for segment in jpath['segments']:
                    srv6_segment = path.sr_path.add()
                    srv6_segment.segment = segment
                # Add the SRv6 path
                response = srv6_stub.Create(srv6_request)
                print response
                # Let's close the session
                channel.close()
        # Create the response
        return response.message

    def getSRv6ExplicitPath(self, router, destination,
                            device, segments=[],
                            encapmode="encap", table=-1):
        print 'Not yet implemented'

    def updateSRv6ExplicitPath(self, router, destination,
                               device, segments=[],
                               encapmode="encap", table=-1):
        print 'Not yet implemented'

    def removeSRv6ExplicitPath(self, router, destination,
                               device, segments=[],
                               encapmode="encap", table=-1):
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(router, 12345, SECURE)
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.SRv6ExplicitPath
        # Create a new SRv6 explicit path request
        path_request = srv6_request.srv6_ep_request
        # Create a new path
        path = path_request.paths.add()
        # Set destination, device, encapmode, table and segments
        path.destination = destination
        path.device = device
        path.encapmode = encapmode
        path.table = table
        for segment in segments:
            # Create a new segment
            srv6_segment = path.sr_path.add()
            srv6_segment.segment = segment
        # Remove the SRv6 path
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def removeSRv6ExplicitPathFromJson(self, router, data):
        json_data = json.loads(data)
        # Iterate over the array and delete one by one all the paths
        for data in json_data:
            # Each time we create a new session
            srv6_stub, channel = self.get_grpc_session(router,
                                                       12345, SECURE)
            # Create message request
            srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
            # Set the type of the carried entity
            srv6_request.entity_type = (srv6_manager_pb2
                                        .SRv6ExplicitPath)
            # Create a new SRv6 explicit path request
            path_request = srv6_request.srv6_ep_request
            for jpath in data['paths']:
                path = path_request.paths.add()
                # Set destination, device, encapmode
                path.destination = jpath['destination']
                path.device = jpath['device']
                path.encapmode = jpath['encapmode']
                for segment in jpath['segments']:
                    # Create a new segment
                    srv6_segment = path.sr_path.add()
                    srv6_segment.segment = segment
                # Remove the SRv6 path
                response = srv6_stub.Remove(srv6_request)
                print response
                # Let's close the session
                channel.close()
        # Create the response
        return response.message

    # CRUD SRv6 Local Processing Function

    def createSRv6LocalProcessingFunction(self, router, segment,
                                          action, device, localsid_table,
                                          nexthop="", table=-1,
                                          interface="", segments=[]):
        # Get the reference of the stub
        srv6_stub, channel = self.get_grpc_session(router, 12345, SECURE)
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = (srv6_manager_pb2
                                    .SRv6LocalProcessingFunction)
        # Create a new SRv6 Lccal Processing Function request
        function_request = srv6_request.srv6_lpf_request
        # Create a new local processing function
        function = function_request.functions.add()
        # Set segment, action, device, locasid table and other params
        function.segment = segment
        function.action = action
        function.nexthop = nexthop
        function.table = table
        function.interface = interface
        function.device = device
        function.localsid_table = localsid_table
        for segment in segments:
            # Create a new segment
            srv6_segment = function.segs.add()
            srv6_segment.segment = segment
        # Create the SRv6 local processing function
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def getSRv6LocalProcessingFunction(self, router, segment,
                                       action, device, localsid_table,
                                       nexthop="", table=-1,
                                       interface="", segments=[]):
        print 'Not yet supported'

    def updateSRv6LocalProcessingFunction(self, router, segment,
                                          action, device, localsid_table,
                                          nexthop="", table=-1,
                                          interface="", segments=[]):
        print 'Not yet supported'

    def removeSRv6LocalProcessingFunction(self, router, segment,
                                          localsid_table, action="",
                                          nexthop="", table=-1,
                                          interface="", segments=[],
                                          device=""):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = (srv6_manager_pb2
                                    .SRv6LocalProcessingFunction)
        # Create a new SRv6 Lccal Processing Function request
        function_request = srv6_request.srv6_lpf_request
        # Create a new local processing function
        function = function_request.functions.add()
        # Set segment, action, device, locasid table and other params
        function.segment = segment
        function.action = action
        function.nexthop = nexthop
        function.table = table
        function.interface = interface
        function.device = device
        function.localsid_table = localsid_table
        for segment in segments:
            # Create a new segment
            srv6_segment = function.segs.add()
            srv6_segment.segment = segment
        # Remove
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    # CRUD VRF Device

    def createVRFDevice(self, router, name, table, interfaces=[]):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.VRFDevice
        # Create a new VRF device request
        vrf_device_request = srv6_request.vrf_device_request
        # Create a new VRF device
        device = vrf_device_request.device.add()
        # Set name, table
        device.name = name
        device.table = table
        for ifname in interfaces:
            # Create a new interface
            interface = device.interfaces.add()
            # Set name
            interface.name = ifname
        # Create VRF device
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def getVRFDevice(self, router, name, table, interfaces=[]):
        print 'Not yet implemented'

    def updateVRFDevice(self, router, name, table=-1, interfaces=[]):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.VRFDevice
        # Create a new VRF device request
        vrf_device_request = srv6_request.vrf_device_request
        # Create a new VRF device
        device = vrf_device_request.device.add()
        # Set name, table
        device.name = name
        if table != -1:
            device.table = table
        for ifname in interfaces:
            # Create a new interface
            interface = device.interfaces.add()
            # Set name
            interface.name = ifname
        # Create VRF device
        response = srv6_stub.Update(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def removeVRFDevice(self, router, name):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.VRFDevice
        # Create a new VRF device request
        vrf_device_request = srv6_request.vrf_device_request
        # Create a new VRF device
        device = vrf_device_request.device.add()
        # Set name
        device.name = name
        # Remove
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    # CRUD Interface

    def createInterface(self, router, ifindex, name, macaddr,
                        ipaddrs, state, ospf_adv):
        print 'Not yet implemented'

    def getInterface(self, router, interfaces=[]):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.Interface
        # Create a new interface request
        interface_request = srv6_request.interface_request
        # Add interfaces
        for interface in interfaces:
            intf = interface_request.interfaces.add()
            intf.name = interface.name
        # Get interfaces
        response = srv6_stub.Get(srv6_request)
        # Parse response and retrieve interfaces information
        interfaces = dict()
        for interface in response.interfaces:
            ifindex = int(interface.index)
            ifname = interface.name
            macaddr = interface.macaddr
            ips = interface.ipaddrs
            ipaddrs = list()
            for ip in ips:
                ipaddrs.append(ip)
            state = interface.state
            interfaces[ifindex] = {
                "ifname": ifname,
                "macaddr": macaddr,
                "ipaddr": ipaddrs,
                "state": state
            }
        # Let's close the session
        channel.close()
        return interfaces

    def updateInterface(self, router, ifindex, name=None, macaddr=None,
                        ipaddrs=None, state=None, ospf_adv=None):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.Interface
        # Create a new interface request
        interface_request = srv6_request.interface_request
        # Create a new interface
        intf = interface_request.interfaces.add()
        # Set name, MAC address and other params
        intf.ifindex = ifindex
        if name is not None:
            intf.name = name
        if macaddr is not None:
            intf.macaddr = macaddr
        if ipaddrs is not None:
            intf.ipaddrs = ipaddrs
        if state is not None:
            intf.state = state
        if ospf_adv is not None:
            intf.ospf_adv = ospf_adv
        # Create interface
        response = srv6_stub.Update(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def removeInterface(self, router, ifindex, name, macaddr,
                        ipaddrs, state, ospf_adv):
        print 'Not yet implemented'

    # CRUD IP rule

    def createIPRule(self, router, family, table=-1,
                     priority=-1, action="", scope=-1,
                     destination="", dst_len=-1, source="",
                     src_len=-1, in_interface="", out_interface=""):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPRule
        # Create a new interface request
        rule_request = srv6_request.iprule_request
        # Create a new rule
        rule = rule_request.rules.add()
        # Set family and optional params
        rule.family = family
        rule.table = table
        rule.priority = priority
        rule.action = action
        rule.scope = scope
        rule.destination = destination
        rule.dst_len = dst_len
        rule.source = source
        rule.src_len = src_len
        rule.in_interface = in_interface
        rule.out_interface = out_interface
        # Create IP rule
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def getIPRule(self, router, family, table=-1,
                  priority=-1, action="", scope=-1,
                  destination="", dst_len=-1, source="",
                  src_len=-1, in_interface="", out_interface=""):
        print 'Not yet implemented'

    def updateIPRule(self, router, family, table=-1,
                     priority=-1, action="", scope=-1,
                     destination="", dst_len=-1, source="",
                     src_len=-1, in_interface="", out_interface=""):
        print 'Not yet implemented'

    def removeIPRule(self, router, family, table=-1,
                     priority=-1, action="", scope=-1,
                     destination="", dst_len=-1, source="",
                     src_len=-1, in_interface="", out_interface=""):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPRule
        # Create a new interface request
        rule_request = srv6_request.iprule_request
        # Create a new rule
        rule = rule_request.rules.add()
        # Set family and optional params
        rule.family = family
        rule.table = table
        rule.priority = priority
        rule.action = action
        rule.scope = scope
        rule.destination = destination
        rule.dst_len = dst_len
        rule.source = source
        rule.src_len = src_len
        rule.in_interface = in_interface
        rule.out_interface = out_interface
        # Remove IP rule
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    # CRUD IP Route

    def createIPRoute(self, router, family=-1, tos="", type="",
                      table=-1, proto=-1, destination="", dst_len=-1,
                      scope=-1, preferred_source="", src_len=-1,
                      in_interface="", out_interface="", gateway=""):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPRoute
        # Create a new interface request
        route_request = srv6_request.iproute_request
        # Create a new route
        route = route_request.route.add()
        # Set params
        route.family = family
        route.tos = tos
        route.type = type
        route.table = table
        route.scope = scope
        route.proto = proto
        route.destination = destination
        route.dst_len = dst_len
        route.preferred_source = preferred_source
        route.src_len = src_len
        route.in_interface = in_interface
        route.out_interface = out_interface
        route.gateway = gateway
        # Create IP Route
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def getIPRoute(self, router, family=-1, tos="", type="",
                   table=-1, proto=-1, destination="", dst_len=-1,
                   scope=-1, preferred_source="", src_len=-1,
                   in_interface="", out_interface="", gateway=""):
        print 'Not yet implemented'

    def updateIPRoute(self, router, family=-1, tos="", type="",
                      table=-1, proto=-1, destination="", dst_len=-1,
                      scope=-1, preferred_source="", src_len=-1,
                      in_interface="", out_interface="", gateway=""):
        print 'Not yet implemented'

    def removeIPRoute(self, router, family=-1, tos="", type="",
                      table=-1, proto=-1, destination="", dst_len=-1,
                      scope=-1, preferred_source="", src_len=-1,
                      in_interface="", out_interface="", gateway=""):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPRoute
        # Create a new interface request
        route_request = srv6_request.iproute_request
        # Create a new route
        route = route_request.route.add()
        # Set params
        route.family = family
        route.tos = tos
        route.type = type
        route.table = table
        route.proto = proto
        route.scope = scope
        route.destination = destination
        route.dst_len = dst_len
        route.preferred_source = preferred_source
        route.src_len = src_len
        route.in_interface = in_interface
        route.out_interface = out_interface
        route.gateway = gateway
        # Remove IP Route
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    # CRUD IP Address

    def createIPAddr(self, router,
                     ip_addr, device, net, family=AF_INET):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPAddr
        # Create a new interface request
        addr_request = srv6_request.ipaddr_request
        # Create a new route
        addr = addr_request.addr.add()
        # Set address, device, family
        addr.ip_addr = ip_addr
        addr.device = device
        addr.family = family
        addr.net = net
        # Create IP Address
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def getIPAddr(self, router,
                  ip_addr, device, net, family=AF_INET):
        print 'Not yet implemented'

    def updateIPAddr(self, router,
                     ip_addr, device, net, family=AF_INET):
        print 'Not yet implemented'

    def removeIPAddr(self, router, ip_addr, device, family=-1):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPAddr
        # Create a new interface request
        addr_request = srv6_request.ipaddr_request
        # Create a new route
        addr = addr_request.addrs.add()
        # Set address, device, family
        addr.ip_addr = ip_addr
        addr.device = device
        addr.family = family
        # Remove IP Address
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def removeManyIPAddr(self, router, addrs, nets, device, family=-1):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPAddr
        # Create a new interface request
        addr_request = srv6_request.ipaddr_request
        for (ip_addr, net) in zip(addrs, nets):
            # Create a new route
            addr = addr_request.addrs.add()
            # Set address, device, family
            addr.ip_addr = ip_addr
            addr.device = device
            addr.family = family
            addr.net = net
        # Remove IP Address
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def createVxLAN(self, router, ifname, vxlan_link, vxlan_id):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPVxlan
        # Create a new vxlan request
        ipvxlan_request = srv6_request.ipvxlan_request
        # Create a new vxlan 
        vxlan = ipvxlan_request.vxlan.add()
        # Set params
        vxlan.ifname = ifname
        vxlan.vxlan_link = vxlan_link
        vxlan.vxlan_id = vxlan_id
        # add vxlan 
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def delVxLAN(self, router, ifname):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPVxlan
        # Create a new vxlan request
        ipvxlan_request = srv6_request.ipvxlan_request
        
        vxlan = ipvxlan_request.vxlan.add()
        # Set params
        vxlan.ifname = ifname
        # remove vxlan 
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def addfdbentries(self, router, ifindex, dst):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPfdbentries
        # Create a new fdb entries request
        fdbentries_request = srv6_request.fdbentries_request
        # Create a new fdb entries  
        fdbentries = fdbentries_request.fdbentries.add()
        # Set params
        fdbentries.ifindex = ifindex
        fdbentries.dst = dst
        # Create fdb entries 
        response = srv6_stub.Create(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message

    def delfdbentries(self, router, ifindex, dst):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        srv6_request = srv6_manager_pb2.SRv6ManagerRequest()
        # Set the type of the carried entity
        srv6_request.entity_type = srv6_manager_pb2.IPfdbentries
        # Create a new fdb entries request
        fdbentries_request = srv6_request.fdbentries_request
      
        fdbentries = fdbentries_request.fdbentries.add()
        # Set params
        fdbentries.ifindex = ifindex
        fdbentries.dst = dst
        # remove fdb entries 
        response = srv6_stub.Remove(srv6_request)
        print response
        # Let's close the session
        channel.close()
        # Create the response
        return response.message


class NetworkEventsListener:

    # Build a grpc stub
    def get_grpc_session(self, ip_address, port, secure):
        # If secure we need to establish a channel with the secure endpoint
        if secure:
            # Open the certificate file
            with open(CERTIFICATE) as f:
                certificate = f.read()
            # Then create the SSL credentials and establish the channel
            grpc_client_credentials = grpc.ssl_channel_credentials(certificate)
            channel = grpc.secure_channel("ipv6:[%s]:%s" % (ip_address, port),
                                          grpc_client_credentials)
        else:
            channel = grpc.insecure_channel("ipv6:[%s]:%s"
                                            % (ip_address, port))
        return (network_events_listener_pb2_grpc
                .NetworkEventsListenerStub(channel), channel)

    def listen(self, router):
        # Get the reference of the stub
        srv6_stub, channel = (self
                              .get_grpc_session(router, 12345, SECURE))
        # Create message request
        request = empty_req_pb2.EmptyRequest()
        # Listen for Netlink notifications
        for event in srv6_stub.Listen(request):
            yield response.nlmsg
        # Let's close the session
        channel.close()


# Test features
if __name__ == "__main__":
    # Test Netlink messages
    srv6_manager = SRv6Manager()
    # Create a thread for each router and subscribe netlink notifications
    #routers = ["2000::1", "2000::2", "2000::3"]
    #thread_pool = []
    #for router in routers:
    #    thread = Thread(target=srv6_manager
    #                    .createNetlinkNotificationsSubscription,
    #                    args=(router, ))
    #    thread.start()
    #    thread_pool.append(thread)
    #for thread in thread_pool:
    #    thread.join()

    # --- tunnel creation test 
    '''srv6_manager.createVxLAN('10.0.14.45', 'vxlan100','ewED1-eth0', 100)
    srv6_manager.addfdbentries('10.0.14.45', 'vxlan100', '10.0.16.49')
    srv6_manager.createVxLAN('10.0.16.49', 'vxlan100','ewED2-eth0', 100)
    srv6_manager.addfdbentries('10.0.16.49', 'vxlan100', '10.0.14.45')
    srv6_manager.createIPAddr('10.0.14.45', '10.100.0.1/24', 'vxlan100', '')
    srv6_manager.createIPAddr('10.0.16.49', '10.100.0.2/24', 'vxlan100', '')
    
    srv6_manager.createVRFDevice('10.0.14.45', 'vrf1', 1, ['vxlan100', 'ewED1-eth1'])
    srv6_manager.createVRFDevice('10.0.16.49', 'vrf1', 1, ['vxlan100', 'ewED2-eth1'])

    srv6_manager.createIPRoute('10.0.14.45', destination='192.168.38.0', dst_len=24, gateway='10.100.0.2', table=1)
    srv6_manager.createIPRoute('10.0.16.49', destination='192.168.32.0', dst_len=24, gateway='10.100.0.1', table=1)
    #---- tunnel cancellation test
    srv6_manager.removeIPRoute('10.0.16.49', destination='192.168.32.0', dst_len=24, table=1)
    srv6_manager.removeVRFDevice('10.0.14.45', 'vrf1')
    srv6_manager.delVxLAN('10.0.14.45', 'vxlan100')
    srv6_manager.delfdbentries('10.0.16.49', 'vxlan100', '10.0.14.45')'''
