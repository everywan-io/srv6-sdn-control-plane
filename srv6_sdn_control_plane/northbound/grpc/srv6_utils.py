#!/usr/bin/python

from tunnel import tunnel
from tunnel import register_tunnel
from tunnel import unregister_tunnel

TUNNEL_NAME = 'SRv6'
TUNNEL_NUM = tunnel[TUNNEL_NAME]


# Install a VPN on a specified router
#
# Three steps are required to install a VPN
# 1. Create a rule for local SIDs processing
# 2. Add a route to enforce packet decapsulation
#    and lookup in the VPN table
# 3. Create a VRF and assign it to the VPN
def _install_vpn_on_router(self, routerid, vpn_name):
    logger.debug(
        'Attempting to install the VPN %s on the router %s'
        % (vpn_name, routerid)
    )
    # Get the router address
    router = self.srv6_controller_state.get_router_address(routerid)
    if router is None:
        # Cannot get the router address
        logger.warning('Cannot get the router address')
        return 'Cannot get the router address'
    # If the VPN is already installed on the router,
    # we don't need to create it
    installed = self.srv6_controller_state.is_vpn_installed_on_router(
        vpn_name, routerid
    )
    if installed:
        logger.debug(
            'The VPN is already installed on the router %s'
            % routerid
        )
        return 'OK'
    # First step: create a rule for local SIDs processing
    # This step is just required for the first VPN
    installed_vpns = (self.srv6_controller_state
                      .get_num_vpn_installed_on_router(routerid))
    if installed_vpns == 0:
        # We are installing the first VPN in the router
        #
        # Get SID family for this router
        sid_family = self.srv6_controller_state.get_sid_family(
            routerid
        )
        if sid_family is None:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot get SID family for routerid %s' % routerid
            )
            return 'Cannot get SID family for routerid %s' % routerid
        # Add the rule to steer the SIDs through the local SID table
        response = self.srv6_manager.create_iprule(
            router, self.grpc_client_port, family=AF_INET6,
            table=utils.LOCAL_SID_TABLE, destination=sid_family
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            logger.warning(
                'Cannot create the IP rule for destination %s: %s'
                % (sid_family, response)
            )
            # If the operation has failed, return an error message
            return 'Cannot create the rule for destination %s: %s' \
                % (sid_family, response)
        # Add a blackhole route to drop all unknown active segments
        response = self.srv6_manager.create_iproute(
            router, self.grpc_client_port, family=AF_INET6,
            type='blackhole', table=utils.LOCAL_SID_TABLE
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            logger.warning(
                'Cannot create the blackhole route: %s' % response
            )
            # If the operation has failed, return an error message
            return 'Cannot create the blackhole route: %s' % response
    # Second step is the creation of the decapsulation and lookup route
    tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
    if tableid is None:
        logger.warning('Cannot retrieve VPN table ID')
        return 'Cannot retrieve VPN table ID'
    vpn_type = self.srv6_controller_state.get_vpn_type(vpn_name)
    if vpn_type is None:
        logger.warning('Cannot retrieve VPN type')
        return 'Cannot retrieve VPN type'
    if vpn_type == utils.VPNType.IPv6VPN:
        # For IPv6 VPN we have to perform decap and lookup in IPv6 routing
        # table. This behavior is realized by End.DT6 SRv6 action
        action = 'End.DT6'
    elif vpn_type == utils.VPNType.IPv4VPN:
        # For IPv4 VPN we have to perform decap and lookup in IPv6 routing
        # table. This behavior is realized by End.DT4 SRv6 action
        action = 'End.DT4'
    else:
        logger.warning('Error: Unsupported VPN type: %s' % vpn_type)
        return 'Error: Unsupported VPN type %s' % vpn_type
    # Get an non-loopback interface
    # We use the management interface (which is the first interface)
    # in order to solve an issue of routes getting deleted when the
    # interface is assigned to a VRF
    dev = self.srv6_controller_state.get_first_interface(routerid)
    if dev is None:
        # Cannot get non-loopback interface
        logger.warning('Cannot get non-loopback interface')
        return 'Cannot get non-loopback interface'
    # Get the SID
    logger.debug('Attempting to get a SID for the router')
    sid = self.srv6_controller_state.get_sid(routerid, tableid)
    logger.debug('Received SID %s' % sid)
    # Add the End.DT4 / End.DT6 route
    response = self.srv6_manager.create_srv6_local_processing_function(
        router, self.grpc_client_port, segment=sid, action=action,
        device=dev, localsid_table=utils.LOCAL_SID_TABLE, table=tableid
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        logger.warning(
            'Cannot create the SRv6 Local Processing function: %s'
            % response
        )
        # The operation has failed, return an error message
        return 'Cannot create the SRv6 Local Processing function: %s' \
            % response
    # Third step is the creation of the VRF assigned to the VPN
    response = self.srv6_manager.create_vrf_device(
        router, self.grpc_client_port, name=vpn_name, table=tableid
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        logger.warning(
            'Cannot create the VRF %s: %s' % (vpn_name, response)
        )
        # If the operation has failed, return an error message
        return 'Cannot create the VRF %s: %s' % (vpn_name, response)
    # Add all the remote destinations to the VPN
    interfaces = self.srv6_controller_state.get_vpn_interfaces(
        vpn_name
    )
    if interfaces is not None:
        for intf in interfaces:
            if intf.routerid == routerid:
                print('Bug in _assign_interface_to_vpn(): attempt to add a'
                      ' local interface to a not-already-in-router VPN')
                exit(-1)
            # Get the SID
            sid = self.srv6_controller_state.get_sid(
                intf.routerid, tableid
            )
            # Add remote interfacace to the VPN
            response = self._assign_remote_interface_to_vpn(
                routerid, intf.vpn_prefix, tableid, sid
            )
            if response != 'OK':
                logger.warning(
                    'Cannot add remote interface to the VPN: %s'
                    % (response)
                )
                # If the operation has failed, return an error message
                return response
    # The VPN has been installed on the router
    #
    # Update data structures
    logger.debug('Updating controller state')
    succ = self.srv6_controller_state.add_router_to_vpn(routerid, vpn_name)
    if not succ:
        logger.warning('Cannot add the router to the VPN')
        return 'Cannot add the router to the VPN'
    # Success
    logger.debug('The VPN has been successfully installed on the router')
    return 'OK'

# Remove a router from a VPN
#
# Three steps are required to install a VPN
# 1. Remove the decap and lookup route
# 2. Remove the VRF associated to the VPN
# 3. Remove the IPv6/IPv4 routes associated to the VPN
# 4. If there are no more VPNs installed on the router,
#    we can safely remove the local SIDs processing rule
def _remove_vpn_from_router(self, routerid, vpn_name, sid, tableid):
    # Get the router address
    router = self.srv6_controller_state.get_router_address(routerid)
    if router is None:
        # Cannot get the router address
        logger.warning('Cannot get the router address')
        return 'Cannot get the router address'
    # If the VPN is not installed on the router we don't need to remove it
    installed = self.srv6_controller_state.is_vpn_installed_on_router(
        vpn_name, routerid
    )
    if not installed:
        logger.debug(
            'The VPN is not installed on the router %s' % routerid
        )
        return 'OK'
    # Remove the decap and lookup function (i.e. the End.DT4 or End.DT6
    # route)
    response = self.srv6_manager.remove_srv6_local_processing_function(
        router, self.grpc_client_port, segment=sid,
        localsid_table=utils.LOCAL_SID_TABLE
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning('Cannot remove seg6local route: %s' % response)
        return 'Cannot remove seg6local route: %s' % response
    # Delete the VRF assigned to the VPN
    response = self.srv6_manager.remove_vrf_device(
        router, self.grpc_client_port, vpn_name
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning(
            'Cannot remove the VRF %s from the router %s: %s'
            % (vpn_name, router, response)
        )
        return 'Cannot remove the VRF %s from the router %s' \
            % (vpn_name, router)
    # Delete all remaining IPv6 routes associated to the VPN
    response = self.srv6_manager.remove_iproute(
        router, self.grpc_client_port, family=AF_INET6, table=tableid
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning('Cannot remove the IPv6 route: %s' % response)
        return 'Cannot remove the IPv6 route: %s' % response
    # Delete all remaining IPv4 routes associated to the VPN
    response = self.srv6_manager.remove_iproute(
        router, self.grpc_client_port, family=AF_INET, table=tableid
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning('Cannot remove IPv4 routes: %s' % response)
        return 'Cannot remove IPv4 routes: %s' % response
    # Remove the VPN from the controller state
    if not self.srv6_controller_state.remove_vpn_from_router(vpn_name, routerid):
        # If the operation has failed, return an error message
        logger.warning('Cannot remove the VPN from the controller state')
        return 'Cannot remove the VPN from the controller state'
    # If no more VPNs are installed on the router,
    # we can delete the rule for local SIDs
    if self.srv6_controller_state.get_num_vpn_installed_on_router(routerid) == 0:
        # Get SID family for this router
        sid_family = self.srv6_controller_state.get_sid_family(routerid)
        if sid_family is None:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot get SID family for routerid %s' % routerid
            )
            return 'Cannot get SID family for routerid %s' % routerid
        # Remove rule for SIDs
        response = self.srv6_manager.remove_iprule(
            router, self.grpc_client_port, family=AF_INET6, table=utils.LOCAL_SID_TABLE,
            destination=sid_family
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the localSID rule: %s' % response
            )
            return 'Cannot remove the localSID rule: %s' % response
        # Remove blackhole route
        response = self.srv6_manager.remove_iproute(
            router, self.grpc_client_port, family=AF_INET6, type='blackhole',
            table=utils.LOCAL_SID_TABLE
        )
        if response != status_codes_pb2.STATUS_SUCCESS:
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the blackhole rule: %s' % response
            )
            return 'Cannot remove the blackhole rule: %s' % response
    # Success
    logger.debug('Successfully removed the VPN from the router')
    return 'OK'

# Associate a router interface to a VPN
#
# 1. Take the router owning the interface; if the VPN is not yet installed
#    on it, we need to install the VPN and assign to it all the interface
#    already belonging to the VPN before we can add the new interfac
# 2. Iterate on the routers on which the VPN is installed and add the new
#    interface to the VPN
def _assign_interface_to_vpn(self, vpn_name, interface):
    logger.debug(
        'Attempting to associate the interface %s to the '
        'VPN %s' % (interface.interface_name, vpn_name)
    )
    # Get table ID
    tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
    if tableid is None:
        logger.warning('Cannot get table ID for the VPN %s' % vpn_name)
        return('Cannot get table ID for the VPN %s' % vpn_name)
    # Get the SID
    logger.debug('Attempting to get a SID for the router')
    sid = self.srv6_controller_state.get_sid(interface.routerid, tableid)
    logger.debug('Received SID %s' % sid)
    # Extract params from the VPN
    vpn_type = self.srv6_controller_state.get_vpn_type(vpn_name)
    if vpn_type is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get VPN type for the VPN %s' % vpn_name)
        return 'Cannot get VPN type the VPN %s' % vpn_name
    # Extract params from the interface
    routerid = interface.routerid
    interface_name = interface.interface_name
    interface_ip = interface.interface_ip
    vpn_prefix = interface.vpn_prefix
    # Set the address family depending on the VPN type
    if vpn_type == utils.VPNType.IPv6VPN:
        family = AF_INET6
    elif vpn_type == utils.VPNType.IPv4VPN:
        family = AF_INET
    else:
        logger.warning('Unsupported VPN type: %s' % vpn_type)
        return 'Unsupported VPN type: %s' % vpn_type
    # Iterate on the routers on which the VPN is already installed
    # and assign the interface to the VPN
    # The interface can be local or remote
    for r in self.srv6_controller_state.get_routers_in_vpn(vpn_name):
        # Assign the interface to the VPN
        if r == routerid:
            # The interface is local to the router
            logger.debug(
                'Attempting to add the local interface %s to the VPN %s'
                % (interface_name, vpn_name)
            )
            response = self._assign_local_interface_to_vpn(
                r, vpn_name, interface_name, interface_ip,
                vpn_prefix, family
            )
            if response != 'OK':
                logger.warning(
                    'Cannot add the local interface to the VPN: %s'
                    % response
                )
                # The operation has failed, return an error message
                return response
        else:
            logger.debug(
                'Attempting to add the remote interface %s to the VPN %s'
                % (interface_name, vpn_name)
            )
            # The interface is remote to the router
            response = self._assign_remote_interface_to_vpn(
                r, vpn_prefix, tableid, sid
            )
            if response != 'OK':
                logger.warning(
                    'Cannot add the remote interface to the VPN: %s'
                    % response
                )
                # The operation has failed, return an error message
                return response
    # Add the new interface to the controller state
    logger.debug('Add interface to controller state')
    self.srv6_controller_state.add_interface_to_vpn(
        vpn_name, routerid, interface_name, interface_ip, vpn_prefix
    )
    # Success
    logger.debug('Interface assigned to the VPN successfully')
    return 'OK'

# Remove an interface from a VPN
#
# 1. Iterate on the routers on which the VPN is installed and remove the
#    interface from the VPN
# 2. If the router owning the interface has no more interfaces on the VPN,
#    remove the VPN from the router
def _remove_interface_from_vpn(self, routerid, interface_name, vpn_name):
    logger.debug(
        'Attempting to remove interface %s from the VPN %s'
        % (interface_name, vpn_name)
    )
    # Extract params from the VPN
    tableid = self.srv6_controller_state.get_vpn_tableid(vpn_name)
    if tableid is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get table ID for the VPN %s' % vpn_name)
        return 'Cannot get table ID for the VPN %s' % vpn_name
    # Extract VPN prefix
    vpn_prefix = self.srv6_controller_state.get_vpn_prefix(
        vpn_name, routerid, interface_name
    )
    if vpn_prefix is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get VPN prefix for the VPN %s' % vpn_name)
        return 'Cannot get VPN prefix the VPN %s' % vpn_name
    # Iterate on the routers on which the VPN is installed
    # and remove the interfaces from the VPN
    interfaces = self.srv6_controller_state.get_vpn_interfaces(vpn_name)
    if interfaces is None:
        # If the operation has failed, return an error message
        logger.warning(
            'Cannot get the interfaces associated to the '
            'VPN %s' % vpn_name
        )
        return 'Cannot get the interfaces associated to the VPN %s' \
            % vpn_name
    routers = self.srv6_controller_state.get_routers_in_vpn(vpn_name)
    for r in routers:
        # Remove the interface from the VPN
        if r == routerid:
            # The interface is local to the router
            response = self._remove_local_interface_from_vpn(
                r, vpn_name, interface_name
            )
            if response != 'OK':
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the local interface %s from '
                    'the VPN %s' % (interface_name, vpn_name)
                )
                return response
        else:
            # The interface is remote to the router
            response = self._remove_remote_interface_from_vpn(
                r, vpn_prefix, tableid
            )
            if response != 'OK':
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the remote interface %s from the VPN '
                    '%s' % (vpn_prefix, vpn_name)
                )
                return response
    # Remove the interface from the VPNs dictionary
    response = self.srv6_controller_state.remove_interface_from_vpn(
        routerid, interface_name, vpn_name
    )
    if not response:
        return 'Interface not found %s on router %s' \
                                % (interface_name, routerid)
    if self.srv6_controller_state.get_number_of_interfaces(vpn_name, routerid) == 0:
        # No more interfaces belonging to the VPN in the router,
        # remove remote interfaces from the VPN
        interfaces = self.srv6_controller_state.get_vpn_interfaces(
            vpn_name
        )
        for i in interfaces:    
            print(i.routerid)
            print(i.interface_name)
            print(i.interface_ip)
            print(i.vpn_prefix)
        for intf in interfaces:
            if intf.routerid == routerid:
                # Skip local destinations
                logger.critical('Bug in _remove_interface_from_vpn()')
                exit(-1)
            # Remove the remote interface
            response = self._remove_remote_interface_from_vpn(
                routerid, intf.vpn_prefix, tableid
            )
            if response != 'OK':
                # If the operation has failed, return an error message
                logger.warning(
                    'Cannot remove the remote interface %s from the router'
                    ' %s' % (intf.vpn_prefix, routerid)
                )
                return response
        # Get the SID
        sid = self.srv6_controller_state.get_sid(routerid, tableid)
        if sid is None:
            # If the operation has failed, return an error message
            logger.warning('Cannot get SID for routerid %s' % routerid)
            return 'Cannot get SID for routerid %s' % routerid
        # Remove the VPN from the router
        response = self._remove_vpn_from_router(
            routerid, vpn_name, sid, tableid
        )
        if response != 'OK':
            # If the operation has failed, return an error message
            logger.warning(
                'Cannot remove the VPN %s from the router %s'
                % (vpn_name, routerid)
            )
            return response
    # Success
    logger.debug('Interface removed successfully from the VPN')
    return 'OK'

# Assign a local interface to a VPN
def _assign_local_interface_to_vpn(self, routerid, vpn_name,
                                   interface_name, interface_ip,
                                   vpn_prefix, family):
    logger.debug(
        'Attempting to assign local interface %s to the VPN %s'
        % (interface_name, vpn_name)
    )
    # Get router address
    router = self.srv6_controller_state.get_router_address(routerid)
    if router is None:
        # Cannot get the router address
        logger.warning('Cannot get the router address')
        return 'Cannot get the router address'
    # Remove all IPv4 and IPv6 addresses
    addrs = self.srv6_controller_state.get_interface_ips(
        routerid, interface_name
    )
    if addrs is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get interface addresses')
        return 'Cannot get interface addresses'
    nets = []
    for addr in addrs:
        nets.append(str(IPv6Interface(unicode(addr)).network))
    response = self.srv6_manager.remove_many_ipaddr(
        router, self.grpc_client_port, addrs=addrs, nets=nets,
        device=interface_name, family=AF_UNSPEC
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, report an error message
        logger.warning(
            'Cannot remove the public addresses from the interface'
        )
        return 'Cannot remove the public addresses from the interface'
    # Don't advertise the private customer network
    response = self.srv6_manager.update_interface(
        router, self.grpc_client_port, name=interface_name, ospf_adv=False
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, report an error message
        logger.warning('Cannot disable OSPF advertisements')
        return 'Cannot disable OSPF advertisements'
    # Add IP address to the interface
    response = self.srv6_manager.create_ipaddr(
        router, self.grpc_client_port, ip_addr=interface_ip,
        device=interface_name, net=vpn_prefix, family=family
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, report an error message
        logger.warning(
            'Cannot assign the private VPN IP address to the interface'
        )
        return 'Cannot assign the private VPN IP address to the interface'
    # Get the interfaces assigned to the VPN
    interfaces_in_vpn = self.srv6_controller_state.get_vpn_interface_names(
        vpn_name, routerid
    )
    if interfaces_in_vpn is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get VPN interfaces')
        return 'Cannot get VPN interfaces'
    interfaces_in_vpn.add(interface_name)
    # Add the interface to the VRF
    response = self.srv6_manager.update_vrf_device(
        router, self.grpc_client_port, name=vpn_name,
        interfaces=interfaces_in_vpn
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, report an error message
        logger.warning(
            'Cannot assign the interface to the VRF: %s' % response
        )
        return 'Cannot assign the interface to the VRF: %s' % response
    # Success
    logger.debug('Local interface assigned to VPN successfully')
    return 'OK'

# Assign an local interface to a VPN
def _assign_remote_interface_to_vpn(self, routerid, vpn_prefix, tableid,
                                    sid):
    logger.debug(
        'Attempting to assign remote interface %s to the VPN'
        % vpn_prefix
    )
    # Get router address
    router = self.srv6_controller_state.get_router_address(routerid)
    if router is None:
        # Cannot get the router address
        logger.warning('Cannot get the router address')
        return 'Cannot get the router address'
    # Any non-loopback device
    # We use the management interface (which is the first interface)
    # in order to solve an issue of routes getting deleted when the
    # interface is assigned to a VRF
    dev = self.srv6_controller_state.get_first_interface(routerid)
    if dev is None:
        # Cannot get non-loopback interface
        logger.warning('Cannot get non-loopback interface')
        return 'Cannot get non-loopback interface'
    # Create the SRv6 route
    response = self.srv6_manager.create_srv6_explicit_path(
        router, self.grpc_client_port, destination=vpn_prefix,
        table=tableid, device=dev, segments=[sid], encapmode='encap'
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, report an error message
        logger.warning('Cannot create SRv6 Explicit Path: %s' % response)
        return 'Cannot create SRv6 Explicit Path: %s' % response
    # Success
    logger.debug('Remote interface assigned to VPN successfully')
    return 'OK'

# Remove a local interface from a VPN
def _remove_local_interface_from_vpn(self, routerid, vpn_name,
                                     interface_name):
    logger.debug(
        'Attempting to remove local interface %s from the VPN %s'
        % (interface_name, vpn_name)
    )
    # Get router address
    router = self.srv6_controller_state.get_router_address(routerid)
    if router is None:
        # Cannot get the router address
        logger.warning('Cannot get the router address')
        return 'Cannot get the router address'
    # Remove all the IPv4 and IPv6 addresses
    addr = self.srv6_controller_state.get_vpn_interface_ip(
        vpn_name, routerid, interface_name
    )
    if addr is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get interface address')
        return 'Cannot get interface address'
    net = str(IPv6Interface(unicode(addr)).network)
    response = self.srv6_manager.remove_ipaddr(
        router, self.grpc_client_port, ip_addr=addr, net=net,
        device=interface_name, family=AF_UNSPEC
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning(
            'Cannot remove address from the interface: %s' % response
        )
        return 'Cannot remove address from the interface: %s' % response
    # Enable advertisements the private customer network
    response = self.srv6_manager.update_interface(
        router, self.grpc_client_port, name=interface_name, ospf_adv=True
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning('Cannot enable OSPF advertisements: %s' % response)
        return 'Cannot enable OSPF advertisements: %s' % response
    # Get the interfaces assigned to the VPN
    interfaces_in_vpn = self.srv6_controller_state.get_vpn_interface_names(
        vpn_name, routerid
    )
    if interfaces_in_vpn is None:
        # If the operation has failed, return an error message
        logger.warning('Cannot get VPN interfaces')
        return 'Cannot get VPN interfaces'
    interfaces_in_vpn.remove(interface_name)
    # Remove the interface from the VRF
    response = self.srv6_manager.update_vrf_device(
        router, self.grpc_client_port, name=vpn_name,
        interfaces=interfaces_in_vpn
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning('Cannot remove the VRF device: %s' % response)
        return 'Cannot remove the VRF device: %s' % response
    # Success
    logger.debug('Local interface removed successfully')
    return 'OK'

# Remove a remote interface from a VPN
def _remove_remote_interface_from_vpn(self, routerid, vpn_prefix, tableid):
    logger.debug(
        'Attempting to remove remote interface %s from the VPN'
        % vpn_prefix
    )
    # Get router address
    router = self.srv6_controller_state.get_router_address(routerid)
    if router is None:
        # Cannot get the router address
        logger.warning('Cannot get the router address')
        return 'Cannot get the router address'
    # Remove the SRv6 route
    response = self.srv6_manager.remove_srv6_explicit_path(
        router, self.grpc_client_port, destination=vpn_prefix,
        table=tableid
    )
    if response != status_codes_pb2.STATUS_SUCCESS:
        # If the operation has failed, return an error message
        logger.warning('Cannot remove SRv6 Explicit Path: %s' % response)
        return 'Cannot remove SRv6 Explicit Path: %s' % response
    # Success
    logger.debug('Remote inteface removed successfully')
    return 'OK'


TUNNEL_OPS = {
    'install_vpn_on_router': _install_vpn_on_router,
    'remove_vpn_from_router': _remove_vpn_from_router,
    'assign_interface_to_vpn': _assign_interface_to_vpn,
    'remove_interface_from_vpn': _remove_interface_from_vpn
}


def srv6_init():
    register_tunnel(TUNNEL_NAME, TUNNEL_NUM, TUNNEL_OPS)


def srv6_exit():
    unregister_tunnel(TUNNEL_NAME);