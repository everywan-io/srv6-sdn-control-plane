# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Arguments marked as "Required" below must be included for upload to PyPI.
# Fields marked as "Optional" may be commented out.
setup(
    name='srv6-sdn-control-plane',  
    version='1.0-beta',
    description='SRv6 SDN Control Plane',  # Required
    long_description=long_description,
    long_description_content_type='text/markdown',  # Optional (see note above)
    entry_points={'console_scripts': ['srv6_controller = srv6_sdn_control_plane.srv6_controller:_main']},
    url='',  # Optional
    packages=['srv6_sdn_control_plane',
              'srv6_sdn_control_plane.interface_discovery',
              'srv6_sdn_control_plane.topology',
              'srv6_sdn_control_plane.northbound',
              'srv6_sdn_control_plane.northbound.grpc',
              'srv6_sdn_control_plane.southbound',
              'srv6_sdn_control_plane.southbound.grpc',
              'srv6_sdn_control_plane.southbound.netconf',
              'srv6_sdn_control_plane.southbound.rest',
              'srv6_sdn_control_plane.southbound.ssh'],  # Required
    install_requires=[
        'setuptools',
        'grpcio>=1.19.0',
        'grpcio-tools>=1.19.0',
        'ipaddress>=1.0.22',
        'networkx==1.11',
        'protobuf>=3.7.1',
        'pygraphviz>=1.5',
        'six>=1.12.0',
        'sshutil>=1.5.0',
        'filelock>=3.0.12'
    ]
)