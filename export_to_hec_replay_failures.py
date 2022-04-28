import splunklib.client as client
import splunklib.results as results
import sys
import logging
import random
import json
from time import sleep
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# HEC target and token
url = "https://myhectarget.mydomain.com:8088/services/collector/event"
authHeader = {'Authorization': 'Splunk MY_HEC_TOKEN'}

# store failure batches, any HEC permanently failed batch will be added to this file, allowing for a manual replay
failure_output_file = 'myexport_restore_failures.json'

# some counters
success_count = 0
processed_count = 0
failures_count = 0

#
# Go
#

print("Hold on while HEC re-processing is being performed...")

with open(failure_output_file) as file:
    lines = file.readlines()
    for line in lines:

        session = requests.Session()
        session.verify = True

        chunk = json.loads(line)
        chunk_len = len(chunk)

        try:
            response = session.post(url, headers=authHeader, data=json.dumps(chunk), verify=False)

            if response.status_code not in (200, 201, 204):
                failures_count+=chunk_len
                processed_count+=chunk_len
                print("failure forwarding to HEC failed with error code=\"{}\" and response=\"{}\"".format(response.status_code, response.text))
            else:
                processed_count+=chunk_len
                success_count+=chunk_len

        except Exception as e:
            failures_count+=chunk_len
            processed_count+=chunk_len
            print("failure, forwarding to HEC failed with exception=\"{}\"".format(e))

summary_results = {
    'process_count': str(processed_count),
    'success_count': str(success_count),
    'failures_count': str(failures_count),
}

# logging
print("terminated HEC batch stream, summary=\"{}\"".format(json.dumps(summary_results, indent=1)))
print("If you are happy with the results, please empty the file={}".format(failure_output_file))
