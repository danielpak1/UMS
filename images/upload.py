#! /usr/bin/env python
import os
import pysftp
import json
import datetime

now = str(datetime.datetime.now())
targetFileDir = '/var/www/makerspace/htdocs/images/'
localFileDir = '/home/e4ms/job_tracking/images/'

#username and password kepy in a seperate file for security reasons
with open(localFileDir+'../passList.txt','r') as passFile:
	passDict = json.load(passFile) 
	
#attempt to establish an sftp connection to makerspace.ucsd.edu
try:
	#establish the connection to makerspace server
	srv = pysftp.Connection(host='makerspace.ucsd.edu',username=passDict['makerspace-user'],password=passDict['makerspace-pass'])
	#attempt to place that copy on the envision server
	try:	
		srv.chdir(targetFileDir)
		srv.put(localFileDir+'schedule.png')
		srv.close()
	except Exception:
		print ("Upload Failed at",now)
	else:
		print ("Upload Success at ", now)
except Exception:
	print ("Connection to MakerSpace DB failed at %s", now)

