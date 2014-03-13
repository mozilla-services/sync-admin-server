#!/usr/bin/env python2.6
"""Create, modify and delete Sync nodes


"""
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# sudo easy_install https://github.com/mozilla-services/tokenlib/archive/master.zip
# wget https://raw.githubusercontent.com/mozilla-services/mozservices/master/mozsvc/secrets.py
import sys
req_version = (2,6)
cur_version = sys.version_info
if cur_version < req_version:
    print("This tool requires Python 2.6, please upgrade and run this again.")
    sys.exit(1)

try:
    import importlib
except ImportError:
    print("The module importlib doesn't appear to be installed. Try running \"sudo yum install python-importlib\"")
    sys.exit(1)

import importlib
for module in [('argparse', 'Try running "sudo install python-argparse"'),
               ('tokenlib', 'Try running "sudo easy_install https://github.com/mozilla-services/tokenlib/archive/master.zip"'),
               ('secrets', 'Try fetching the file with "wget https://raw.githubusercontent.com/mozilla-services/mozservices/master/mozsvc/secrets.py"'),
               ('MySQLdb', 'Try running "sudo yum install MySQL-python"'),
               ('boto', 'Try running "sudo pip install -U boto"'),
               ('boto.ec2', 'Try running "sudo pip install -U boto"'),
               ('boto.cloudformation', 'Try running "sudo pip install -U boto"')]:
    try:
        globals()[module[0]] = importlib.import_module(module[0], package=None)
    except ImportError:
        print("The module %s doesn't appear to be installed. %s" % module)
        sys.exit(1)
import logging
import os
import re
import yaml
import time

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
    defaults = {"loglevel" : "INFO"}
    all_regions = [x.name for x in 
                   boto.ec2.connect_to_region('us-east-1').get_all_regions()]
    conf_parser = argparse.ArgumentParser(
        # Turn off help, so we print all options in response to -h
            add_help=False
            )
    conf_parser.add_argument("-c", "--config", 
                             type=type_filename, metavar="FILE", 
                             help="Specify a YAML configuration file")
    args, remaining_argv = conf_parser.parse_known_args()

    if args.config:
        with open(args.config) as f:
            config = yaml.load(f)
        if 'defaults' in config and type(config['defaults']) == dict:
            defaults.update(config['defaults'])
    
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
    parser.add_argument('-e', '--environment', choices = ['prod', 'stage', 'dev'],
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
    config.update(vars(result))
    return config

class SyncNode:
    def __init__(self, config):
        self.config = config
        if config['action'] == 'create':
            self.create()
    
    def wait(self):
        logging.info("Waiting for %s seconds" % self.config['wait_interval'])
        time.sleep(self.config['wait_interval'])

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
        name = "syn-%s-%s" % (next_index, environment)
        url = "https://sync-%s-%s.%s.mozaws.net" % (next_index, self.config['region'], environment)
        return (name, url)
    
    def get_node_secret(self):
        return secrets.DerivedSecrets(self.config['token_secret']).get(self.url)[0]
    
    def spawn_instance(self):
        conn_cfn = boto.cloudformation.connect_to_region(self.config['region'])
        with open(self.config['cloudformation_template_filename']) as f:
            stack_id = conn_cfn.create_stack(stack_name=self.name,
                 template_body=f.read(),
                 parameters=[('Environment', self.config['environment']),
                             ('SyncNodeInstanceType', self.config['instance_type']),
                             ('ProvisioningVersion', 'latest'),
                             ('NodeSecret', self.node_secret)])

        logging.info("Node %s being created" % self.name)

        # We'll loop here to wait for the stack to finish. A better way to do
        # this would be to have CloudFormation publish events to SNS, then
        # subscribe an https endpoint to the SNS topic. That endpoint would
        # be hosted on the admin server and would kick off the remainder
        # of the tasks after stack creation
        status='CREATE_IN_PROGRESS'
        while status == 'CREATE_IN_PROGRESS':
            stacks = conn_cfn.describe_stacks(stack_name_or_id=stack_id)
            if len(stacks) > 1:
                raise Exception("Describe stacks returned %s stacks" % len(stacks))
            elif len(stacks) < 1:
                logging.debug("Describe stacks returned no stacks")
                self.wait()
            else:
                status = stacks[0].stack_status
                logging.info("Stack state is %s" % status)
                if status == 'CREATE_IN_PROGRESS':
                    self.wait()
        logging.info("Node created with final status %s" % status)
        return status

    def set_node_live(self):
        return True
    
    def create(self):
        self.name, self.url = self.get_next_available_node_name()
        logging.debug("New node name and url are %s and %s" % (self.name, self.url))
        self.node_secret = self.get_node_secret()
        logging.debug("New node secret is %s" % self.node_secret)
        cloudformation_status = self.spawn_instance()
        if cloudformation_status != 'CREATE_COMPLETE':
            logging.error("Attempt to build a sync node failed with CloudFormation result %s" % cloudformation_status)
            sys.exit(1)
        verification_status = self.verify()
        if not verification_status:
            logging.error("Verification of new node %s failed." % self.name)
            sys.exit(1)
        if not self.set_node_live():
            logging.error("Attempt to set node %s live failed." % self.name)
            sys.exit(1)

    def verify(self):
        return True
        
    def modify(self):
        pass
    
    def terminate(self):
        pass

if __name__=='__main__':
    config = collect_arguments()
    logging.basicConfig(level=config['loglevel'])
    logging.debug(config)
    node = SyncNode(config)
    

