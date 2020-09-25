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
SERVERADDRESS='localhost'
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
		spacer = 5*" "
		initText = spacer+"LAST NAME, FIRST INITIAL PID: ****0000"+str(num)
		fontSize = 15
		studentFont = wx.Font(fontSize,wx.FONTFAMILY_SWISS,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL)
		parent = parent
		self.index = num
		self.rowPanel = wx.Panel(parent.panel_1, wx.ID_ANY)
		self.linePanel = wx.Panel(parent.panel_1, wx.ID_ANY)
		self.rowSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.lineSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.nameCell = wx.StaticText(self.rowPanel, label=initText, style=wx.ALIGN_LEFT|wx.ST_NO_AUTORESIZE)
		self.cellLine = wx.StaticLine(self.linePanel, style=wx.LI_HORIZONTAL)
		self.signedInButton = wx.StaticBitmap(self.rowPanel, wx.ID_ANY, app.bitmaps["green"], style = wx.NO_BORDER | wx.ALIGN_CENTRE)
		self.signedOutButton = wx.StaticBitmap(self.rowPanel, wx.ID_ANY, app.bitmaps["red"], style = wx.NO_BORDER | wx.ALIGN_CENTRE)
		self.nameCell.SetFont(studentFont)
		self.status = None

class MainWindow(wx.Frame):
	def __init__(self):
		self.inputList = [] #stores keyboard characters as they come in
		self.acceptString = False #will the panel accept keyboard input?

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
		#self.hiddenTC = wx.TextCtrl(self.panel_1, wx.ID_ANY, "")
		#self.hiddenTC.SetFocus()
		#self.hiddenTC.Hide()
		
		#establish a listener thread. This allows the GUI to respond to spawned processes. In this case the socket process
		pub.subscribe(self.socketListener, "socketListener")
		#create a socket instance and start it
		self.socketWorker = SocketThread(self,None)
		self.socketWorker.start()
		
		for i in xrange(NUMSTUDENTS):
			self.rows.append(Student(self,i))
		self.__do_layout()
		self.__set_properties()
		
	def __do_layout(self):
		#SIZERS
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.mainSizer.Add(self.focusPanel,1,wx.EXPAND|wx.ALL,0)
		
		self.mainSizer.Add(self.firstLinePanel,1,wx.EXPAND|wx.ALL,0)
		self.firstLineSizer.Add(self.cellLine,10, wx.ALIGN_CENTER_VERTICAL)
		self.firstLinePanel.SetSizer(self.firstLineSizer)
		for row in self.rows:
			self.mainSizer.Add(row.rowPanel,1,wx.EXPAND|wx.ALL,0)
			row.rowSizer.Add(row.nameCell, 10, wx.ALIGN_CENTER_VERTICAL, 0)
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
			for row in self.rows:
				row.signedInButton.SetBitmap(app.bitmaps["green"])
				row.signedOutButton.SetBitmap(app.bitmaps["red"])
				row.rowSizer.Layout()
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
		if len(self.inputList) > 50:
			self.inputList=[]
			return
		if keycode > 256:
			wx.MessageBox("Please Use The ID-Reader", "ERROR")
			return
		#ascii code 37 is % and is the start and trail char of the magreader
		elif keycode == ASCII_START:
			#if present, start accepting characters into the inputList
			self.acceptString = True
		if self.acceptString:
			self.inputList.append(keycode)
			if len(self.inputList) == READER_LENGTH:
				if self.inputList[-1] == ASCII_END:
					#join the character together in a string
					inputString = ''.join(chr(i) for i in self.inputList[3:13])
					print inputString
					self.idEnter(inputString)
				#reset the capture variables
				self.acceptString = False
				self.inputList = []
		#ignore all strings that don't start with '$'
		else:
			wx.MessageBox("Please Use The ID-Reader", "ERROR")
		#event.Skip()
	def idEnter(self, idInput):
		idList = list(idInput)
		if idList[1] == '9':
		#magstripe reads a '09' for students, replace this with a 'A' per UCSD standards
			idList[1]='A'
		if idList[1] == '7':
		#magstripe reads '07' for international students, replace with something
			idList[1]='U'
			idList[2]='0'
		idList = ''.join(i for i in idList[1:])
		print idList
		self.userIDnumber = idList #set the current user to this ID string
			#self.socketWorker.sendEvent(["EVT_CHECKID",MACHINENAME,self.userIDnumber,"True"]) #check the ID record on the server

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
		if command == "EVT_START":
		#A start event is called to start the appropirate program in a new thread
			if infoList[0]=="FRONT":
			#Front desk doesn't have a program to thread
				pass
			else:
				self.startSelect(wx.EVT_BUTTON)

	#this function is called if the socketListener determines that the packet was processed but not approved by the server
	def processDeny(self,command, error):
		#functions expects two lists, one command and containing any relevant error messages
		now = datetime.datetime.now()
		errorList = error.split("|")
		if machineName.upper().startswith("FRONT"):
			self.lightWorker.light(wx.ID_NO)
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
	app.frame.socketWorker.sendEvent(["EVT_CLASSES",MACHINENAME,"False","False"])
	app.frame.Show()
	#wx.lib.inspection.InspectionTool().Show()
	app.MainLoop()