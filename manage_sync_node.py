#!/usr/bin/env python2.7
"""Create, modify and delete Sync nodes



[Defaults]


[Main]
; master token password
token_secret=example master token secret

; MySQL Database user's password
dbpass=password goes here

; Ami map
; SvcOps SL 6.3 20140128
ami.us-west-2=ami-6afe9e5a
; SvcOps SL 6.3 20140128
ami.us-east-1=ami-059ea16c

; EC2 keypair name
key_pair_name=20130730-svcops-base-key-dev

; EC2 sync storage server instance type
instance_type=c3.4xlarge

; Sync storage server security groups
security_groups.1=open-everything

"""
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# sudo easy_install https://github.com/mozilla-services/tokenlib/archive/master.zip
# wget https://raw.githubusercontent.com/mozilla-services/mozservices/master/mozsvc/secrets.py
import sys
req_version = (2,7)
cur_version = sys.version_info
if cur_version < req_version:
    print("This tool requires Python 2.7, please upgrade and run this again.")
    sys.exit(1)

import importlib
for module in [('argparse', 'Try running "sudo pip install argparse"'),
               ('tokenlib', 'Try running "sudo easy_install https://github.com/mozilla-services/tokenlib/archive/master.zip"'),
               ('secrets', 'Try fetching the file with "wget https://raw.githubusercontent.com/mozilla-services/mozservices/master/mozsvc/secrets.py"'),
               ('MySQLdb', 'Try running "sudo yum install python-mysqldb"'),
               ('boto.ec2', 'Try running "sudo pip install -U boto"')]:
    try:
        mod = importlib.import_module(module[0], package=None)
    except ImportError:
        print("The module %s doesn't appear to be installed. %s" % module)
        sys.exit(1)
import logging
import os
import re
import yaml

def type_loglevel(level):
    try:
        result = getattr(logging, level.upper())
    except AttributeError:
        raise argparse.ArgumentTypeError("'%s' is not a valid log level. Please use %s" %
                                         (level, 
                                          [x for x in logging._levelNames.keys() 
                                           if isinstance(x, str)]))
    return result


def type_filename(filename):
    if not os.path.exists(filename):
       parser.error("The file %s does not exist"% filename)
    else:
       return filename
   
def collect_arguments():
    defaults = {"tokensecret" : "default master token secret",
                "loglevel" : "INFO"}
    all_regions = [x.name for x in 
                   boto.ec2.connect_to_region('us-east-1').get_all_regions()]
    conf_parser = argparse.ArgumentParser(
        # Turn off help, so we print all options in response to -h
            add_help=False
            )
    conf_parser.add_argument("-c", "--config", required=True, 
                             type=type_filename, metavar="FILE", 
                             help="Specify a YAML configuration file")
    args, remaining_argv = conf_parser.parse_known_args()

    with open(args.config) as f:
        config = yaml.load(f)
    if 'defaults' in config and type(config['defaults']) == dict:
        defaults = config['defaults']
    
    # Don't suppress add_help here so it will handle -h
    parser = argparse.ArgumentParser(
        # Inherit options from config_parser
        parents=[conf_parser],
        # print script description with -h/--help
        description=__doc__,
        # Don't mess with format of description
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.set_defaults(**defaults)
    parser.add_argument('action', choices = ['create', 'modify', 'delete'], 
                       help="Action to perform")
    parser.add_argument('-n', '--nodename', 
                       help="Node name")
    parser.add_argument('-r', '--region', choices = all_regions,
                       help="AWS Region")
    parser.add_argument('--dbserver', 
                       help="Host name of the MySQL token server database")
    parser.add_argument('--dbuser', 
                       help="User name of the MySQL token server database")
    parser.add_argument('--dbname', 
                       help="Database name of the MySQL token server database")
    parser.add_argument('-l', '--loglevel', type=type_loglevel,
                   help='Log level verbosity')
    result = parser.parse_args(remaining_argv)

    config.update(result)
    return config

    def __init__(self, config):
        self.config = config
        if config['action'] == 'create':
            create()

    def get_next_available_node_name(self):
        query = "SELECT node FROM nodes ORDER BY node DESC LIMIT 0,1"
        db = MySQLdb.connect(host=self.config['dbserver'],
                             user=self.config['dbuser'],
                             passwd=self.config['dbpass'],
                             db=self.config['dbname'])
        cur = db.cursor() 
        cur.execute(query)
        result = cur.fetchone() # we should test if 0 rows returned
        # example result "https://sync-3-us-east-1.stage.mozaws.net"
        m = re.match(r"^https://sync-(\d*)-([^\.]*)\.([^\.]*)\.mozaws\.net$", 
                     result[0])
        if m:
            (current_index, region, environment) = m.groups()
        else:
            raise Exception("The newest node, %s, found in the nodes table " +
                "in the %s database doesn't conform to the naming " +
                "convention expected." % (result[0], self.config['dbname']))
        next_index = int(current_index) + 1
        return "https://sync-%s-%s.%s.mozaws.net" % (next_index, self.config['region'], environment)
    
    def get_node_secret(self):
        return secrets.DerivedSecrets(self.config['token_secret']).get(self.name)
    
    def spawn_instance(self):
        conn_ec2 = boto.ec2.connect_to_region(self.config['region'])
        image_id = config['ami_map'][self.config['region']]
        user_data = 'foo'
        existing_security_groups = conn_ec2.get_all_security_groups()
        security_group_ids = [x.id for x in existing_security_groups if x.name in self.config['security_groups']]
        reservation = conn_ec2.run_instances(image_id = image_id,
                                             key_name = self.config['key_pair_name'],
                                             user_data = user_data,
                                             instance_type = self.config['instance_type'],
                                             security_group_ids = security_group_ids
                                             )
        instances = reservation.instances
        if 0 < len(instances) < 2:
            raise Exception("Instance creation returned reservation with %s instances" % len(instances))
        else:
            instance = instances[0]

        conn_cfn = boto.cloudformation.connect_to_region(self.config['region'])
        stack = conn_cfn.create_stack(stack_name='foo',
                                      template_body='foo')
        
        # loop and wait for provisioning of the instance to complete
        
    
    def create(self):
        self.name = self.get_next_available_node_name()
        self.node_secret = self.get_node_secret()
        
        

if __name__=='__main__':
    config = collect_arguments()
    logging.basicConfig(level=config['loglevel'])
    node = SyncNode(config)
    

