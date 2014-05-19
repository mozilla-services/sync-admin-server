#!/usr/bin/env python
"""Create, modify and delete Sync nodes


"""
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
req_version = (2, 6)
cur_version = sys.version_info
if cur_version < req_version:
    print("This tool requires Python 2.6, please upgrade and run this again.")
    sys.exit(1)

sp_prefix = '/data/server-syncstorage/lib/python2.6/site-packages/'
sys.path.extend([
     '/data/server-syncstorage/lib/python2.6/site-packages',
     sp_prefix + 'Paste-1.7.5.1-py2.6.egg',
     sp_prefix + 'WSGIProxy-0.2.2-py2.6.egg',
     sp_prefix + 'metlog_py-0.10.0-py2.6.egg',
     sp_prefix + 'pyramid-1.5a3-py2.6.egg-info',
     '/data/server-syncstorage/build/lib'])

import pyramid
from syncstorage.tests.functional.test_storage import TestStorage
from syncstorage.tests.functional.support import StorageFunctionalTestCase

module_help = {'tokenlib': 'Try running "sudo easy_install '
      'https://github.com/mozilla-services/tokenlib/archive/master.zip"',
   'mozsvc': 'Try running "sudo yum install server-syncstorage"',
   'mozsvc.secrets': 'Try running "sudo yum install '
      'server-syncstorage"',
   'MySQLdb': 'Try running "sudo yum install MySQL-python"',
   'unittest2': 'Try running "sudo yum install python-unittest2"',
   'boto': 'Try running "sudo pip install -U boto"',
   'boto.cloudformation': 'Try running "sudo pip install -U boto"'}
try:
    import tokenlib
    import mozsvc
    import mozsvc.secrets
    import MySQLdb
    import unittest2
    import boto
    import boto.cloudformation
except ImportError, e:
    m = e.args[0].split()[-1]
    print("The module %s doesn't appear to be installed." % m)
    if m in module_help:
        print(module_help[m])
    raise

import logging
import os
import re
import time


class SyncNode:
    def __init__(self, config):
        self.config = config
        if 'action' in self.config:
            if self.config['action'] == 'create':
                self.create()
            if self.config['action'] == 'verify':
                self.verify(self.config['nodeurl'])
            if self.config['action'] == 'check':
                self.get_node_record(self.config['nodeurl'])
            if self.config['action'] == 'setlive':
                self.set_node_live(self.config['nodeurl'])

    def wait(self):
        logging.info("Waiting for %s seconds" % self.config['wait_interval'])
        time.sleep(self.config['wait_interval'])

    def get_next_available_node_index(self):
        query = '''SELECT node
            FROM nodes
            WHERE service = %s''' % self.config['serviceid']
        db = MySQLdb.connect(host=self.config['dbserver'],
                             user=self.config['dbuser'],
                             passwd=self.config['dbpass'],
                             db=self.config['dbname'])
        cur = db.cursor()
        cur.execute(query)
        results = cur.fetchall()

        # example result "https://sync-3-us-east-1.stage.mozaws.net"
        # example result "https://sync-9-us-west-2.sync.services.mozilla.com"

        index = 0
        for result in results:
            m = re.match(r"^https://sync-(\d*)-([^\.]*)\."
                 r"(sync\.services\.mozilla\.com|stage\.mozaws\.net)$",
                 result[0])
            if m and int(m.group(1)) > index:
                index = int(m.group(1))
                url = "https://sync-%s-%s.%s" % (index + 1,
                                                 self.config['region'],
                                                 m.group(3))
        return (index + 1, url)

    def get_node_record(self, url):
        query = '''SELECT *
            FROM nodes
            WHERE node = "%s"''' % self.config['nodeurl']
        db = MySQLdb.connect(host=self.config['dbserver'],
                             user=self.config['dbuser'],
                             passwd=self.config['dbpass'],
                             db=self.config['dbname'])
        cur = db.cursor()
        cur.execute(query)
        result = cur.fetchone()  # we should test if 0 rows returned
        logging.info(result)
        return result

    def set_node_live(self, url):
        capacity = (
            self.config['capacity_map'][self.config['instance_type']]
            if self.config['instance_type'] in self.config['capacity_map']
            else self.config['capacity_map']['default'])
        query = '''INSERT INTO nodes
            SET service = %(serviceid)d,
            node = "%(nodeurl)s",
            available = %(capacity)d,
            current_load = 0,
            capacity = %(capacity)d,
            downed = 0,
            backoff = 0''' % {'serviceid': self.config['serviceid'],
                              'nodeurl': url,
                              'capacity': capacity}

        logging.debug("Setting node live with query %s" % query)

        db = MySQLdb.connect(host=self.config['dbserver'],
                             user=self.config['dbuser'],
                             passwd=self.config['dbpass'],
                             db=self.config['dbname'])
        cur = db.cursor()
        result = cur.execute(query)
        db.commit()
        logging.debug("%s rows affected : %s" % (result, cur.messages))
        return True if result == 1 else False

    def get_node_secrets(self, url):
        return (mozsvc.secrets.
                DerivedSecrets(self.config['token_secret']).
                get(url))

    def get_az(self):
        instances = self.conn_ec2.get_only_instances(
                         filters={'tag:App': 'sync_1_5',
                                  'tag:Type': 'all_in_one_node'})
        result = None
        for zone in set([x.placement for x in instances]):
            if (result is None
                or result < [x.placement for x in instances].count(zone)):
                result = zone
        return result

    def spawn_instance(self):
        conn_cfn = boto.cloudformation.connect_to_region(self.config['region'])
        with open(self.config['cloudformation_template_filename']) as f:
            stack_id = conn_cfn.create_stack(
                 stack_name="syn-%s-%s" % (self.config['nodeindex'],
                                           self.config['environment']),
                 template_body=f.read(),
                 parameters=[
                     ('Environment', self.config['environment']),
                     ('SyncNodeInstanceType', self.config['instance_type']),
                     ('ProvisioningVersion', 'latest'),
                     ('NodeSecrets', ",".join(self.node_secrets)),
                     ('NodeNumber', self.config['nodeindex']),
                     ('AMI', self.config['amiid']),
                     ('AvailabilityZone', self.get_az())])

        logging.info("Node %s being created" % self.config['nodeindex'])

        # We'll loop here to wait for the stack to finish. A better way to do
        # this would be to have CloudFormation publish events to SNS, then
        # subscribe an https endpoint to the SNS topic. That endpoint would
        # be hosted on the admin server and would kick off the remainder
        # of the tasks after stack creation
        status = 'CREATE_IN_PROGRESS'
        while status == 'CREATE_IN_PROGRESS':
            stacks = conn_cfn.describe_stacks(stack_name_or_id=stack_id)
            if len(stacks) > 1:
                raise Exception("Describe stacks returned %s stacks" %
                                len(stacks))
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

    def create(self):
        if self.config['nodeurl'] is None or self.config['nodeindex'] is None:
            (self.config['nodeindex'],
                self.config['nodeurl']) = self.get_next_available_node_index()
        logging.debug("New node index and url are %s and %s" %
                      (self.config['nodeindex'], self.config['nodeurl']))
        self.node_secrets = self.get_node_secrets(self.config['nodeurl'])
        logging.debug("New node secret is %s" % self.node_secrets)
        cloudformation_status = self.spawn_instance()
        if cloudformation_status != 'CREATE_COMPLETE':
            logging.error("Attempt to build a sync node failed with "
                          "CloudFormation result %s" % cloudformation_status)
            sys.exit(1)
        verification_status = self.verify(self.config['nodeurl'])
        if not verification_status:
            logging.error("Verification of new node %s failed." %
                          self.config['nodeindex'])
            sys.exit(1)
        if not self.set_node_live():
            logging.error("Attempt to set node %s live failed." %
                          self.config['nodeindex'])
            sys.exit(1)
        logging.info("Node %s created, verified and set live in the "
                     "tokenserver DB" % self.config['nodeindex'])

    def verify(self, url):
        assert issubclass(
            TestStorage,
            StorageFunctionalTestCase)
        os.environ["MOZSVC_TEST_REMOTE"] = url
        test_ini_file = ("/data/server-syncstorage/build"
                        "/lib/syncstorage/tests/tests.ini")
        os.environ["MOZSVC_TEST_INI_FILE"] = test_ini_file
        secret = self.get_node_secrets(url)[0]
        logging.debug("url and secret are %s %s" % (url, secret))

        class LiveTestCases(TestStorage):
            def _authenticate(self):
                policy = self.config.registry.getUtility(
                              pyramid.interfaces.IAuthenticationPolicy)

                if secret is not None:
                    policy.secrets._secrets = [secret]
                return super(LiveTestCases, self)._authenticate()

        # Now use the unittest2 runner to execute them.
        suite = unittest2.TestSuite()
        suite.addTest(unittest2.makeSuite(LiveTestCases))
        runner = unittest2.TextTestRunner(
            stream=sys.stderr,
            failfast=True,
        )
        res = runner.run(suite)
        logging.info("Result of verification is %s" % res.wasSuccessful())
        return True if res.wasSuccessful() else False

    def modify(self):
        pass

    def terminate(self):
        pass
