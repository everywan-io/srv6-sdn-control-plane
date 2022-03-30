#!/usr/bin/python

# Copyright (C) 2022 Carmine Scarpitta, Stefano Salsano -
# (CNIT and University of Rome "Tor Vergata")
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Server of a Northbound interface based on gRPC protocol
#
# @author Carmine Scarpitta <carmine.scarpitta@uniroma2.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#


"""
This module implements exceptions used by EveryEdgeOS controller.
"""


class BadRequestError(Exception):
    """
    Raised when the request made by the user is invalid (e.g. the user
    provided an invalid argument).
    """


class InternalServerError(Exception):
    """
    Raised when an internal error occurred while attempting to execute an
    operation.
    """
