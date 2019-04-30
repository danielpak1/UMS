#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import wx, threading, csv, os, sys, select,signal
import subprocess, time, datetime

#platform check, useful for GUI layout
if wx.Platform == "__WXMSW__":
	MSW = True
	GTK = False
else:
	GTK = True
	MSW = False

#hardcoded number of machines, that I should probably tie to /etc/hosts
NUMMACHINES = 16

def signalINT_handler(sig,frame):
	app.frame.OnExit(wx.EVT_CLOSE)
#threaded instance that pings a machine and checks for a response
#if the machine does/not reply, the GUI is updated accordingly with a CallAfter
#output from subprocess is piped to dev/null
class PingThread(threading.Thread):
	def __init__(self,machine):
	#machine is an element in the list of machines (includes status, bitmap, etc). I should turn this into an object.
		self.machine=machine
		threading.Thread.__init__(self)
		self.runFlag = True #run Flag indicates the thread is still running. Can be called externally to end the thread
		
	#required function called by start()
	def run(self):
		ip = self.machine.box.GetLabel()
		i=0 #counter for pings, I don't want more than three attempts
		#pipe all output to dev/null
		with open(os.devnull, 'w') as blackHole:
			while self.runFlag:
			#run until timer expires or kill flag is set
				time.sleep(0.5)
				response = subprocess.call(['ping', '-c', '1', ip],stdout=blackHole, stderr=blackHole)
				#ping return is 0 for a success, 2 for machine didn't respond, >0 for everything else
				if response == 0:
					if self.machine.status!="UP":
						self.machine.status="UP"
					self.stop()
				else:
					if i>=5:
						if self.machine.status!="DOWN":
							self.machine.status="DOWN"
						self.stop()
					else:
						i+=1
		#we let the GUI handle all of the GUI work. We simply change the machine status based on the ping result
		#and then send to updateFromThread
		wx.CallAfter(app.frame.updateFromThread, self.machine)		

	def stop(self):
	#Set the run flag to end the thread. Usefull for terminating a thread from somewhere else
		self.runFlag = False

class LogThread(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.runFlag = True
	def run(self):
		fileName = '/var/log/envision/socketServer.log'
		self.result = subprocess.Popen(['tail','-F',fileName],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
		self.polled = select.poll()
		self.polled.register(self.result.stdout)

		while self.runFlag:
			if self.polled.poll(1):
				wx.CallAfter(app.frame.updateLog, self.result.stdout.readline())
		self.polled.unregister(self.result.stdout)
		self.result.terminate()
	def stop(self):
		self.runFlag = False


class MainWindow(wx.Frame):
	def __init__(self):
		styleFlags = wx.DEFAULT_FRAME_STYLE# | wx.NO_BORDER# | wx.FRAME_NO_TASKBAR
		if GTK:
			styleFlags = wx.DEFAULT_FRAME_STYLE# | wx.STAY_ON_TOP
		wx.Frame.__init__(self, None, title = "EnVision Client Machines", style=styleFlags)
		self.statusLight=[]
		self.clientDict = {}
		self.pingNum = 0
		self.systemUp = False
		
		self.pingTimer = wx.Timer(self) #set the timer as a wx Timer
		self.upTimer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER,self.ping,self.pingTimer) #and bind it to a function
		self.Bind(wx.EVT_TIMER,self.updateUptime,self.upTimer)
		self.Bind(wx.EVT_SIZE,self.onResize)
		self.Bind(wx.EVT_CLOSE, self.OnExit)
		
		self.__get_clients__()
		self.__set_bitmaps__()
		self.__do_layout()
		self.__set_properties()
		
		#start a oneshot one minute timer
		self.pingTimer.Start(5000,oneShot=True)
		self.upTimer.Start(1000)
		
		self.logWorker = LogThread()
		self.logWorker.start()
		
		sys.stdout = self.log
		sys.stderr = self.log

	def __get_clients__(self):
		with open("/etc/hosts",'r') as hostsFile:
			ipReader = csv.reader(hostsFile,delimiter='\t')
			for hosts in ipReader:
				if hosts[0].startswith("192"):
					self.clientDict[hosts[1]]=hosts[0]
		clientList = []
		for host in self.clientDict:
			clientList.append((host,self.clientDict[host]))
		self.sortedClients = sorted(clientList,key = lambda x: x[0].upper())
	
	def __set_bitmaps__(self):
		printerInfoFont = wx.Font(app.printerFontSize,wx.FONTFAMILY_SWISS,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL)
		for i in xrange(NUMMACHINES):
			if i < len(self.sortedClients):
				self.statusLight.append(wx.StaticBitmap(self, wx.ID_ANY, app.bitmaps["machineDown"], style = wx.NO_BORDER))
				machineLabel = self.sortedClients[i][0]
				machineIP = self.sortedClients[i][1]
				status = "DOWN"
			else:
				self.statusLight.append(wx.StaticBitmap(self, wx.ID_ANY, app.bitmaps["noMachine"], style = wx.NO_BORDER))
				machineLabel = "---"
				machineIP = "XXX.XXX.XXX"
				status = None 		
			this = self.statusLight[-1]
			this.status = status
			this.machineName = wx.StaticText(self, label=machineLabel,style=wx.ALIGN_CENTRE_HORIZONTAL|wx.ST_NO_AUTORESIZE)
			this.machineName.SetFont(printerInfoFont)
			this.sizer = (wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, machineIP), wx.VERTICAL))
			this.box = this.sizer.GetStaticBox()
			this.pingWorker = PingThread(this)
	
	def __do_layout(self):
		
		#SIZERS
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.grid_sizer1 = wx.GridSizer(app.grids, app.grids, app.grid_gap, app.grid_gap)
		self.infoSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.logSizer = wx.BoxSizer(wx.VERTICAL)
		
		##WIDGETS
		logstyle = wx.TE_MULTILINE|wx.TE_READONLY
		self.log = wx.TextCtrl(self, wx.ID_ANY, style=logstyle)
		self.restartButton = wx.Button(self, wx.ID_ANY,"RESTART SERVER")
		updateLabel = "Updated xx:xx"
		timeLabel =   "xx-xx:xx:xx"
		self.updateText=wx.StaticText(self,-1,updateLabel,style = wx.ALIGN_CENTRE_HORIZONTAL|wx.ST_NO_AUTORESIZE)
		self.upTimeText=wx.StaticText(self,-1,timeLabel,style=wx.ALIGN_CENTRE_HORIZONTAL|wx.ST_NO_AUTORESIZE)
		
		for light in self.statusLight:
			light.sizer.Add(light, 0, wx.ALL | wx.EXPAND, 0)
			light.sizer.Add(light.machineName,0,wx.CENTER)
			self.grid_sizer1.Add(light.sizer, 1, wx.ALL | wx.EXPAND, app.gridSizerBorder)
		
		self.mainSizer.Add(self.grid_sizer1, 3, wx.EXPAND, 0)
		
		self.infoSizer.Add((20, 20), 1, wx.EXPAND, 0)
		self.infoSizer.Add(self.updateText,1,wx.CENTER, 0)
		self.infoSizer.Add((20, 20), 1, wx.EXPAND, 0)
		self.infoSizer.Add(self.restartButton,1,wx.ALIGN_CENTER | wx.EXPAND, 0)
		self.infoSizer.Add((20, 20), 1, wx.EXPAND, 0)
		self.infoSizer.Add(self.upTimeText,1,wx.CENTER, 0)
		self.infoSizer.Add((20, 20), 1, wx.EXPAND, 0)
		
		self.mainSizer.Add(self.infoSizer,0,wx.TOP | wx.BOTTOM | wx.EXPAND,10)
		self.logSizer.Add(self.log, 1, wx.EXPAND, 0)
		self.mainSizer.Add(self.logSizer,1,wx.EXPAND,0)
		
		self.SetSizer(self.mainSizer)
		self.mainSizer.Fit(self)
		self.SetMinSize((650,500))
		self.Layout()	
	
	def __set_properties(self):
		# begin wxGlade: MyFrame.__set_properties
		self.SetTitle("EnVision Clients")
		self.restartButton.Bind(wx.EVT_BUTTON,self.restartServer)
		updateFont = wx.Font(12,wx.FONTFAMILY_SWISS,wx.FONTSTYLE_ITALIC,wx.FONTWEIGHT_NORMAL)
		self.updateText.SetFont(updateFont)
		self.restartButton.SetFont(updateFont)
		self.upTimeText.SetFont(updateFont)

	def updateUptime(self,event):
		if self.systemUp:
			self.upTimeSeconds +=1
			secs=datetime.timedelta(seconds=self.upTimeSeconds)
			converted=datetime.datetime(1,1,1) + secs
			upStr = ("%s-%s:%s:%s" %(str(converted.day-1).zfill(2),str(converted.hour).zfill(2),str(converted.minute).zfill(2),str(converted.second).zfill(2)))
			self.upTimeText.SetLabel(upStr)
			
		else:
			self.upTimeText.SetLabel("00-00:00:00")
			self.upTimeSeconds = 0
		#self.upTimeText.Layout()
	def OnExit(self,event):
		for thread in threading.enumerate():
			if (not thread.name.upper().startswith("MAIN")):
				thread.stop()
		self.Destroy()
	
	def updateLog(self,logInfo):
		self.log.AppendText(logInfo)
	
	def updateFromThread(self,machine):
		if machine.status=="UP":
			machine.SetBitmap(app.bitmaps["machineUp"])
		elif machine.status=="DOWN":
			machine.SetBitmap(app.bitmaps["machineDown"])
		else:
			machine.SetBitmap(app.bitmaps["noMachine"])
		machine.pingWorker = PingThread(machine)
		self.Layout()
		if self.pingNum >= len(self.clientDict)-1:
			now = datetime.datetime.now()
			self.updateText.SetLabel("Updated " + now.strftime("%H:%M"))
			allMachinesUp = True
			for status in self.statusLight:
				if status.status == "DOWN":
					self.systemUp = False
					allMachinesUp = False
			if allMachinesUp == True:
				self.systemUp = True
			self.pingNum=0
			self.Layout()
			self.Refresh()
		else:
			self.pingNum+=1
	def ping(self,event):
		#self.inPing = True
		self.restartButton.Disable()
		with open("/etc/hosts",'r') as hostsFile:
			ipReader = csv.reader(hostsFile,delimiter='\t')
			for hosts in ipReader:
				if hosts[0].startswith("192"):
					name = hosts[1]
					ip = hosts[0]
					if name in self.clientDict:
						if ip == self.clientDict[name]:
							pass
						else:
							self.clientDict[name]=ip
							for machine in self.statusLight:
								if machine.machineName.GetLabel() == name:
									machine.box.SetLabel(ip)
									break
					else:
						self.clientDict[name] = ip
						for machine in self.statusLight:
							if machine.status == None:
								machine.status = "machineDown"
								machine.SetBitmap(app.bitmaps["machineDown"])
								machine.machineName.SetLabel(name)
								machine.box.SetLabel(ip)
								break
		for machine in self.statusLight:
			if machine.status != None:
				while (machine.pingWorker.isAlive()):
					time.sleep(.01)
				machine.pingWorker.start()
		self.pingTimer.Start(60000,oneShot=True)
		self.restartButton.Enable()
	def onResize(self,newSize):
		winWidth = newSize.GetSize()[0] * (2.0/3.0)
		winHeight = newSize.GetSize()[1] * (2.0/3.0)
		if (winWidth > 1 and winHeight > 1):
			app.__set_bitmaps__(winWidth,winHeight)
			for light in self.statusLight:
				if light.status == "DOWN":
					light.SetBitmap(app.bitmaps["machineDown"])
				elif light.status is None:
					light.SetBitmap(app.bitmaps["noMachine"])
				else:
					light.SetBitmap(app.bitmaps["machineUp"])
				light.sizer.Layout()
		newSize.Skip()
		self.Layout()
		
	def restartServer(self,event):
		agreeMessage = "\nRestart Socket Server?"
		agreeDlg = wx.MessageDialog(self, agreeMessage, "RESTART", wx.YES | wx.NO | wx.CENTRE)
		result = agreeDlg.ShowModal()
		agreeDlg.Close()
		agreeDlg.Destroy()
		if result == wx.ID_YES:
			response = subprocess.call(['sudo', 'systemctl', 'restart', 'envisionSocketServer.service'])#,stdout=self.log, stderr=self.log)
			self.gaugeDialog = 	wx.Dialog(self,style= wx.STAY_ON_TOP, title = "WAITING...", size = (300,100))
			panel = wx.Panel(self.gaugeDialog,size=(300,100))
			dw, dh = panel.GetSize()
			gSize = (dw-dw//10,dh//3)
			location = (dw/2 - gSize[0]/2, dh/2 - gSize[1]/2)
			self.gauge = wx.Gauge(panel, wx.ID_ANY, 10, size=gSize, pos=location)
			self.gauge.SetRange(10)
			dw, dh = wx.DisplaySize()
			w, h = self.gaugeDialog.GetSize()
			#x = dw/2 - w/2
			#y = dh/2 - h/2
			framePos = ((self.Position[0]+(self.Size[0]/2)),(self.Position[1]+(self.Size[1]/2)))
			self.gaugeDialog.SetPosition((framePos[0]-w/2,framePos[1]-h/2))
			self.gaugeCounter = 0
			self.gaugeTimer = wx.Timer(self)
			#and bind it to a function
			self.Bind(wx.EVT_TIMER,self.GaugeSet,self.gaugeTimer)
			self.gaugeTimer.Start(500)
			self.gaugeDialog.ShowModal()
			if response == 0:
				wx.MessageBox('Successfully Restarted', 'SUCCESS', wx.OK | wx.ICON_INFORMATION)
			else:
				wx.MessageBox('Operation could not be completed', 'ERROR', wx.OK | wx.ICON_ERROR)
		elif result == wx.ID_NO:
		#no indicates the admin wants to change the printer timer
			pass
	def GaugeSet(self,event):
		if self.gaugeCounter == 10:
			self.gaugeTimer.Stop()
			self.gaugeDialog.EndModal(0)
			self.gaugeDialog.Destroy()
		else:
			self.gaugeCounter +=1
			self.gauge.SetValue(self.gaugeCounter)
		

class MyApp(wx.App):
	def OnInit(self):
		self.bitmaps = {}
		self.gridSizerBorder = 5
		self.grid_gap = 5
		self.grids = 4
		self.printerFontSize = 10
		self.buttonSize = 90
		self.__set_bitmaps__()
		return True
	
	def __set_bitmaps__(self,dw=400,dh=800):
		imageDir = "/home/e4ms/job_tracking/images/"
		imageList = ["red_button.png","green_button.png","gray_button.png"]
		bitmaps = []
		bitmap_padding = 20
		bitmapWidth = ((dw - (2*self.gridSizerBorder) - self.grid_gap) / self.grids) - self.grid_gap - (2 * bitmap_padding)
		bitmapHeight =((dh - (2*self.gridSizerBorder) - self.grid_gap) / self.grids) - self.grid_gap - (2 * bitmap_padding)
		#bitmapWidth = (dw - 2 * self.gridSizerBorder - self.grid_gap)/self.grids - 2 * bitmap_padding
		#bitmapHeight = (dh - 2*self.gridSizerBorder - self.grid_gap) / self.grids - 2 * bitmap_padding
		#print dw,dh,bitmapWidth,bitmapHeight
		bitmapScale = bitmapHeight if bitmapHeight < bitmapWidth else bitmapWidth
		for image in imageList:
			bitmap = wx.Image(imageDir + image)
			W, H = bitmap.GetSize()
			proportion = float(W) / float(H)
			scaleH = bitmapScale
			scaleW = scaleH * proportion
			bitmap = bitmap.Scale(scaleW, scaleH, wx.IMAGE_QUALITY_HIGH)
			bitmaps.append(wx.BitmapFromImage(bitmap))
			mask = wx.Mask(bitmaps[-1], wx.WHITE)
			bitmaps[-1].SetMask(mask)
		self.bitmaps = {"machineUp":bitmaps[1], "machineDown":bitmaps[0], "noMachine":bitmaps[2]}
# end of class MyApp

if __name__ == "__main__":
	app = MyApp(0)
	app.frame = MainWindow()
	app.frame.Show()
	signal.signal(signal.SIGINT,signalINT_handler)
	app.MainLoop()