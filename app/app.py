from flask import Flask,request ,make_response,g#, url_for
import xml.etree.ElementTree as ET
import time
import logging
import csv
import json

import redis

from xml.etree.ElementTree import Element, SubElement, Comment, tostring
import datetime

from flask import request
from flask import Response, stream_with_context

from xml.etree import ElementTree
from xml.dom import minidom
# from ElementTree_pretty import prettify

generated_on = str(datetime.datetime.now())

app = Flask(__name__)

# db = redis.Redis('localhost') #connect to server
#'tid-redis'
db = redis.StrictRedis('localhost', 6379, charset="utf-8", decode_responses=True)
# db = redis.StrictRedis('tid-redis', 6379, charset="utf-8", decode_responses=True)

def prettify(elem):
	"""Return a pretty-printed XML string for the Element.
	"""
	rough_string = ElementTree.tostring(elem, 'utf-8')
	reparsed = minidom.parseString(rough_string)
	return reparsed.toprettyxml(indent="  ")

@app.before_request
def before_request():
   g.request_start_time = time.time()
   g.request_time = lambda: "%.5fs" % (time.time() - g.request_start_time)

@app.route('/')
def api_root():
	return 'Welcome to N4 printing Service version 1.0'


@app.route('/truck/<truck_licence>', methods = ['GET'])
def truck(truck_licence):
	ttl = 31104000 #one year in seconds

	if not db.exists(truck_licence): #does the hash exist?
		return "Error: truck_licence doesn't exist"
 
	json_data = db.get(truck_licence) #get all the keys in the hash
	jdata = json.loads(json_data)
	jdata["ttl"] = db.ttl(truck_licence)
	return json.dumps(jdata, indent=4,sort_keys=True) ,200

@app.route('/container/<container>/<truck_licence>/<action>', methods = ['GET'])
def container_damage(container,truck_licence,action):
	key = '%s:%s:%s' % (container,truck_licence,action)
	ttl = 31104000 #one year in seconds

	if not db.exists(key): #does the hash exist?
		return "Error: %s doesn't exist" % key,500
 
	value = db.get(key) #get all the keys in the hash
	return value ,200

@app.route('/n4/print/<document>', methods=['PUT','POST'])
def print_document(document):
	try:
		xml = request.data
		return_msg ,http_code		= make_printable_xml(xml)
	except Exception as e:
		http_code = 500
		return_msg ='HTTP_500_INTERNAL_SERVER_ERROR'
	
	return make_response( return_msg, http_code)

def make_printable_xml(xml):
	try:
		generated_on = str(datetime.datetime.now())

		json_data 	= {}

		top = Element('print')
		comment = Comment('Generated for N4 printing on %s' % generated_on)
		top.append(comment)

		root = ET.fromstring(xml)
		ns = {'argo': 'http://www.navis.com/argo'}
		# Truck Visit
		
		json_data['document'] 		=   root.find('./argo:docDescription/docName',ns).text
		json_data['printer'] 		=   root.find('./argo:docDescription/ipAddress',ns).text
		

		truck_visit_node 	=  	root.find('./argo:docBody/argo:truckVisit',ns)
		license_number 		= 	truck_visit_node.find('tvdtlsLicNbr').text
		truck_company_code	= 	truck_visit_node.find('tvdtlsTrkCompany').text
		truck_company_name	= 	truck_visit_node.find('tvdtlsTrkCompanyName').text
		truck_start 		= 	truck_visit_node.find('tvdtlsTrkStartTime').text
		# Create XML for printing
		truck_child 			= 	SubElement(top, 'truck')
		license_child 			= 	SubElement(truck_child, 'license')
		license_child.text 		=  	license_number
		json_data['license'] 	=   license_number

		company_child 			= 	SubElement(truck_child, 'company',{'code':truck_company_code})
		company_child.text 		=  	truck_company_name
		json_data['company_code'] 	=   truck_company_code
		json_data['company'] 		=   truck_company_name

		start_child 			= 	SubElement(truck_child, 'start')
		start_child.text 		=  	truck_start
		json_data['start'] 		=   truck_start

		# Truck Transaction
		truck_trans_nodes 	=  root.findall('./argo:docBody/argo:trkTransaction',ns)
		container 	=	''
		iso 		= 	''
		is_damage 	= 	False
		position 	= 	''
		state 		= 	''
		category 	= 	''
		seal1 		= 	''
		seal2 		= 	''
		

		containers_child  = 	SubElement(top, 'containers')
		containers = []
		for t in truck_trans_nodes:
			json_container ={}
			# Make container for each container
			container_child  = 	SubElement(containers_child, 'container')

			if t.find('tranCtrNbr',ns) != None:
				container = t.find('tranCtrNbr',ns).text
			else :
				container = ''

			# Case swap or change container
			if t.find('tranCtrNbrAssigned',ns) != None:
				container = t.find('tranCtrNbrAssigned',ns).text

			child 			= 	SubElement(container_child, 'number')
			child.text 		=  	container
			json_container['number'] = container

			# <tranSubType>DI</tranSubType>
			# RE  Receive export (ส่งตู้)
			# RM  Receive empty (ส่งตู้)
			# DI  Delivery import (รับตู้)
			# DM  Delivery empty (รับตู้)
			# Dray in  ส่งตู้
			# Dray off  รับตู้

			transtype = t.find('tranSubType',ns).text
			child 			= 	SubElement(container_child, 'trans_type')
			child.text 		=  	transtype
			json_container['trans_type'] = transtype


			if t.find('tranLineId',ns) != None:
				line = t.find('tranLineId',ns).text
			else :
				line = ''

			child 			= 	SubElement(container_child, 'line')
			child.text 		=  	line
			json_container['line'] = line


			if t.find('tranCtrTypeId',ns) != None:
				iso = t.find('tranCtrTypeId',ns).text
			else :
				iso = ''
		  # <tranEqoEqIsoGroup>GP</tranEqoEqIsoGroup>
		  # <tranEqoEqLength>NOM40</tranEqoEqLength>
		  # <tranEqoEqHeight>NOM96</tranEqoEqHeight>
			if t.find('tranEqoEqIsoGroup',ns) != None :
				container_type 		= t.find('tranEqoEqIsoGroup',ns).text
			else :
				container_type		= 'DV' #default

			if t.find('tranEqoEqLength',ns) != None :
				container_length 	= t.find('tranEqoEqLength',ns).text.replace('NOM','')
			else:
				container_length 	= '40' #default

			if t.find('tranEqoEqHeight',ns) != None :
				container_height 	= t.find('tranEqoEqHeight',ns).text.replace('NOM','')
			else :
				container_height	= '86' #default


			iso_text 			= '%s\' %s %s' % (container_length,int(container_height)/10,container_type)
			# print (iso_text)
			child 			= 	SubElement(container_child, 'iso',{'code':iso})
			child.text 		=  	iso_text
			json_container['iso_text'] = iso_text
			json_container['iso_code'] = iso
			

		# <argo:tranCarrierVisit>
  #       <cvId>C1B_939E-946W</cvId>
  #       <cvCvdCarrierVehicleName>NORTHERN MAJESTIC</cvCvdCarrierVehicleName>
  #       <cvCvdCarrierIbVygNbr>939E</cvCvdCarrierIbVygNbr>
  #       <cvCvdCarrierObVygNbr>946W</cvCvdCarrierObVygNbr>
  #     	</argo:tranCarrierVisit>
			vessel_code 	= t.find('argo:tranCarrierVisit/cvId',ns).text.split('_')[0]
			vessel_name 	= t.find('argo:tranCarrierVisit/cvCvdCarrierVehicleName',ns).text
			voy_in	 		= t.find('argo:tranCarrierVisit/cvCvdCarrierIbVygNbr',ns).text
			voy_out	 		= t.find('argo:tranCarrierVisit/cvCvdCarrierObVygNbr',ns).text
			vessel_child 	= 	SubElement(container_child, 'vessel')
			child 			= 	SubElement(vessel_child, 'code')
			child.text 		=  	vessel_code
			child 			= 	SubElement(vessel_child, 'name')
			child.text 		=  	vessel_name
			child 			= 	SubElement(vessel_child, 'voy_in')
			child.text 		=  	voy_in
			child 			= 	SubElement(vessel_child, 'voy_out')
			child.text 		=  	voy_out
			child 			= 	SubElement(vessel_child, 'full_name')
			child.text 		=  	'%s/%s %s' % (vessel_code,voy_out,vessel_name)

			json_container['vessel_code'] 	= vessel_code
			json_container['vessel_name'] 	= vessel_name
			json_container['voy_in'] 		= voy_in
			json_container['voy_out'] 		= voy_out

			# <tranCtrFreightKind>FCL</tranCtrFreightKind>
			if t.find('tranCtrFreightKind',ns) != None:
				freightkind = t.find('tranCtrFreightKind',ns).text
			else :
				freightkind = ''

			child 			= 	SubElement(container_child, 'freightkind')
			child.text 		=  	freightkind
			json_container['freightkind'] 		= freightkind

			# <argo:tranDischargePoint1>
   #      	<pointId>SGSIN</pointId>
			if t.find('argo:tranDischargePoint1/pointId',ns) != None:
				pod = t.find('argo:tranDischargePoint1/pointId',ns).text
			else :
				pod = ''

			child 			= 	SubElement(container_child, 'pod')
			child.text 		=  	pod
			json_container['pod'] 		= pod

			# <tranCtrGrossWeight>10000.0</tranCtrGrossWeight>
			if t.find('tranCtrGrossWeight',ns) != None:
				gross = t.find('tranCtrGrossWeight',ns).text
			else :
				gross = 	''


			child 			= 	SubElement(container_child, 'gross_weight')
			child.text 		=  	gross
			json_container['gross_weight'] 		= gross

			# <tranCreated>Nov 6, 2019 4:09 PM</tranCreated>
			  # <tranCreator>gab2295</tranCreator>
			  # <tranChanged>Nov 6, 2019 4:09 PM</tranChanged>
			  # <tranChanger>gab2295</tranChanger>
			created_date	= t.find('tranCreated',ns).text
			created_user 	= t.find('tranCreator',ns).text
			changed_date 	= t.find('tranChanged',ns).text
			changed_user 	= t.find('tranChanger',ns).text
			
			child 			= 	SubElement(container_child, 'created')
			child.text 		=  	created_date
			child 			= 	SubElement(container_child, 'creator')
			child.text 		=  	created_user
			child 			= 	SubElement(container_child, 'changed')
			child.text 		=  	changed_date
			child 			= 	SubElement(container_child, 'changer')
			child.text 		=  	changed_user
			json_container['created'] 		= created_date
			json_container['creator'] 		= created_user
			json_container['changed'] 		= changed_date
			json_container['changer'] 		= changed_user
			


			if t.find('tranCtrIsDamaged',ns) != None:
				is_damage = True if t.find('tranCtrIsDamaged',ns).text == 'true' else False

			child 			= 	SubElement(container_child, 'damage')
			child.text 		=  	str(is_damage)


			# argo:tranCtrPosition/posLocId -->Old
			# tranFlexString02
			if t.find('tranFlexString02',ns) != None :
				position = t.find('tranFlexString02',ns).text
			new_position	= 	'%s-%s' % (position[:3],position[3:5])
			child 			= 	SubElement(container_child, 'position')
			child.text 		=  	new_position
			json_container['position'] 		= new_position

			if t.find('argo:tranCtrDmg/dmgitemTypeDescription',ns) != None :
				damage = t.find('argo:tranCtrDmg/dmgitemTypeDescription',ns).text
			else :
				damage = ''
			
			child 			= 	SubElement(container_child, 'damage')
			child.text 		=  	damage
			json_container['damage'] 		= damage

			# UnitCategoryEnum[STRGE]
			# UnitCategoryEnum[EXPRT]
			# "EXPRT" (or) "IMPRT" (or) "TRSHP" (or)"STRGE".
			if t.find('tranUnitCategory',ns) != None:
				category = t.find('tranUnitCategory',ns).text

			child 			= 	SubElement(container_child, 'category')
			child.text 		=  	category.replace('UnitCategoryEnum','')
			json_container['category'] 		= category.replace('UnitCategoryEnum','')

			if t.find('tranSealNbr1',ns) != None :
				seal1 = t.find('tranSealNbr1',ns).text
			else :
				seal1 =''

			child 			= 	SubElement(container_child, 'seal1')
			child.text 		=  	seal1
			json_container['seal1'] 		= seal1

			if t.find('tranSealNbr2',ns) != None :
				seal2 = t.find('tranSealNbr2',ns).text
			else :
				seal2 = ''

			child 			= 	SubElement(container_child, 'seal2')
			child.text 		=  	seal2
			json_container['seal2'] 		= seal2

			# <tranUnitFlexString01>B1</tranUnitFlexString01>
			if t.find('tranUnitFlexString01',ns) != None:
				terminal = t.find('tranUnitFlexString01',ns).text
			else :
				terminal = ''
			json_container['terminal'] 		= terminal

			if t.find('tranTempRequired',ns) != None:
				temperature = t.find('tranTempRequired',ns).text
			else :
				temperature = ''
			json_container['temperature'] 		= temperature
			
			containers.append(json_container)

			print ('%s-%s-%s-%s-%s-%s-%s-%s-%s' % (container,iso,is_damage,position,
												category.replace('UnitCategoryEnum',''),seal1,seal2,damage,iso_text))
		# print ('Done')
		# app.logger.warning('Done')
		# app.logger.error('testing error log')
		# app.logger.info('testing info log')
		# print (prettify(top))

		# Save to file (naming should be IP of requested computer)
		# file1 = open("print.xml","w+")
		# file1.write(prettify(top))
		# file1.close()


		# Save to json
		ttl = 60*60 #60*60*24 *365 #31104000 #one year in seconds
		json_data['terminal'] = terminal
		json_data['containers'] = containers
		json_data['ttl'] = ttl

		file2 = open("print.json","w+")
		file2.write(json.dumps(json_data, indent=4, sort_keys=True))
		file2.close()
		# save to redis
		
		# event["ttl"] = db.ttl(path)
		
		db.set(license_number,json.dumps(json_data) ) #store dict in a hashjson.dumps(json_data)
		db.expire(license_number, ttl) #expire it after a year
		db.publish(json_data['printer'].lower(),license_number)
		# -------------------------------------------------------

		return_msg = '%s - %s container(s) - save successful!(%s)' % (license_number,
													len(truck_trans_nodes),
													g.request_time())
		app.logger.info(return_msg)
		return return_msg,200

	except Exception as e:
		app.logger.error('%s - %s' % (license_number,e))
		return '%s' % e,500
	


	


if __name__ == '__main__':
	app.run(host='0.0.0.0',debug=True)
	# serve(app, host='0.0.0.0', port=8013)