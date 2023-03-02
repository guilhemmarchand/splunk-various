from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os,sys
import logging
import requests
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Args
parser = argparse.ArgumentParser()
parser.add_argument('--debug', dest='debug', action='store_true')
parser.add_argument('--target_url', dest='target_url')
parser.add_argument('--target_port', dest='target_port')
parser.add_argument('--username', dest='username')
parser.add_argument('--password', dest='password')
parser.add_argument('--req_peer_name', dest='req_peer_name')
parser.add_argument('--remove_peer', dest='remove_peer', action='store_true')
parser.set_defaults(debug=False)
parser.set_defaults(remove_peer=False)
args = parser.parse_args()

# Set debug boolean
if args.debug:
    debug = True
else:
    debug = False

# Set remove_peer boolean
if args.remove_peer:
    remove_peer = True
else:
    remove_peer = False

# username
if args.username:
    username = args.username
else:
    username = False

# password
if args.password:
    password = args.password
else:
    password = False

# Set target_url
if args.target_url:
    target_url = args.target_url
else:
    target_url = False

# Set target_port
if args.target_port:
    target_port = args.target_port
else:
    target_port = False    

# Set req_peer_name
if args.req_peer_name:
    req_peer_name = args.req_peer_name
else:
    req_peer_name = False

# set logging
root = logging.getLogger()
root.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)

if debug:
    root.setLevel(logging.DEBUG)
    handler.setLevel(logging.DEBUG)
else:
    root.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)

# check args
if not username or not password or not target_url or not target_port or not req_peer_name:
    logging.error("Your arguments are wrong, target_url, username, password and req_peer_name are required")
    sys.exit(1)

# Set
url = 'https://' + str(target_url) + ':' + str(target_port) + '/services/cluster/manager/peers?output_mode=json&count=100000'
peers_dict = {}

# Get response from the manager
try:
    response = requests.get(url, auth=(str(username), str(password)), headers={'Content-Type': 'application/json'}, verify=False)

    # check response
    if response.status_code not in (200, 201, 204):
        logging.error(
            'REST call has failed!. url={}, HTTP Error={}, '
            'content={}'.format(target_url, response.status_code, response.text))
        sys.exit(1)

    else:
        manager_response = json.loads(response.text)
        response_manager = manager_response.get('entry')

        for subobject in response_manager:
            peer_guid = subobject.get('name')
            peer_name = subobject.get('content')['label']
            peers_dict[peer_name] = {'guid': peer_guid}

        logging.debug("list of peers and guid, dict=\"{}\"".format(json.dumps(peers_dict, indent=2)))

except Exception as e:
    raise Exception("An exception was encountered, exception=\"{}\"".format(str(e)))

# get and return peer
get_peer_guid = None
try:
    get_peer_guid = peers_dict.get(req_peer_name)['guid']
except Exception as e:
    get_peer_guid = None

# check
if not get_peer_guid:
    raise Exception("The requested peers=\"{}\" does not exist, or the API did not return the expected result, peers=\"{}\"".format(req_peer_name, json.dumps(peers_dict, indent=2)))

#
# remove the peer from the manager
#

if not remove_peer:
    logging.info("The peer_name=\"{}\" guid=\"{}\" was not removed from the manager, run this command with --remove_peer to remove the peer".format(req_peer_name, get_peer_guid))
else:
    logging.info("Attempting to remove the peer_name==\"{}\", guid=\"{}\"".format(req_peer_name, get_peer_guid))

    # Attempt to remove the peer
    url = 'https://' + str(target_url) + ':' + str(target_port) + '/services/cluster/manager/control/control/remove_peers'
    data = {'peers': peer_guid}

    try:
        response = requests.post(url, auth=(str(username), str(password)), headers={'Content-Type': 'application/json'}, data=data, verify=False)

        # check response
        if response.status_code not in (200, 201, 204):
            logging.error(
                'remove peer rest call has failed!. url={}, HTTP Error={}, '
                'content={}'.format(target_url, response.status_code, response.text))
            sys.exit(1)

        else:
            logging.info("successfully removed the peer_name==\"{}\", guid=\"{}\"".format(req_peer_name, get_peer_guid))

    except Exception as e:
        raise Exception("An exception was encountered, exception=\"{}\"".format(str(e)))    

    # refresh the list of peers and show
    url = 'https://' + str(target_url) + ':' + str(target_port) + '/services/cluster/manager/peers?output_mode=json&count=100000'
    new_peers_dict = {}

    # Get response from the manager
    try:
        response = requests.get(url, auth=(str(username), str(password)), headers={'Content-Type': 'application/json'}, verify=False)

        # check response
        if response.status_code not in (200, 201, 204):
            logging.error(
                'get peers call has failed!. url={}, HTTP Error={}, '
                'content={}'.format(target_url, response.status_code, response.text))
            sys.exit(1)

        else:
            manager_response = json.loads(response.text)
            response_manager = manager_response.get('entry')

            for subobject in response_manager:
                peer_guid = subobject.get('name')
                peer_name = subobject.get('content')['label']
                new_peers_dict[peer_name] = {'guid': peer_guid}

            logging.info("final list of peers and guid, dict=\"{}\"".format(json.dumps(new_peers_dict, indent=2)))

    except Exception as e:
        raise Exception("An exception was encountered, exception=\"{}\"".format(str(e)))
