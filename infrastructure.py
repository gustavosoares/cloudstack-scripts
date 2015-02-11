#!/usr/bin/env python

import argparse
import os
import sys
from ConfigParser import SafeConfigParser
from ACSConn import CloudStack
from prettytable import PrettyTable

parser = argparse.ArgumentParser(description='Check Cloudstack status')
parser.add_argument('--project', action="store_true", help='Resource usage by projects, ordered by project name')
parser.add_argument('--cluster', action="store_true", help='Cluster capacity, ordered by used resources')
parser.add_argument('--vr', action="store_true", help='State and version of Virtual Routers')
parser.add_argument('--ssvm', action="store_true", help='State of system vms')
parser.add_argument('--lb', action="store_true", help="List LoadBalancer by Project/account")
parser.add_argument('--capacity', action="store_true", help='Capacity by zone and type, ordered by used resources')
parser.add_argument('--region', type=str, default='lab', help='Run the tests on this region')
args = parser.parse_args()


# import keys from cloudmonkey config
parser = SafeConfigParser()
parser.read(os.path.expanduser('~/.cloudmonkey/config'))
if parser.has_section(args.region):
    if not parser.has_option(args.region, 'url'):
        print "There is no url option in '%s' section" % args.region
        sys.exit(1)
    if not parser.has_option(args.region, 'apikey'):
        print "There is no 'apikey' option in '%s' section" % args.region
        sys.exit(1)
    if not parser.has_option(args.region, 'secretkey'):
        print "There is no 'secretkey' option in '%s' section" % args.region
        sys.exit(1)

    apikey = parser.get(args.region, 'apikey')
    api_url = parser.get(args.region, 'url')
    secretkey = parser.get(args.region, 'secretkey')
else:
    print "Invalid region: '%s'" % args.region
    sys.exit(1)

api = CloudStack(api_url, apikey, secretkey)

capacity_type = {
    0:  'Memory',
    1:  'CPU',
    2:  'Storage',
    3:  'Stg Allocated',
    4:  'Public IP',
    5:  'Private IP',
    6:  'Secondary Stg',
    7:  'Vlan',
    8:  'Direct Attc Pub IP',
    9:  'Local Storage',
    19: 'GPU'
}


def get_configuration(name):
    result = api.listConfigurations({
        'name': name
    })
    return result['configuration']


def get_accounts(param):
    result = api.listAccounts({
        'listall':  'true'
    })
    acc_ids = []
    for acc_id in result['account']:
        acc_ids.append(acc_id[param])
    return acc_ids


def get_projects(param):
    result = api.listProjects({
        'listall':  'true',
        'state':    'Active'
    })
    p_ids = []
    for p_id in result['project']:
        p_ids.append(p_id[param])
    return p_ids


def list_projects():
    result = api.listProjects({
        'listall':  'true',
        'state':    'Active'
    })
    t = PrettyTable(['Project', 'Account', 'CPU Available', 'MEM Available (GB)', 'Pri Stg Available (GB)', 'Sec Stg Available (GB)', 'Templates Available', 'VM Available', 'Vol Available'])
    t.align['Project'] = 'l'
    for res in result['project']:
        t.add_row([res['name'], res['account'], res['cpuavailable'], int(res['memoryavailable'])/1024,    res['primarystorageavailable'], res['secondarystorageavailable'], res['templateavailable'], res['vmavailable'], res['volumeavailable']])
    return t.get_string(sortby="Project")


def list_clusters():
    result = api.listClusters({
        'showcapacities':   'true',
        'allocationstate':  'Enabled'
    })
    t = PrettyTable(['Zone', 'Cluster', 'Pod', 'Type', 'Used (%)', 'To Threshold', 'Free (GB/unit)'])

    for res in result['cluster']:
        for r in res['capacity']:
            if (r['type'] == 0):
                # memory
                threshold = float(get_configuration('cluster.memory.allocated.capacity.disablethreshold')[0]['value'])
            elif (r['type'] == 1):
                # CPU
                threshold = float(get_configuration('cluster.cpu.allocated.capacity.disablethreshold')[0]['value'])
            elif (r['type'] == 2):
                # Storage
                threshold = float(get_configuration('pool.storage.capacity.disablethreshold')[0]['value'])
            elif (r['type'] == 3):
                # Allocated Storage
                threshold = float(get_configuration('pool.storage.allocated.capacity.disablethreshold')[0]['value'])
            else:
                threshold = 1

            # if the resource is not unit, convert to GB
            if (r['type'] in [0, 2, 3, 6, 9]):
                convert_unit = 1024*1024*1024
            else:
                convert_unit = 1

            free_until_hit_threshold = int(((r['capacitytotal'] * threshold) - r['capacityused'])/convert_unit)
            total_free_resource = (r['capacitytotal'] - r['capacityused'])/convert_unit

            t.add_row([res['zonename'], res['name'], res['podname'], capacity_type[r['type']], float(r['percentused']), free_until_hit_threshold, total_free_resource])

    return t.get_string(sortby="Used (%)", reversesort=True)


def list_vrs():
    result = api.listRouters({
        'listall':  'true',
        'state':    'Running'
    })
    t = PrettyTable(['Name', 'State', 'Zone', 'Host', 'Version', 'Netowork Domain', 'Link Local IP', 'Guest IP Addr'])
    for rtr in result['router']:
        t.add_row([rtr['name'], rtr['state'], rtr['zonename'], rtr['hostname'], rtr['version'], rtr['networkdomain'], rtr['linklocalip'], rtr['guestipaddress']])
    return t.get_string(sortby="Version", reversesort=True)


def list_ssvms():
    result = api.listSystemVms({})
    t = PrettyTable(['Name', 'Version', 'State', 'Agent', 'Type', 'Zone', 'Host'])
    for ssvm in result['systemvm']:
        agent_status = api.listHosts({
            'name':     ssvm['name']
        })
        # if ssvm is not in running state, the xen host is empty.
        if not ssvm.has_key('hostname'):
            ssvm['hostname'] = '-'
        t.add_row([ssvm['name'], agent_status['host'][0]['version'], ssvm['state'], agent_status['host'][0]['state'], ssvm['systemvmtype'], ssvm['zonename'], ssvm['hostname']])
    return t.get_string(sortby="Zone")


def list_capacities():
    result = api.listCapacity({})
    t = PrettyTable(['Type', 'Zone', 'Used (%)'])
    t.align['Type'] = 'l'
    for rsc_type in result['capacity']:
        t.add_row([capacity_type[rsc_type['type']], rsc_type['zonename'], float(rsc_type['percentused'])])
    return t.get_string(sortby="Used (%)", reversesort=True)


def list_loadbalancers():
    # account para pegar os balanceadores soltos
    t = PrettyTable(['Project', 'State', 'Name', 'PublicIP', 'CIDR', 'Network Name', 'Network Domain',  'Additional Networks'])
    # list all projects with LB
    for project_id in get_projects('id'):
        result = api.listLoadBalancerRules({
            'listall':      'true',
            'projectid':    project_id
        })
        # if project has LB
        if result:
            # Get details from network
            for lb in result['loadbalancerrule']:
                network_details = network_detail(id=lb['networkid'], projectid=project_id)
                # get details from additional network(s) in LB
                additional_network = []
                if lb['additionalnetworkids']:
                    for adt_network in lb['additionalnetworkids']:
                        additional_network.append(network_detail(id=adt_network, projectid=project_id)['name'])
                t.add_row([lb['project'], lb['state'], lb['name'], lb['publicip'], network_details['cidr'], network_details['name'], network_details['networkdomain'], additional_network])
    return t.get_string(sortby="Project")


def network_detail(id, projectid):
    result = api.listNetworks({
        'listall':      'true',
        'id':           id,
        'projectid':    projectid
    })
    if result:
        return result['network'][0]


if args.project:
    print list_projects()
elif args.cluster:
    print list_clusters()
elif args.vr:
    # add flag --running|stopped
    print "List only VR's in 'Running' state!"
    print list_vrs()
elif args.ssvm:
    print list_ssvms()
elif args.capacity:
    print list_capacities()
elif args.lb:
    print list_loadbalancers()
