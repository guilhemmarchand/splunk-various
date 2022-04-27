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

__name__ = "export_to_hec.py"
__author__ = "Guilhem Marchand"
__copyright__ = "Apache 2.0"
__credits__ = ["Guilhem Marchand"]
__license__ = "Apache 2.0"
__version__ = "0.1.0"
__maintainer__ = "Guilhem Marchand"
__email__ = "gmarchand@splunk.com"
__status__ = "PRODUCTION"

# set logging
splunkhome = '/opt/splunk'
log_file = "export_myexport.log"
filehandler = logging.FileHandler(splunkhome + "/var/log/splunk/" + log_file, 'a')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(filename)s %(funcName)s %(lineno)d %(message)s')
filehandler.setFormatter(formatter)
log = logging.getLogger()  # root logger - Good to get it only once.
for hdlr in log.handlers[:]:  # remove the existing file handlers
    if isinstance(hdlr,logging.FileHandler):
        log.removeHandler(hdlr)
log.addHandler(filehandler)      # set the new handler
# set the log level to INFO, DEBUG as the default is ERROR
log.setLevel(logging.INFO)

# How to use:
# Ideally run this script as the Splunk user, which allows writting the log file to the Splunk var location leading it to be indexed transparently
# Run this script in the background once it is configured, ex:
# nohup python3 export_to_hec.py &

# Provide the search head targets (if multiple provide as a list, example below with an SHC)
HOST = ["sh1", "sh2", "sh3"]
# Splunkd port
PORT = 8089
# Credentials
USERNAME = "mylogin"
PASSWORD = "mypassword"

# HEC target and token
url = "https://myhectarget.mydomain.com:8088/services/collector/event"
authHeader = {'Authorization': 'Splunk MY_HEC_TOKEN'}

# Run a one-shot search and display the results using the results reader

# Set the parameters for the search:
# - Search everything in a 24-hour time range starting June 19, 12:00pm
# - Display the first 10 results

# source and destination indexes
source_index = "my_source_index"
destination_index = "my_destination_index"

# the total time range in second for each search to be performed
# a period of 24 hours is a good choice for various reasons, from a performance and logic perspective, even at very large scale
# At extremely large scale (this was validated up to several dozen of millions per days), you may reduce up to 4 hours or less
time_sec_chunk = 86400

# epoch start and end
epoch_start = 1535760000
epoch_end = 1648944000

# process chunks by day
epoch_chunk = epoch_start++time_sec_chunk

# grand total counters
total_eventcount = 0
total_successes = 0
total_failures = 0

# store failure batches, any HEC permanently failed batch will be added to this file, allowing for a manual replay
failure_output_file = 'myexport_restore_failures.json'

#
# START
#

print("Consult the log_file={} for more information about the data offload process.".format(log_file))
logging.info("Starting data offload and ingestion process")

# Go
while epoch_start < epoch_end:

    # The Splunk search
    searchquery_oneshot = "search index=" + str(source_index) + " earliest=" + str(epoch_start) + " latest=" + str(epoch_chunk) + " | eval time=_time | where _time<" + str(epoch_end)
    logging.info("Running the Splunk search, query=\"{}\"".format(searchquery_oneshot))

    # empty array to store our processed records
    records_list = []

    # counter
    records_count = 0

    # Perform the Splunk search, with repeat in case of failure
    search_attempts = 0
    search_max_attempts = 100
    while search_attempts <= search_max_attempts:

        try:

            # Create a Service instance and log in
            service = client.connect(
                host=random.choice(HOST),
                port=PORT,
                username=USERNAME,
                password=PASSWORD)

            # for stdout
            print("Running the Splunk search, query=\"{}\"".format(searchquery_oneshot))

            rr = results.JSONResultsReader(service.jobs.export(searchquery_oneshot, count=0, output_mode='json'))

            for result in rr:
                if isinstance(result, dict):

                    # increment the grand total
                    total_eventcount +=1

                    # increment the counter
                    records_count +=1

                    # get the event details
                    source_value = result.get('source')
                    raw_value = result.get('_raw')
                    time_value = result.get('time')
                    sourcetype_value = result.get('sourcetype')
                    host_value = result.get('host')

                    # set the record
                    event_dict = {
                            "time": str(time_value),
                            "source": str(source_value),
                            "sourcetype": str(sourcetype_value),
                            "host": str(host_value),
                            "index": str(destination_index),
                            "event": str(raw_value),
                        }

                    # add to the dict
                    records_list.append(event_dict)

            assert rr.is_preview == False

            # send to HEC by chunk

            # to report processed messages
            processed_count = 0
            success_count = 0
            failures_count = 0

            # process by chunk
            chunks = [records_list[i:i + 500] for i in range(0, len(records_list), 500)]
            for chunk in chunks:

                chunk_len = len(chunk)

                session = requests.Session()
                session.verify = True

                # Handle failures and re-attempting
                hec_send_attempts = 0
                max_hec_send_attempts = 100

                while hec_send_attempts <= max_hec_send_attempts:

                    try:
                        response = session.post(url, headers=authHeader, data=json.dumps(chunk), verify=False)

                        if response.status_code not in (200, 201, 204):

                            # increment
                            hec_send_attempts+=1

                            # if permanent or temporary failure
                            if hec_send_attempts == max_hec_send_attempts:

                                # permanent failure, write to file
                                failures_count+=chunk_len
                                total_failures+=chunk_len
                                logging.error("permanent failure forwarding to HEC failed with error code=\"{}\" and response=\"{}\"".format(response.status_code, response.text))
                                with open(failure_output_file, 'a') as file:
                                    file.write(json.dumps(chunk) + '\n')

                            else:
                                logging.warning("temporary failure forwarding to HEC failed with error code=\"{}\" and response=\"{}\"".format(response.status_code, response.text))

                        else:

                            processed_count = processed_count + chunk_len
                            success_count+=chunk_len
                            total_successes+=chunk_len

                            # end this iteration
                            break

                    except Exception as e:

                        # increment
                        hec_send_attempts+=1

                        # if permanent or temporary failure
                        if hec_send_attempts == max_hec_send_attempts:

                            failures_count+=chunk_len
                            total_failures+=chunk_len
                            logging.error("permanent failure, forwarding to HEC failed with exception=\"{}\"".format(e))
                            with open(failure_output_file, 'a') as file:
                                file.write(json.dumps(chunk) + '\n')

                        else:
                            logging.warning("tempoary forwarding to HEC failed with exception=\"{}\"".format(e))


            summary_results = {
                'records_count' : str(records_count),
                'process_count': str(processed_count),
                'success_count': str(success_count),
                'failures_count': str(failures_count),
            }

            # logging
            logging.info("terminated HEC batch stream, summary=\"{}\"".format(json.dumps(summary_results, indent=1)))

            # end this iteration

            # logging
            logging.info("terminated the search iteration, epoch_start=\"{}\", epoch_end=\"{}\"".format(str(epoch_start), str(epoch_chunk)))

            epoch_start = epoch_start++time_sec_chunk
            epoch_end = epoch_end++time_sec_chunk
            epoch_chunk = epoch_chunk++time_sec_chunk

            break

        except Exception as e:

            search_attempts+=1
            if search_attempts == search_max_attempts:
                logging.error("permanent failure while attempting to run the Splunk search with exception=\"{}\"".format(e))
                sys.exit(1)
            else:
                logging.warning("temporary failure while attempting to run the Splunk search with exception=\"{}\"".format(e))

#
# END
#

final_summary_results = {
    'total_records_count' : str(total_eventcount),
    'total_successes': str(total_successes),
    'total_failures': str(total_failures),
}
print("Export job is now terminated, summary=" + json.dumps(final_summary_results, indent=1))
logging.info("Export job is now terminated, summary=\"{}\"".format(json.dumps(final_summary_results, indent=1)))
sys.exit(0)
