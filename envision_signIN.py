#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from __future__ import print_function
import wx
import wx.lib.inspection
from wx.lib.pubsub import pub #used to "listen" for messages sent by spawned GUI windows
import threading, subprocess, signal #used for threading external programs
import socket #communicate, via a socket, to external (or local!) server
import wx.lib.agw.pybusyinfo as PBI
import os, time, sys #basic OS functions
import serial
import paho.mqtt.client as mqtt

#platform check, useful for GUI layout
if wx.Platform == "__WXMSW__":
	MSW = True
	GTK = False
else:
	GTK = True
	MSW = False
NUMSTUDENTS = 30
NUMCOLUMNS = 2
READER_LENGTH = 39
ASCII_START = 37
ASCII_END = 63
IDLENGTH = 10
MACHINENAME = "LECTURE_ROSTER-IN"
SERVERADDRESS='envision-local'
SERVERPORT=6969
MQTT_SERVER_IP = "envision-local"
MQTT_PORT = 1883
MQTT_SIGN_IN_TOPIC   = "envision/front_desk/sign_in"

class MyDialog(wx.Dialog):
	def __init__(self, parent, banner, msg):
		#wx.Dialog.__init__(self, parent, wx.ID_ANY, banner, size=wx.DefaultSize, pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE)
		self.parent = parent
		pre = wx.PreDialog()
		pre.Create(parent, wx.ID_ANY, banner, wx.DefaultPosition, wx.DefaultSize, wx.DEFAULT_DIALOG_STYLE)
		self.PostCreate(pre)
		sizer = wx.BoxSizer(wx.VERTICAL)

		label = wx.StaticText(self,-1,msg)
		sizer.Add(label, 1, wx.ALIGN_CENTRE|wx.ALL, 5)
		btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		sizer.Add(btn_sizer, 1, wx.ALIGN_RIGHT)
		no_btn = wx.FindWindowById(wx.ID_NO,self)
		
		self.Bind(wx.EVT_CLOSE, self.OnClose)
		self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
		self.SetSizerAndFit(sizer)
		self.Layout()
		sizer.Fit(self)

	def OnClose(self, event):
		print('In OnClose')
		event.Skip()

	def OnDestroy(self, event):
		print('In OnDestroy')
		self.parent.focusPanel.SetFocus()
		event.Skip()

class SocketThread(threading.Thread):
	#initializer, takes parent and a message as inputs
	def __init__(self,parent,message):
		threading.Thread.__init__(self)
		self.parent=parent
		self.message=message
		self.runFlag = True #run Flag indicates the thread is still running. Can be called externally to end the thread
	#called automatically by the start() function (implicitly defined by the threading class)... required
	def run(self):
		pass
	#use this function to send message through the socket to the server. Function expects a packet length of 3
	def sendEvent(self,eventPacket):
		wx.CallAfter(self.parent.contactServer)
		wx.GetApp().ProcessPendingEvents()
		# convert all messages to uppercase
		packet = [x.upper() for x in eventPacket]
		#form the list into a string delineated by a SPACE 
		packetStr = ' '.join(packet)
		try:

			#connect to the server on the port specified
			client = socket.create_connection((SERVERADDRESS, SERVERPORT))
			#send the packet string
			client.send(packetStr)
			#receive a response in a buffer, and split string into a list
			reply=(client.recv(1024)).split()
			wx.CallAfter(self.parent.closeSocket)
			wx.GetApp().ProcessPendingEvents()
		except Exception, msg:
			#call this function if the connection was a failure
			wx.CallAfter(self.parent.closeSocket)
			wx.CallAfter(self.parent.socketClosed,wx.EVT_CLOSE,msg)
		else:
			if len(reply) == 3:
			#make sure the reply packet is properly formed
				if reply[0] == packet[0] and reply[1]:
				#make sure the correct packet was received by comparing the outgoing and the incoming EVENT (EVT)
					#send the reply to the pub listener "socketListener"
					pub.sendMessage("socketListener", sent=packet, reply=reply)
			else:
				#alert the GUI that the packet was incorrect
				wx.CallAfter(self.parent.socketClosed,wx.EVT_CLOSE,"BAD-FORMED REPLY")
	#action to take on closing the socket 
	def closeSocket(self):
		try:
			client.shutdown(socket.SHUT_RDWR)
			client.close()
		except Exception, msg:
			#force close on an exception
			wx.CallAfter(self.parent.socketClosed,wx.EVT_CLOSE,msg)

class Student:
	def __init__(self,parent,num):
		#spacer = 5*" "
		#initText = spacer+"LAST NAME, FIRST INITIAL PID: ****0000"+str(num)
		fontSize = 15
		studentFont = wx.Font(fontSize,wx.FONTFAMILY_SWISS,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL)
		parent = parent
		self.index = num
		self.rowPanel = wx.Panel(parent.panel_1, wx.ID_ANY)
		self.linePanel = wx.Panel(parent.panel_1, wx.ID_ANY)
		self.rowSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.lineSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.lnameDefault = 20*"-"
		self.fnameDefault = 5*"-"
		self.pidCellDefault = 10*"-"
		self.lnameCell = wx.StaticText(self.rowPanel, label=self.lnameDefault, style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.fnameCell = wx.StaticText(self.rowPanel, label=self.fnameDefault, style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.pidCell = wx.StaticText(self.rowPanel, label=self.pidCellDefault, style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.cellLine = wx.StaticLine(self.linePanel, style=wx.LI_HORIZONTAL)
		self.signedInButton = wx.StaticBitmap(self.rowPanel, wx.ID_ANY, app.bitmaps["gray"], style = wx.NO_BORDER | wx.ALIGN_CENTRE)
		self.signedOutButton = wx.StaticBitmap(self.rowPanel, wx.ID_ANY, app.bitmaps["gray"], style = wx.NO_BORDER | wx.ALIGN_CENTRE)
		self.lnameCell.SetFont(studentFont)
		self.fnameCell.SetFont(studentFont)
		self.pidCell.SetFont(studentFont)
		self.status = None
		self.pid = None

class MainWindow(wx.Frame):
	def __init__(self):
		self.inputList = [] #stores keyboard characters as they come in
		self.acceptString = False #will the panel accept keyboard input?
		self.classList = []
		self.classHeaders = ["section_id","course","number","day","startTime","endTime"]
		self.currentSection = False
		self.userIDnumber = None

		styleFlags = wx.DEFAULT_FRAME_STYLE # | wx.NO_BORDER# | wx.FRAME_NO_TASKBAR
		if GTK:
			styleFlags = wx.DEFAULT_FRAME_STYLE# | wx.STAY_ON_TOP
		wx.Frame.__init__(self, None, title = "EnVision Client Machines", style=styleFlags)
		
		#Think I finally fixed the 'need focus' issue by creating a separate, empty panel 
		#that has the main panel as a parent
		#this seems to capture evt_char AND doesn't lose focus (yet)...it loses focus randomly. Somehow tied to the hidden text control spawning modal dialogs
		self.panel_1 = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_RAISED)
		self.focusPanel = wx.Panel(self.panel_1, wx.ID_ANY, style=wx.WANTS_CHARS)
		
		self.rows = []
		self.columns = []
		self.firstLineSizers = []
		self.firstLinePanels = []
		self.cellLines = []
		
		self.hiddenTC = wx.TextCtrl(self.panel_1, wx.ID_ANY, "", style=wx.TE_PROCESS_ENTER)
		self.hiddenTC.Hide()
		
		for i in xrange(NUMSTUDENTS):
			self.rows.append(Student(self,i))
		self.__do_layout()
		self.__set_properties()
		
		wx.CallAfter(self.OnLoad)
		
	def __do_layout(self):
		#SIZERS
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.columnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.mainSizer.Add(self.focusPanel,1,wx.EXPAND|wx.ALL,0)
		self.mainSizer.Add(self.hiddenTC,1,wx.EXPAND)
		self.mainSizer.Add(self.columnSizer,1,wx.EXPAND)
		
		for i in xrange(NUMCOLUMNS):
			self.columns.append(wx.BoxSizer(wx.VERTICAL))
			#self.columns.append(wx.StaticBoxSizer(wx.StaticBox(self.panel_1, wx.ID_ANY, ""), wx.VERTICAL))
			self.columnSizer.Add(self.columns[i],1,wx.EXPAND)
			self.firstLinePanels.append(wx.Panel(self.panel_1, wx.ID_ANY))
			self.firstLineSizers.append(wx.BoxSizer(wx.HORIZONTAL))
			self.cellLines.append(wx.StaticLine(self.firstLinePanels[i], style=wx.LI_HORIZONTAL))
			self.columns[i].Add(self.firstLinePanels[i],1,wx.EXPAND|wx.ALL,0)
			self.firstLineSizers[i].Add(self.cellLines[i],10, wx.ALIGN_CENTER_VERTICAL)
			self.firstLinePanels[i].SetSizer(self.firstLineSizers[i])
		
		for row in self.rows:
			self.columns[row.index%NUMCOLUMNS].Add(row.rowPanel,1,wx.EXPAND|wx.ALL,0)
			if row.index % NUMCOLUMNS == 0:
				row.rowSizer.Add(row.signedInButton,1, wx.TOP | wx.BOTTOM, 0)#, wx.ALL | wx.EXPAND,0)
				row.rowSizer.Add(row.signedOutButton,1, wx.TOP | wx.BOTTOM, 0)#, wx.ALL | wx.EXPAND,0)				
			row.rowSizer.Add(row.lnameCell, 3, wx.ALIGN_CENTER_VERTICAL, 0)
			row.rowSizer.Add(row.fnameCell, 2, wx.ALIGN_CENTER_VERTICAL, 0)
			row.rowSizer.Add(row.pidCell, 2, wx.ALIGN_CENTER_VERTICAL, 0)
			row.rowSizer.AddStretchSpacer(2)
			if row.index % NUMCOLUMNS != 0:
				row.rowSizer.Add(row.signedInButton,1, wx.TOP | wx.BOTTOM, 0)#, wx.ALL | wx.EXPAND,0)
				row.rowSizer.Add(row.signedOutButton,1, wx.TOP | wx.BOTTOM, 0)#, wx.ALL | wx.EXPAND,0)
			row.rowPanel.SetSizer(row.rowSizer)
			self.columns[row.index%NUMCOLUMNS].Add(row.linePanel,1,wx.EXPAND,0)
			row.lineSizer.Add(row.cellLine,10, wx.ALIGN_CENTER_VERTICAL)
			row.linePanel.SetSizer(row.lineSizer)
			#row.linePanel.SetBackgroundColour('red')
			if (row.index % 2 == 0):
				row.rowPanel.SetBackgroundColour('white')
			else:
				row.rowPanel.SetBackgroundColour('white')
		self.panel_1.SetSizer(self.mainSizer)
		self.SetMinSize((650,500))
		self.Layout()
	
	def __set_properties(self):
		# begin wxGlade: MyFrame.__set_properties
		self.SetTitle("EnVision Roster")
		self.Bind(wx.EVT_SIZE,self.onResize)
		self.focusPanel.Bind(wx.EVT_CHAR,self.onKeyPress)
		self.focusPanel.SetFocus()
		self.focusPanel.Bind(wx.EVT_KILL_FOCUS, self.onFocusLost)
		self.Bind(wx.EVT_CLOSE, self.OnExit)
		#self.Bind(wx.EVT_WINDOW_MODAL_DIALOG_CLOSED, self.OnClose)
		#establish a listener thread. This allows the GUI to respond to spawned processes. In this case the socket process
		pub.subscribe(self.socketListener, "socketListener")
		pub.subscribe(self.sectionListener,"sectionListener")
		#create a socket instance and start it
		self.socketWorker = SocketThread(self,None)
		self.socketWorker.start()
		self.lightWorker = LightThread(self)
		self.lightWorker.start()

	def onFocusLost(self,event):
		print("FOCUS LOST!")
		self.focusPanel.SetFocus()

	def OnLoad(self):
		#self.Maximize(True)
		self.ShowFullScreen(True)
		self.lightWorker.light(wx.ID_YES)
		self.socketWorker.sendEvent(["EVT_CLASSES",MACHINENAME,"False","False"])
		

	def OnExit(self,event):
		#for thread in threading.enumerate():
			#if (not thread.name.upper().startswith("MAIN")):
				#thread.stop()
		print("exiting")
		mqtt_client.disconnect()
		while (self.socketWorker.is_alive()):
			print("Killing Socket Thread")
			time.sleep(5)
		while (self.lightWorker.is_alive()):
			print("Killing Light Thread")
			time.sleep(5)
		#self.socketWorker.runFlag=False
		#self.lightWorker.runFlag=False
		self.Destroy()
		
	def OnClose(self,event):
		print("dialog closed")
	
	def onResize(self,newSize):
		winWidth = newSize.GetSize()[0] #* (2.0/3.0)
		winHeight = newSize.GetSize()[1] #* (2.0/3.0)
		print(winHeight, winWidth)
		if (winWidth > 1 and winHeight > 1):
			app.__set_bitmaps__(winWidth,winHeight)
			self.setAllStatus()
		newSize.Skip()
		self.mainSizer.Layout()
		self.panel_1.Layout()

	def onKeyPress(self, event):
		"""
		capture key events in the panel focus
		if ESC is pressed, ask for the escape code
		if any other key but the "start-key" ($) are captured
		ignore and print an error message
		"""
		#pseudo buffer for inputList
		keycode = event.GetKeyCode()
		#print chr(keycode)
		if keycode == 306:
			return
		elif len(self.inputList) > 50 or keycode > 256 or keycode== wx.WXK_RETURN:
			self.inputList=[]
			wx.MessageBox("Please Use The ID-Reader", "ERROR")
			return
		#ascii code 37 is % and is the start and trail char of the magreader
		elif keycode == wx.WXK_ESCAPE:
			self.debugTextControl()
			return
		elif keycode == ASCII_START:
			#if present, start accepting characters into the inputList
			self.acceptString = True
			#print "accepting"
		if self.acceptString:
			self.inputList.append(keycode)
			#print [chr(i) for i in self.inputList], self.inputList
			#print len(self.inputList)
			if len(self.inputList) == READER_LENGTH:
				if self.inputList[-1] == ASCII_END:
					#join the character together in a string
					inputString = ''.join(chr(i) for i in self.inputList[3:13])
					#print inputString
					self.idEnter(inputString)
					#reset the capture variables
					self.acceptString = False
					self.inputList = []
		#ignore all strings that don't start with '$'
		else:
			wx.MessageBox("Please Use The ID-Reader!", "ERROR")
		#event.Skip()
		self.focusPanel.SetFocus()

	def idEnter(self, idInput):
		idList = list(idInput)
		if idList[1] == '9':
		#magstripe reads a '09' for students, replace this with a 'A' per UCSD standards
			idList[1]='A'
		if idList[1] == '7':
		#magstripe reads '07' for international students, replace with something
			idList[1]='U'
			idList[2]='0'
		self.userIDnumber = ''.join(i for i in idList[1:])
		#print self.userIDnumber
		#check the ID record on the server, info slot is True/False depending on whether I want these machines in etc/hosts
		self.socketWorker.sendEvent(["EVT_ROSTER",MACHINENAME,self.userIDnumber,str(self.currentSection)]) 


	def setStatus(self):
		for student in self.rows:
			#print student.pid, self.userIDnumber
			if student.pid == self.userIDnumber:
				print(student.status)
				if student.status is None:
					student.signedInButton.SetBitmap(app.bitmaps["green"])
					student.signedOutButton.SetBitmap(app.bitmaps["red"])
					student.status = False
				elif student.status == False:
					student.signedInButton.SetBitmap(app.bitmaps["green"])
					student.signedOutButton.SetBitmap(app.bitmaps["green"])
					student.status = True
				student.rowSizer.Layout()
				break
		#self.mainSizer.Layout()

	def setAllStatus(self):
		for row in self.rows:
			if row.status is None:
				row.signedInButton.SetBitmap(app.bitmaps["gray"])
				row.signedOutButton.SetBitmap(app.bitmaps["gray"])
			elif row.status == False:
				row.signedInButton.SetBitmap(app.bitmaps["green"])
				row.signedOutButton.SetBitmap(app.bitmaps["red"])
			elif row.status == True:
				row.signedInButton.SetBitmap(app.bitmaps["green"])
				row.signedOutButton.SetBitmap(app.bitmaps["green"])
			row.rowSizer.Layout()

	def debugTextControl(self):
		self.focusPanel.Unbind(wx.EVT_CHAR)
		self.focusPanel.Unbind(wx.EVT_KILL_FOCUS)
		self.hiddenTC.Show()
		self.mainSizer.Layout()
		self.Layout()
		self.hiddenTC.SetFocus()
		self.hiddenTC.Bind(wx.EVT_TEXT_ENTER, self.processTextBox)
	def processTextBox(self,event):
		
		debugString=self.hiddenTC.GetLineText(0)
		self.hiddenTC.Clear()
		self.hiddenTC.Hide()
		#print debugString
		self.hiddenTC.Unbind(wx.EVT_TEXT_ENTER)
		self.focusPanel.Bind(wx.EVT_CHAR,self.onKeyPress)
		self.focusPanel.Bind(wx.EVT_KILL_FOCUS, self.onFocusLost)
		self.focusPanel.SetFocus()
		#wx.CallAfter(self.hiddenTC.Hide)
		#wx.GetApp().ProcessPendingEvents()
		self.mainSizer.Layout()
		self.Layout()
		if debugString == "e4ms":
			self.OnExit(wx.EVT_CLOSE)
		else:
			self.userIDnumber=debugString
			self.socketWorker.sendEvent(["EVT_ROSTER",MACHINENAME,self.userIDnumber,str(self.currentSection)])
		
	def sectionListener(self,selected):
		#self.choiceFrame.onExit(wx.EVT_CLOSE)
		msg = "I certify that I will: \n\n- Enforce cleaning protocols; \n- Monitor social distancing and mask usage"
		agreeDlg = MyDialog(self,"Open Class?",msg)
		agreeDlg.CenterOnScreen()
		result = agreeDlg.ShowModal()
		agreeDlg.Destroy()
		if result == wx.ID_OK:
			#self.focusPanel.SetFocus()
			self.currentSection = self.classList[selected]["section_id"]
			self.socketWorker.sendEvent(["EVT_OPENCLASS",MACHINENAME,self.userIDnumber,self.currentSection])
		elif result == wx.ID_CANCEL:
			pass
			#self.focusPanel.SetFocus()
	
	#this function listens to the published messages from the socket process
	def socketListener(self, sent=None, reply=None):
	#function expects two lists of strings 
		#set variables for clarity
		command = sent[0]
		user = sent[1]
		machine = sent[2]
		machineTime = sent[3]
		
		event = reply[0]
		status = reply[1]
		statusInfo = reply[2]
		
		if status == "OK":
		#checks if the command was accepted
			self.processReply(event,statusInfo)
		elif status == "DENY":
		#checks if the command was rejected
			self.processDeny(event, statusInfo)
		elif status == "DBERROR":
		#problem with the process directive on the socketServer, this will resend the packet indefinitely (YIKES)
			#time.sleep(3)
			#self.socketWorker.sendEvent(command,user,machine,machineTime)
			errorMsg = "DATABASE ERROR\n\n Please try again"
			wx.MessageBox(errorMsg,"ERROR")

	def contactServer(self):
		message = "Contacting Server..."
		self.busyMsg = PBI.PyBusyInfo(message, parent=None, title=" ")
		time.sleep(0.1)
		try:
			wx.Yield()
		except Exception as e:
			print(e)
	def closeSocket(self):
		self.busyMsg = None
		self.focusPanel.SetFocus()
		

	def socketClosed(self, event, errorMsg):
		self.Show()
		self.Raise()
		errorMsg = str(errorMsg)
		errorDlg = wx.MessageDialog(self, "Connection to SERVER failed!\n\n"+errorMsg+"\n\nPlease see an Administrator", "ERROR", wx.OK | wx.ICON_ERROR | wx.CENTER)
		result = errorDlg.ShowModal()
		#wx.CallAfter(agreeDlg.EndModal,result)
		#errorDlg.Close()
		errorDlg.Destroy()
		if result == wx.ID_OK:
			pass
	#called after the socketlistener determines the packets were properly formed, and were accepted by the server
	def processReply(self, command, info):
		#function expects two strings: the command and the information returned by the server
		infoList = info.split("|") #split the info string into a list, delineated by | ... 
		#extraneous info is often bundled together in one string to keep the reply packet uniform
		if command == "EVT_CLASSES":
			self.setClasses(infoList)
		elif command == "EVT_ROSTER":
			if infoList[0] == "SUPERVISOR":
				self.openSection()
			else:
				self.lightWorker.light(wx.ID_YES)
				self.setStatus()
		elif command == "EVT_OPENCLASS":
			self.lightWorker.light(wx.ID_YES)
			self.setRoster(infoList)
			#print self.classList
		elif command == "EVT_RESTORE":
			self.restoreRoster(infoList)
		elif command == "EVT_CLOSECLASS":
			self.lightWorker.light(wx.ID_YES)
			self.resetRoster()
			self.currentSection = False

	#this function is called if the socketListener determines that the packet was processed but not approved by the server
	def processDeny(self,command, error):
		#functions expects two lists, one command and containing any relevant error messages
		errorList = error.split("|")
		if command == "EVT_ROSTER":
			if errorList[0] == "SUPERVISOR":
				self.closeSection()
			elif errorList[0] == "NOTENROLLED":
				self.lightWorker.light(wx.ID_NO)
				wx.MessageBox("You are not enrolled in this section", "ERROR")
			elif errorList[0] == "CLOSED":
				self.lightWorker.light(wx.ID_NO)
				wx.MessageBox("Only supervisors can open sections", "ERROR")
		elif command == "EVT_CLASSES":
			self.currentSection = errorList.pop()
			self.setClasses(errorList)
			self.socketWorker.sendEvent(["EVT_RESTORE",MACHINENAME,"False",self.currentSection])

	def setClasses(self,infoList):
		for section in infoList:
			sectionInfo = section.split(",")
			self.classList.append([])
			self.classList[-1]={}
			for i,detail in enumerate(sectionInfo):
				self.classList[-1][self.classHeaders[i]]=detail

	def setRoster(self,roster):
		for i,student in enumerate(roster):
			if i>NUMSTUDENTS:
				break
			else:
				studentInfo = student.split("~")
				self.rows[i].pidCell.SetLabel(studentInfo[0][0]+5*"*"+studentInfo[0][6:])
				self.rows[i].pid = studentInfo[0]
				self.rows[i].lnameCell.SetLabel(studentInfo[1].split(",")[0])
				firstName = studentInfo[1].split(",")[1].lstrip("_").rstrip("_").split("_")
				nameString = ""
				for names in firstName:
					nameString += names[0]+"."
				self.rows[i].fnameCell.SetLabel(nameString)
				self.rows[i].rowSizer.Layout()
	def restoreRoster(self,roster):
		
		for i,student in enumerate(roster):
			if i>NUMSTUDENTS:
				break
			else:
				studentInfo = student.split("~")
				self.rows[i].pidCell.SetLabel(studentInfo[0][0]+5*"*"+studentInfo[0][6:])
				self.rows[i].pid = studentInfo[0]
				self.rows[i].lnameCell.SetLabel(studentInfo[1].split(",")[0])
				firstName = studentInfo[1].split(",")[1].lstrip("_").rstrip("_").split("_")
				nameString = ""
				for names in firstName:
					nameString += names[0]+"."
				self.rows[i].fnameCell.SetLabel(nameString)
				#print studentInfo[2], studentInfo[3]
				if studentInfo[2] != "NONE":
					self.rows[i].status = False
				if studentInfo[3] != "NONE":
					self.rows[i].status = True
				self.rows[i].rowSizer.Layout()
		self.setAllStatus()
		self.mainSizer.Layout()
		self.panel_1.Layout()
	def resetRoster(self):
		for student in self.rows:
			student.pidCell.SetLabel(student.pidCellDefault)
			student.lnameCell.SetLabel(student.lnameDefault)
			student.fnameCell.SetLabel(student.fnameDefault)
			student.status = None
			student.pid = None
		self.setAllStatus()
		self.mainSizer.Layout()
		self.panel_1.Layout()
	def openSection(self):
		#self.choiceFrame = choiceFrame(self,self.classList)
		#results = self.choiceFrame.ShowModal()
		#self.choiceFrame.MakeModal(True)
		classChoices = []
		for section in self.classList:
			sectionString = "Section: " +section["section_id"] + " -- " + section["course"]+section["number"]+", "+section["startTime"]+"-"+section["endTime"]
			classChoices.append(sectionString)
		choiceDlg = wx.SingleChoiceDialog(self,"Please Select Section to Open","Section",classChoices)
		result = choiceDlg.ShowModal()
		choiceDlg.Destroy()
		if result == wx.ID_OK:
			sectionChoice = choiceDlg.GetSelection()
			print(sectionChoice)
			pub.sendMessage("sectionListener", selected=sectionChoice)
	def closeSection(self):
		missingStudents = []
		for student in self.rows:
			if student.status == False:
				#check for students that haven't signed out...I'd like to move this check to the Server....maybe?
				missingStudents.append(", ".join([student.lnameCell.GetLabel(),student.fnameCell.GetLabel()]))
		if missingStudents:
			self.lightWorker.light(wx.ID_NO)
			msg = "There are\n" + str(len(missingStudents)) + " students that have not signed out: \n- " + '\n- '.join(i for i in missingStudents)
			agreeDlg = MyDialog(self,"Proceed?",msg)
			agreeDlg.CenterOnScreen()
			result = agreeDlg.ShowModal()
			agreeDlg.Destroy()
			if result == wx.ID_OK:
				closeSectionMSG = True
			elif result == wx.ID_CANCEL:
				closeSectionMSG = False
		else:
				closeSectionMSG = True
		if closeSectionMSG:
			msg = "I certify that: \n\n- All equipment and furniture has been cleaned; \n- All students have cleared the room" 
			agreeDlg = MyDialog(self,"Proceed?",msg)
			agreeDlg.CenterOnScreen()
			result = agreeDlg.ShowModal()
			agreeDlg.Destroy()
			if result == wx.ID_OK:
				self.socketWorker.sendEvent(["EVT_CLOSECLASS",MACHINENAME,self.userIDnumber,self.currentSection])
			elif result == wx.ID_NO:
				pass
		
class MyApp(wx.App):
	def OnInit(self):
		self.bitmaps = {}
		self.rows = NUMSTUDENTS / NUMCOLUMNS
		self.totalWidth = 100
		self.nameWidth = 80
		self.buttonWidth = self.totalWidth - self.nameWidth
		self.rowPadding = 10
		self.__set_bitmaps__()
		return True
	
	def __set_bitmaps__(self,dw=400,dh=1200):
		imageDir = "./images/"
		imageList = ["red_button.png","green_button.png","gray_button.png"]
		bitmaps = []
		bitmap_padding = 0
		bitmapVpadding = 1
		bitmapWidth = (dw * self.buttonWidth / (2 * self.totalWidth)) - (2 * bitmap_padding)
		bitmapHeight = (dh / self.rows) - (self.rowPadding) 
		if bitmapHeight < bitmapWidth:
			limitingDim = bitmapHeight
			heightLimit = True
		else:
			limitingDim = bitmapWidth
			heightLimit = False
		for image in imageList:
			bitmap = wx.Image(imageDir + image)
			W, H = bitmap.GetSize()
			proportion = float(W) / float(H)
			if heightLimit:
				scaleH = limitingDim
				scaleW = scaleH * proportion
			else:
				scaleW = limitingDim
				scaleH = scaleW * proportion
			#print (scaleW,scaleH)
			if scaleW > 0 and scaleH > 0:
				bitmap = bitmap.Scale(scaleW, scaleH, wx.IMAGE_QUALITY_HIGH)
			try:
				bitmaps.append(wx.Bitmap(bitmap))
			except:
				bitmaps.append(wx.BitmapFromImage(bitmap))
				mask = wx.Mask(bitmaps[-1], wx.WHITE)
				bitmaps[-1].SetMask(mask)
			
		self.bitmaps = {"gray":bitmaps[2], "green":bitmaps[1], "red":bitmaps[0]}
# end of class MyApp

#thread to run the light towers
class LightThread(threading.Thread):
	#initializer function that takes a parent and user selection value as input
	def __init__(self,parent):
		threading.Thread.__init__(self)
		self.parent = parent
		self.response=None
		self.runFlag = True #run Flag indicates the thread is still running. Can be called externally to end the thread
	#not needed but may add functionality in the future
	def stop(self):
		pass
	#required function by threading.start(), light() is redundant but may add some future-proofing
	def run(self):
		pass
	#function to turn the specified light on and off 
	def light(self,value):
		if value == wx.ID_YES:
			try:
				mqtt_client.publish(MQTT_SIGN_IN_TOPIC, "<OK>");
				#pass
			except:
				print("[MQTT Client]: MQTT Publish Failed")
		elif value == wx.ID_NO:
			try:
				mqtt_client.publish(MQTT_SIGN_IN_TOPIC, "<DENY>");
				#pass
			except:
				print("[MQTT Client]: MQTT Publish Failed")

if __name__ == "__main__":
	mqtt_client = mqtt.Client()
	mqtt_client.on_connect = lambda client, userdata, flags, rc: print("MQTT connected to IP " + MQTT_SERVER_IP)
	try:
		mqtt_client.connect(MQTT_SERVER_IP, MQTT_PORT, 5)
		mqtt_client.loop_start();
	except:
		print("[MQTT Client]: Connection to MQTT client failed, proceeding w/o MQTT functionality")
	app = MyApp(0)
	app.frame = MainWindow()
	app.frame.Show()
	#wx.lib.inspection.InspectionTool().Show()
	app.MainLoop()