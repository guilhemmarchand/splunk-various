import splunklib.client as client
import splunklib.results as results
import sys
import logging
import random
import time
import json
from time import sleep
import hashlib
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

__name__ = "search_benchmark.py"
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
log_file = "search_benchmark.log"
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
# example:
HOST = ["sh1", "sh2", "sh3"]
# HOST = ["localhost"]

# Splunkd port
PORT = 8089

# Credentials - you can include multiple users, but they should match all the same password
# example:
# USERNAME = ["user1", "user2", "user3"]
USERNAME = ["benchmark"]
PASSWORD = "ch@ngeM3"

# Run a one-shot search and display the results using the results reader

# Set the parameters for the search:
# - Search everything in a 24-hour time range starting June 19, 12:00pm
# - Display the first 10 results

# index constraint, you can include a wildcard search, example:
# source_constraint = "index=network*"
# You can include multiple index constraints too
# source_constraint = "index=network* OR index=firewall*"
source_constraint = "index=main OR index=network OR index=firewall OR index=linux*"

# the total time range in second for each search to be performed
# a period of 24 hours is a good choice for various reasons, from a performance and logic perspective, even at very large scale
# At extremely large scale (this was validated up to several dozen of millions per days), you may reduce up to 4 hours or less
time_sec_chunk = 300

# A list of some searchs, we are going to randomly choose one of these
spl_statement = ['fields *',
                'bucket _time span=1m | stats count',
                'stats count',
                'timechart span=1s count', 
                'timechart span=1m count', 
                'timechart span=1m count by index', 
                'timechart span=1s count by source', 
                'rex field=host "(?<host_rex>.{0,3})" | rex field=source "(?<source_rex>.{0,3})" | rex field=sourcetype "(?<sourcetype_rex>.{0,3})" | eval key = md5(host_rex . source_rex . sourcetype_rex) | timechart count span=30s limit=0 useother=f by key',
                'stats values(source) as source, values(host) as host, values(sourcetype) as sourcetype | mvexpand source | mvexpand sourcetype | mvexpand host | stats count by _time',
                'eval time=strftime(_time, "%c") | stats count by time'
                ]

# Infinite loop
while 1 == 1:

    # epoch start and end
    epoch_start = time.time()-86400
    epoch_end = time.time()

    # process chunks by day
    epoch_chunk = epoch_start++time_sec_chunk

    # grand total counters
    total_eventcount = 0
    total_successes = 0
    total_failures = 0

    #
    # START
    #

    print("Consult the log_file={} for more information about the data offload process.".format(log_file))
    logging.info("Starting data offload and ingestion process")

    # Go
    while epoch_start < epoch_end:

        # The Splunk search statement
        per_search_statement = random.choice(spl_statement)

        # Store the spl_statement (which is random) as an md5, this will be useful for performance comparison
        per_search_statement_hash = hashlib.md5(per_search_statement.encode('utf-8')).hexdigest()

        searchquery_oneshot = "search " + str(source_constraint) + " earliest=" + str(epoch_start) + " latest=" + str(epoch_chunk) + " | eval time=_time | where _time<" + str(epoch_end) + " | " + str(per_search_statement)
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
                    username=random.choice(USERNAME),
                    password=PASSWORD)

                # for stdout
                print("Running the Splunk search, query=\"{}\"".format(searchquery_oneshot))

                # performance counter
                start_search_counter = time.time()

                rr = results.JSONResultsReader(service.jobs.export(searchquery_oneshot, count=0, output_mode='json'))

                for result in rr:
                    if isinstance(result, dict):

                        # increment the grand total
                        total_eventcount +=1

                        # increment the counter
                        records_count +=1

                        # get the event details
                        try:
                            index_value = result.get('index')
                        except Exception as e:
                            index_value = "undefined"

                        try:
                            source_value = result.get('source')
                        except Exception as e:
                            source_value = "undefined"

                        try:
                            raw_value = result.get('_raw')
                        except Exception as e:
                            raw_value = "undefined"
    
                        try:
                            time_value = result.get('time')
                        except Exception as e:
                            index_value = "undefined"

                        try:
                            sourcetype_value = result.get('sourcetype')
                        except Exception as e:
                            sourcetype_value = "undefined"

                        try:
                            host_value = result.get('host')
                        except Exception as e:
                            host_value = "undefined"

                        # set the record
                        event_dict = {
                                "time": str(time_value),
                                "source": str(source_value),
                                "sourcetype": str(sourcetype_value),
                                "host": str(host_value),
                                "index": str(index_value),
                                "event": str(raw_value),
                            }

                        # add to the dict
                        records_list.append(event_dict)

                assert rr.is_preview == False

                # to report processed messages
                processed_count = 0
                success_count = 0
                failures_count = 0

                # process by chunk
                chunks = [records_list[i:i + 500] for i in range(0, len(records_list), 500)]
                for chunk in chunks:

                    chunk_len = len(chunk)

                    processed_count = processed_count + chunk_len
                    success_count+=chunk_len
                    total_successes+=chunk_len

                summary_results = {
                    'records_count' : str(records_count),
                    'process_count': str(processed_count),
                    'success_count': str(success_count),
                    'failures_count': str(failures_count),
                }

                # logging
                logging.info("terminated batch, summary=\"{}\"".format(json.dumps(summary_results, indent=1)))

                # end this iteration

                # logging
                search_duration = time.time() - start_search_counter
                logging.info("terminated the search iteration, epoch_start=\"{}\", epoch_end=\"{}\", duration=\"{}\", spl_statement=\"{}\", spl_statement_hash=\"{}\"".format(str(epoch_start), str(epoch_chunk), str(search_duration), str(per_search_statement), str(per_search_statement_hash)))

                epoch_start = epoch_start++time_sec_chunk
                epoch_end = epoch_end++time_sec_chunk
                epoch_chunk = epoch_chunk++time_sec_chunk

                break

            except Exception as e:

                search_attempts+=1
                # Sleep 10sec
                time.sleep(10)

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

    # epoch start and end
    epoch_start = time.time()-86400
    epoch_end = time.time()
