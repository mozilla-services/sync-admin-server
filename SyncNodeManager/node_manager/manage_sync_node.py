#!/usr/bin/env python
"""Create, interrogate and manipulate Firefox Sync nodes


"""
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# sudo easy_install https://github.com/mozilla-services/tokenlib/archive/master.zip
# wget https://raw.githubusercontent.com/mozilla-services/mozservices/master/mozsvc/secrets.py
##

import sys

sp_prefix = '/data/server-syncstorage/lib/python2.6/site-packages/'
sys.path.extend([
     '/data/server-syncstorage/lib/python2.6/site-packages',
     sp_prefix + 'Paste-1.7.5.1-py2.6.egg',
     sp_prefix + 'WSGIProxy-0.2.2-py2.6.egg',
     sp_prefix + 'metlog_py-0.10.0-py2.6.egg',
     sp_prefix + 'pyramid-1.5a3-py2.6.egg-info',
     '/data/server-syncstorage/build/lib'])

import os
import logging
import yaml

module_help = {'argparse': 'Try running "sudo install python-argparse"',
               'boto.ec2': 'Try running "sudo pip install -U boto"',
               'syncnode': 'This may be due to a package issue with syncnode'}
try:
    import argparse
    import boto.ec2
    import syncnode
except ImportError, e:
    m = e.args[0].split()[-1]
    print("The module %s doesn't appear to be installed." % m)
    if m in module_help:
        print(module_help[m])
    raise


def type_loglevel(level):
    try:
        result = getattr(logging, level.upper())
    except AttributeError:
        raise argparse.ArgumentTypeError("'%s' is not a valid log level. "
                                         "Please use %s" % (level,
                                         [x for x in logging._levelNames.keys()
                                          if isinstance(x, str)]))
    return result


def type_filename(filename, mode='r'):
    if not os.path.exists(filename):
        msg = "The file %s does not exist" % filename
        raise argparse.ArgumentTypeError(msg)
    else:
        return open(filename, mode)


def collect_arguments():
    defaults = {"loglevel": "INFO"}
    all_regions = [x.name for x in
                   boto.ec2.connect_to_region('us-east-1').get_all_regions()]
    parser_conf = argparse.ArgumentParser(
        # Turn off help, so we print all options in response to -h
            add_help=False
            )
    parser_conf.add_argument("-c", "--config",
                             type=type_filename, metavar="FILE",
                             default='/etc/manage_sync_node.conf',
                             help="Specify a YAML configuration file")
    args, remaining_argv = parser_conf.parse_known_args()
    config = yaml.load(args.config)
    if 'defaults' in config and type(config['defaults']) == dict:
        defaults.update(config['defaults'])

    parser = {}
    # Don't suppress add_help here so it will handle -h
    parser['main'] = argparse.ArgumentParser(
        # Inherit options from config_parser
        parents=[parser_conf],
        # print script description with -h/--help
        description=__doc__,
        # Don't mess with format of description
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser['main'].set_defaults(**defaults)
    parser['main'].add_argument('-r', '--region',
            choices=all_regions,
            help="AWS Region")
    parser['main'].add_argument('-e', '--environment',
            choices=['prod', 'stage', 'dev'],
            help="AWS Region")
    parser['main'].add_argument('--dbserver',
            help="Host name of the MySQL token server database")
    parser['main'].add_argument('--dbuser',
            help="User name of the MySQL token server database")
    parser['main'].add_argument('--dbname',
            help="Database name of the MySQL token server database")
    parser['main'].add_argument('-l', '--loglevel', type=type_loglevel,
            help='Log level verbosity')

    subparsers = parser['main'].add_subparsers(help='sub-command help',
                                               dest='action')
    parser['create'] = subparsers.add_parser('create', help='Create a new '
                                             'Firefox Sync node')
    parser['create'].add_argument('--amiid',
            help="AMI ID to use in the new node")

    # parser['modify'] = subparsers.add_parser('modify', help='create help')

    # parser['delete'] = subparsers.add_parser('delete', help='create help')

    parser['verify'] = subparsers.add_parser('verify', help='Verify the '
                                 'health of an existing Firefox Sync node')
    parser['verify'].add_argument('nodeurl',
            help="URL of the node you would like to verify")

    parser['check'] = subparsers.add_parser('check', help='Check the state of '
                            'a Firefox Sync node in the tokenserver database')
    parser['check'].add_argument('nodeurl',
            help="URL of the node you would like to check")

    parser['setlive'] = subparsers.add_parser('setlive', help='Set a Firefox '
                  'Sync node live by adding it into the tokenserver database')
    parser['setlive'].add_argument('nodeurl',
            help="URL of the node you would like to check")

    result = parser['main'].parse_args(remaining_argv)
    config.update(vars(result))

    if 'amiid' in config and config['amiid'] is None:
        config['amiid'] = config['ami_map'][config['region']]
    return config


def main():
    config = collect_arguments()
    logging.basicConfig(level=config['loglevel'])
    logging.debug(config)
    node = syncnode.SyncNode(config)

if __name__ == '__main__':
    main()
