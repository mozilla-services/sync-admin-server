Firefox Sync Node Manager
=========================

Usage
-----

usage: manage_sync_node [-h] [-c FILE]
                        [-r {eu-west-1,sa-east-1,us-east-1,ap-northeast-1,us-west-2,us-west-1,ap-southeast-1,ap-southeast-2}]
                        [-e {prod,stage,dev}] [--dbserver DBSERVER]
                        [--dbuser DBUSER] [--dbname DBNAME] [-l LOGLEVEL]
                        {verify,create,check,setlive} ...

Create, interrogate and manipulate Firefox Sync nodes

positional arguments:
  {verify,create,check,setlive}
                        sub-command help
    create              Create a new Firefox Sync node
    verify              Verify the health of an existing Firefox Sync node
    check               Check the state of a Firefox Sync node in the
                        tokenserver database
    setlive             Set a Firefox Sync node live by adding it into the
                        tokenserver database

optional arguments:
  -h, --help            show this help message and exit
  -c FILE, --config FILE
                        Specify a YAML configuration file
  -r {eu-west-1,sa-east-1,us-east-1,ap-northeast-1,us-west-2,us-west-1,ap-southeast-1,ap-southeast-2}, --region {eu-west-1,sa-east-1,us-east-1,ap-northeast-1,us-west-2,us-west-1,ap-southeast-1,ap-southeast-2}
                        AWS Region
  -e {prod,stage,dev}, --environment {prod,stage,dev}
                        AWS Region
  --dbserver DBSERVER   Host name of the MySQL token server database
  --dbuser DBUSER       User name of the MySQL token server database
  --dbname DBNAME       Database name of the MySQL token server database
  -l LOGLEVEL, --loglevel LOGLEVEL
                        Log level verbosity
