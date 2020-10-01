#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import wx
import wx.lib.inspection
from wx.lib.pubsub import pub #used to "listen" for messages sent by spawned GUI windows
import threading, subprocess, signal #used for threading external programs
import socket #communicate, via a socket, to external (or local!) server
import wx.lib.agw.pybusyinfo as PBI
import os, time, sys #basic OS functions

#platform check, useful for GUI layout
if wx.Platform == "__WXMSW__":
	MSW = True
	GTK = False
else:
	GTK = True
	MSW = False
NUMSTUDENTS = 20
SIZERPAD = 10
READER_LENGTH = 39
ASCII_START = 37
ASCII_END = 63
IDLENGTH = 10
MACHINENAME = "LECTURE_ROSTER-IN"
SERVERADDRESS='envision-local'
SERVERPORT=6969

class SocketThread(threading.Thread):
	#initializer, takes parent and a message as inputs
	def __init__(self,parent,message):
		threading.Thread.__init__(self)
		self.parent=parent
		self.message=message
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
		self.lnameCell = wx.StaticText(self.rowPanel, label=20*"-", style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.fnameCell = wx.StaticText(self.rowPanel, label=5*"-", style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.pidCell = wx.StaticText(self.rowPanel, label=10*"-", style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.cellLine = wx.StaticLine(self.linePanel, style=wx.LI_HORIZONTAL)
		self.signedInButton = wx.StaticBitmap(self.rowPanel, wx.ID_ANY, app.bitmaps["gray"], style = wx.NO_BORDER | wx.ALIGN_CENTRE)
		self.signedOutButton = wx.StaticBitmap(self.rowPanel, wx.ID_ANY, app.bitmaps["gray"], style = wx.NO_BORDER | wx.ALIGN_CENTRE)
		self.lnameCell.SetFont(studentFont)
		self.fnameCell.SetFont(studentFont)
		self.pidCell.SetFont(studentFont)
		self.status = None

class MainWindow(wx.Frame):
	def __init__(self):
		self.inputList = [] #stores keyboard characters as they come in
		self.acceptString = False #will the panel accept keyboard input?
		self.classList = []
		self.classHeaders = ["section_id","course","number","day","startTime","endTime"]
		self.sectionOpen = False
		self.currentSection = None

		styleFlags = wx.DEFAULT_FRAME_STYLE # | wx.NO_BORDER# | wx.FRAME_NO_TASKBAR
		if GTK:
			styleFlags = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
		wx.Frame.__init__(self, None, title = "EnVision Client Machines", style=styleFlags)
		
		#Think I finally fixed the 'need focus' issue by creating a separate, empty panel 
		#that has the main panel as a parent
		#this seems to capture evt_char AND doesn't lose focus (yet)
		self.panel_1 = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_RAISED)
		self.focusPanel = wx.Panel(self.panel_1, wx.ID_ANY, style=wx.WANTS_CHARS)
		
		self.rows = []
		self.firstLinePanel = wx.Panel(self.panel_1, wx.ID_ANY)
		self.firstLineSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.cellLine = wx.StaticLine(self.firstLinePanel, style=wx.LI_HORIZONTAL)
		self.hiddenTC = wx.TextCtrl(self.panel_1, wx.ID_ANY, "", style=wx.TE_PROCESS_ENTER)
		self.hiddenTC.Hide()
		
		#establish a listener thread. This allows the GUI to respond to spawned processes. In this case the socket process
		pub.subscribe(self.socketListener, "socketListener")
		pub.subscribe(self.sectionListener,"sectionListener")
		#create a socket instance and start it
		self.socketWorker = SocketThread(self,None)
		self.socketWorker.start()
		
		for i in xrange(NUMSTUDENTS):
			self.rows.append(Student(self,i))
		self.__do_layout()
		self.__set_properties()
		
		wx.CallAfter(self.OnLoad)
		
	def __do_layout(self):
		#SIZERS
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.mainSizer.Add(self.focusPanel,1,wx.EXPAND|wx.ALL,0)
		
		self.mainSizer.Add(self.firstLinePanel,1,wx.EXPAND|wx.ALL,0)
		self.firstLineSizer.Add(self.cellLine,10, wx.ALIGN_CENTER_VERTICAL)
		self.firstLinePanel.SetSizer(self.firstLineSizer)
		
		for row in self.rows:
			self.mainSizer.Add(row.rowPanel,1,wx.EXPAND|wx.ALL,0)
			row.rowSizer.Add(row.lnameCell, 3, wx.ALIGN_CENTER_VERTICAL, 0)
			row.rowSizer.Add(row.fnameCell, 2, wx.ALIGN_CENTER_VERTICAL, 0)
			row.rowSizer.Add(row.pidCell, 2, wx.ALIGN_CENTER_VERTICAL, 0)
			row.rowSizer.AddStretchSpacer(2)
			row.rowSizer.Add(row.signedInButton,1, wx.TOP | wx.BOTTOM, 0)#, wx.ALL | wx.EXPAND,0)
			row.rowSizer.Add(row.signedOutButton,1, wx.TOP | wx.BOTTOM, 0)#, wx.ALL | wx.EXPAND,0)
			row.rowPanel.SetSizer(row.rowSizer)
			self.mainSizer.Add(row.linePanel,1,wx.EXPAND,0)
			row.lineSizer.Add(row.cellLine,10, wx.ALIGN_CENTER_VERTICAL)
			row.linePanel.SetSizer(row.lineSizer)
			#row.linePanel.SetBackgroundColour('red')
			if (row.index % 2 == 0):
				row.rowPanel.SetBackgroundColour('white')
			else:
				row.rowPanel.SetBackgroundColour('white')
		self.mainSizer.Add(self.hiddenTC,1,wx.EXPAND)
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

	def onFocusLost(self,event):
		#print "FOCUS LOST!"
		if self.focusPanel.FindFocus() is None:
			self.focusPanel.SetFocus()

	def OnLoad(self):
		self.socketWorker.sendEvent(["EVT_CLASSES",MACHINENAME,"False","False"])

	def OnExit(self,event):
		#for thread in threading.enumerate():
			#if (not thread.name.upper().startswith("MAIN")):
				#thread.stop()
		self.Destroy()
	
	def onResize(self,newSize):
		winWidth = newSize.GetSize()[0] #* (2.0/3.0)
		winHeight = newSize.GetSize()[1] #* (2.0/3.0)
		print (winHeight, winWidth)
		if (winWidth > 1 and winHeight > 1):
			app.__set_bitmaps__(winWidth,winHeight)
			self.setStatus()
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
		if keycode == 306:
			return
		if len(self.inputList) > 50 or keycode > 256 or keycode== wx.WXK_RETURN:
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
		if self.acceptString:
			self.inputList.append(keycode)
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
			wx.MessageBox("Please Use The ID-Reader", "ERROR")
		#event.Skip()

	def setStatus(self):
		for row in self.rows:
			if row.status is None:
				row.signedInButton.SetBitmap(app.bitmaps["gray"])
				row.signedOutButton.SetBitmap(app.bitmaps["gray"])
			elif row.status == False:
				row.signedInButton.SetBitmap(app.bitmaps["green"])
				row.signedOutButton.SetBitmap(app.bitmaps["red"])
			elif row.status == "True":
				row.signedInButton.SetBitmap(app.bitmaps["green"])
				row.signedOutButton.SetBitmap(app.bitmaps["green"])
			row.rowSizer.Layout()

	def idEnter(self, idInput):
		idList = list(idInput)
		if idList[1] == '9':
		#magstripe reads a '09' for students, replace this with a 'A' per UCSD standards
			idList[1]='A'
		if idList[1] == '7':
		#magstripe reads '07' for international students, replace with something
			idList[1]='U'
			idList[2]='0'
		idString = ''.join(i for i in idList[1:])
		print idString
		#self.userIDnumber = idList #set the current user to this ID string
		#check the ID record on the server, info slot is True/False depending on whether I want these machines in etc/hosts
		self.socketWorker.sendEvent(["EVT_ROSTER",MACHINENAME,idString,"False"]) 

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
		#print debugString
		self.hiddenTC.Hide()
		self.mainSizer.Layout()
		self.hiddenTC.Unbind(wx.EVT_TEXT_ENTER)
		self.focusPanel.Bind(wx.EVT_CHAR,self.onKeyPress)
		self.focusPanel.SetFocus()
		self.focusPanel.Bind(wx.EVT_KILL_FOCUS, self.onFocusLost)
		self.Layout()
		self.socketWorker.sendEvent(["EVT_ROSTER",MACHINENAME,debugString,"False"])
		
	def sectionListener(self,selected):
		self.choiceFrame.onExit(wx.EVT_CLOSE)
		self.currentSection = self.classList[selected]["section_id"]
		self.socketWorker.sendEvent(["EVT_OPENCLASS",MACHINENAME,"False",self.currentSection])
	
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
			print e
	def closeSocket(self):
		try:
			del self.busyMsg
		except Exception as e:
			print e
			print "busy message didn't exist"			
	def socketClosed(self, event, errorMsg):
		self.Show()
		self.Raise()
		errorMsg = str(errorMsg)
		errorDlg = wx.MessageDialog(self, "Connection to SERVER failed!\n\n"+errorMsg+"\n\nPlease see an Administrator", "ERROR", wx.OK | wx.ICON_ERROR | wx.CENTER)
		result = errorDlg.ShowModal()
		if result == wx.ID_OK:
			errorDlg.Destroy()
	#called after the socketlistener determines the packets were properly formed, and were accepted by the server
	def processReply(self, command, info):
		#function expects two strings: the command and the information returned by the server
		infoList = info.split("|") #split the info string into a list, delineated by | ... 
		#extraneous info is often bundled together in one string to keep the reply packet uniform
		if command == "EVT_CLASSES":
			self.setClasses(infoList)
		elif command == "EVT_ROSTER":
			if infoList[0] == "SUPERVISOR":
				if self.sectionOpen:
					self.closeSection()
				else:
					self.openSection()
		elif command == "EVT_OPENCLASS":
			self.setRoster(infoList)
			#print self.classList
		elif command == "EVT_RESTORE":
			self.setRoster(infoList)

	#this function is called if the socketListener determines that the packet was processed but not approved by the server
	def processDeny(self,command, error):
		#functions expects two lists, one command and containing any relevant error messages
		errorList = error.split("|")
		if command == "EVT_CHECKID":
		#if check id fails, explain why
			if errorList[0] == "WAIVER":
				errorMsg = 'Your Responsbility Contract has expired! (>90 days)\n\nPlease log into the EnVision Portal to complete'
			elif errorList[0] == "GRAD":
				errorMsg = "Engineering Graduate Use is Restricted \n\n Please see an admin for other options on campus"
			elif errorList[0] == "CERT":
				errorMsg = "You have not completed the training for this machine!\n\nPlease log into the EnVision Portal to complete"
			else:
				errorMsg = error
		elif command == "EVT_CLASSES":
			#currentSection = errorList.pop()
			self.setClasses(errorList)
			self.socketWorker.sendEvent(["EVT_RESTORE",MACHINENAME,"False","False"])

	def setClasses(self,infoList):
		for section in infoList:
			sectionInfo = section.split(",")
			self.classList.append([])
			self.classList[-1]={}
			for i,detail in enumerate(sectionInfo):
				self.classList[-1][self.classHeaders[i]]=detail

	def setRoster(self,roster):
		agreeDlg = wx.MessageDialog(self, "I certify that I will: \n- Enforce cleaning protocols; \n - Monitor social distancing and mask usage", "Open Class?", wx.YES_NO | wx.CENTRE | wx.ICON_QUESTION)
		result = agreeDlg.ShowModal()
		agreeDlg.Close()
		agreeDlg.Destroy()
		if result == wx.ID_YES:
			for i,student in enumerate(roster):
				if i>20:
					break
				else:
					studentInfo = student.split(":")
					self.rows[i].pidCell.SetLabel(studentInfo[0][0]+5*"*"+studentInfo[0][6:])
					self.rows[i].lnameCell.SetLabel(studentInfo[1].split(",")[0])
					firstName = studentInfo[1].split(",")[1].lstrip("_").rstrip("_").split("_")
					nameString = ""
					for names in firstName:
						nameString += names[0]+"."
					self.rows[i].fnameCell.SetLabel(nameString)
					self.rows[i].rowSizer.Layout()
		elif result == wx.ID_NO:
			pass
	
	def restoreRoster(self,roster):
		for i,student in enumerate(roster):
			if i>20:
				break
			else:
				studentInfo = student.split(":")
				self.rows[i].pidCell.SetLabel(studentInfo[0][0]+5*"*"+studentInfo[0][6:])
				self.rows[i].lnameCell.SetLabel(studentInfo[1].split(",")[0])
				firstName = studentInfo[1].split(",")[1].lstrip("_").rstrip("_").split("_")
				nameString = ""
				for names in firstName:
					nameString += names[0]+"."
				self.rows[i].fnameCell.SetLabel(nameString)
				if studentInfo[2] != "None":
					self.rows[i].status = False
				if studentInfo[3] != "None":
					self.rows[i].status = True
				self.rows[i].rowSizer.Layout()
		self.setStatus()
		self.mainSizer.Layout()
		self.panel_1.Layout()
	def openSection(self):
		self.choiceFrame = choiceFrame(self,self.classList)
		self.choiceFrame.Show()
	def closeSection(self):
		pass

class choiceFrame(wx.Frame):
	def __init__(self,parent,classList):
		"""Constructor"""
		wx.Frame.__init__(self, parent, style= wx.STAY_ON_TOP | wx.NO_BORDER | wx.FRAME_NO_TASKBAR | wx.FRAME_FLOAT_ON_PARENT, title="More Time?",size=(400,250))
		#wx.Dialog.__init__(self,parent,style= wx.STAY_ON_TOP, title = "MORE TIME?", size = (400,200))
		self.panel = wx.Panel(self,style=wx.SUNKEN_BORDER,size=(400,250))
		self.parent = parent
		self.classChoices = []
		self.message = "Please Select Section To Open"
		self.choiceMessage = wx.StaticText(self.panel,label=self.message,style=wx.ALIGN_CENTRE_VERTICAL|wx.ST_NO_AUTORESIZE)
		for section in classList:
			sectionString = "Section: " +section["section_id"] + " -- " + section["course"]+section["number"]+", "+section["startTime"]+"-"+section["endTime"]
			self.classChoices.append(sectionString)
		print self.classChoices
		self.radioText = 10*"." + "Choose Section" + 10*"."
		self.__do_layout()
		self.__set_properties()
		self.MakeModal(True)

	def __do_layout(self):
		sizer_1 = wx.BoxSizer(wx.VERTICAL)
		#self.nameCell = wx.StaticText(self.panel, label="", style=wx.ALIGN_CENTRE_VERTICAL|wx.ST_NO_AUTORESIZE)
		self.radio_box_1 = wx.RadioBox(self.panel, wx.ID_ANY, "", choices=self.classChoices, majorDimension=1, style=wx.RA_SPECIFY_COLS)
		self.radio_box_1.SetFocus()
		self.radio_box_1.SetSelection(0)
		sizer_1.Add(self.choiceMessage,1, wx.ALIGN_CENTRE_HORIZONTAL)
		sizer_1.Add(self.radio_box_1, 2, wx.EXPAND, 0)
		#sizer_1.Add(0,0,1)
		sizer_1.AddStretchSpacer(1)
		sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
		sizer_1.Add(sizer_2, 1, wx.EXPAND, 0)
		sizer_1.AddStretchSpacer(1)

		sizer_2.AddStretchSpacer(3)

		self.okButton = wx.Button(self.panel, wx.ID_ANY, "PROCEED")
		sizer_2.Add(self.okButton, 2, 0, 0)

		sizer_2.AddStretchSpacer(1)

		self.cancelButton = wx.Button(self.panel, wx.ID_ANY, "CANCEL")
		sizer_2.Add(self.cancelButton, 2, 0, 0)

		sizer_2.AddStretchSpacer(3)
		choiceFont = wx.Font(20,wx.FONTFAMILY_SWISS,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL)
		buttonFont = wx.Font(20,wx.FONTFAMILY_SWISS,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_BOLD)
		self.radio_box_1.SetFont(choiceFont)
		self.okButton.SetFont(buttonFont)
		self.cancelButton.SetFont(buttonFont)

		#self.Bind(wx.EVT_SIZE,self.onResize)

		self.panel.SetSizer(sizer_1)
		sizer_1.Fit(self)
		self.SetSize((600, len(self.classChoices)*50+30))

		self.Layout()
		self.alignToCenter(self)

	def __set_properties(self):
		self.okButton.Bind(wx.EVT_BUTTON, self.onOK)
		self.cancelButton.Bind(wx.EVT_BUTTON, self.onExit)

	def alignToCenter(self,window):
	#set the window dead-center of the screen
		dw, dh = wx.DisplaySize()
		w, h = window.GetSize()
		x = dw/2 - w/2
		y = dh/2 - h/2
		window.SetPosition((x,y))
		#print dw, dh, w, h, x, y	

	def onOK(self,event):
		#self.radio_box_1.GetString(self.radio_box_1.GetSelection())
		#sectionChoice = self.radio_box_1.GetStringSelection()
		sectionChoice = self.radio_box_1.GetSelection()
		print sectionChoice
		pub.sendMessage("sectionListener", selected=sectionChoice)
		###maybe send index so I can use my classList / dict
	def onExit(self,event):
	#when the timer has ended (by user or countdown), stop the timer; destroy the frame; "stop" the thread using the stop function
		#self.EndModal(0)
		self.MakeModal(False)
		self.Destroy()
		self.parent.focusPanel.SetFocus()
		
class MyApp(wx.App):
	def OnInit(self):
		self.bitmaps = {}
		self.rows = NUMSTUDENTS
		self.totalWidth = 100
		self.nameWidth = 80
		self.buttonWidth = self.totalWidth - self.nameWidth
		self.rowPadding = 8
		self.printerFontSize = 10
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

if __name__ == "__main__":
	app = MyApp(0)
	app.frame = MainWindow()
	app.frame.Show()
	#wx.lib.inspection.InspectionTool().Show()
	app.MainLoop()