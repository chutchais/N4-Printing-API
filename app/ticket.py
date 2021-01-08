from flask import Flask,request
import time
import logging
import csv
import json

import redis
import datetime

from flask import request
from flask import Response, stream_with_context

generated_on = str(datetime.datetime.now())

app = Flask(__name__)

#'tid-redis'
# db = redis.StrictRedis('localhost', 6379, charset="utf-8", decode_responses=True)
# db = redis.StrictRedis('192.168.10.102', 6379, charset="utf-8", decode_responses=True)
db = redis.StrictRedis('tid-redis', 6379, charset="utf-8", decode_responses=True)

@app.route('/')
def api_root():
	return 'Welcome to Ticket printing Service version 1.0'

@app.route('/ticket/print', methods=['PUT','POST'])
def ticket_print_document():
    json_data = request.get_json()
    ttl = 60*60 #60*60*24 *365 #31104000 #one year in seconds
    license_number = json_data['license']
    printer = json_data['printer']
 
    # file2 = open("print.json","w+")
    # file2.write(json.dumps(json_data, indent=4, sort_keys=True))
    # file2.close()
    # save to redis
   
    db.set(license_number,json.dumps(json_data) ) #store dict in a hashjson.dumps(json_data)
    db.expire(license_number, ttl) #expire it after a year
    db.publish(printer.lower(),license_number)
    # -------------------------------------------------------
	# return json_data #make_response( return_msg, http_code)
    return f'Save {license_number} success'

if __name__ == '__main__':
	app.run(host='0.0.0.0',debug=True)
	# serve(app, host='0.0.0.0', port=8013)