#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import wx
import wx.lib.inspection

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
		self.hiddenTC = wx.TextCtrl(self.panel_1, wx.ID_ANY, "")
		self.hiddenTC.SetFocus()
		self.hiddenTC.Hide()
		
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