import wx
import bisect
import sys
import Utils
import Model
from Utils import formatTime, SetLabel
from Utils import logException
import ColGrid
import StatusBar
import OutputStreamer
import NumKeypad
import VideoBuffer
from GetResults import GetResults
from EditEntry import CorrectNumber, SplitNumber, ShiftNumber, InsertNumber, DeleteEntry, DoDNS, DoDNF, DoPull
from FtpWriteFile import realTimeFtpPublish

@Model.memoize
def interpolateNonZeroFinishers():
	results = GetResults( None, False )
	Entry = Model.Entry
	Finisher = Model.Rider.Finisher
	entries = []
	for r in results:
		if r.status == Finisher:
			riderEntries = [Entry(r.num, lap, t, r.interp[lap]) for lap, t in enumerate(r.raceTimes)]
			entries.extend( riderEntries[1:] )
	entries.sort( key=Entry.key )
	return entries
	
# Define columns for recorded and expected information.
iNumCol, iNoteCol, iTimeCol, iLapCol, iGapCol, iNameCol, iColMax = range(7)
colnames = [None] * iColMax
colnames[iNumCol]  = _('Num')
colnames[iNoteCol] = _('Note')
colnames[iLapCol]  = _('Lap')
colnames[iTimeCol] = _('Time')
colnames[iGapCol]  = _('Gap')
colnames[iNameCol] = _('Name')

fontSize = 14

def GetLabelGrid( parent ):
	font = wx.Font( fontSize, wx.DEFAULT, wx.NORMAL, wx.NORMAL )
	dc = wx.WindowDC( parent )
	dc.SetFont( font )
	w, h = dc.GetTextExtent( '999' )

	label = wx.StaticText( parent, wx.ID_ANY, _('Recorded:') )
	
	grid = ColGrid.ColGrid( parent, colnames = colnames )
	grid.SetLeftAlignCols( [iNameCol] )
	grid.SetRowLabelSize( 0 )
	grid.SetRightAlign( True )
	grid.AutoSizeColumns( True )
	grid.DisableDragColSize()
	grid.DisableDragRowSize()
	grid.SetDoubleBuffered( True )
	grid.SetDefaultCellFont( font )
	grid.SetDefaultRowSize( int(h * 1.15), True )
	return label, grid
		
class LabelGrid( wx.Panel ):
	def __init__( self, parent, id = wx.ID_ANY, style = 0 ):
		wx.Panel.__init__(self, parent, id, style=style)
		
		bsMain = wx.BoxSizer( wx.VERTICAL )
		
		self.label, self.grid = GetLabelGrid( self )
		bsMain.Add( self.label, 0, flag=wx.ALL, border=4 )
		bsMain.Add( self.grid, 1, flag=wx.ALL|wx.EXPAND, border = 4 )
		
		self.SetSizer( bsMain )
		self.Layout()

class ForecastHistory( wx.Panel ):
	def __init__( self, parent, id = wx.ID_ANY, style = 0 ):
		wx.Panel.__init__(self, parent, id, style=style)
		
		self.quickRecorded = None
		self.quickExpected = None
		self.entryCur = None
		self.orangeColour = wx.Colour(255, 165, 0)
		self.redColour = wx.Colour(255, 51, 51)

		self.callLaterRefresh = None
		
		# Main sizer.
		bsMain = wx.BoxSizer( wx.VERTICAL )
		
		# Put Recorded and Expected in a splitter window.
		self.splitter = wx.SplitterWindow( self )
		
		self.lgHistory = LabelGrid( self.splitter, style = wx.BORDER_SUNKEN )
		self.historyName = self.lgHistory.label
		self.historyName.SetLabel( _('Recorded:') )
		self.historyGrid = self.lgHistory.grid
		self.Bind( wx.grid.EVT_GRID_CELL_LEFT_DCLICK, self.doNumDrilldown, self.historyGrid )
		self.Bind( wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self.doHistoryPopup, self.historyGrid )
		
		self.lgExpected = LabelGrid( self.splitter, style = wx.BORDER_SUNKEN )
		self.expectedName = self.lgExpected.label
		self.expectedGrid = self.lgExpected.grid
		self.expectedGrid.SetDoubleBuffered( True )
		colnames[iTimeCol] = _('ETA')
		self.expectedGrid.Set( colnames = colnames )
		self.expectedName.SetLabel( _('Expected:') )
		self.expectedGrid.SetDefaultCellBackgroundColour( wx.Colour(230,255,255) )
		self.Bind( wx.grid.EVT_GRID_SELECT_CELL, self.doExpectedSelect, self.expectedGrid )
		self.Bind( wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self.doExpectedPopup, self.expectedGrid )	
		
		self.splitter.SetMinimumPaneSize( 64 )
		self.splitter.SetSashGravity( 0.5 )
		self.splitter.SplitHorizontally( self.lgExpected, self.lgHistory, 100 )
		self.Bind( wx.EVT_SPLITTER_DCLICK, self.doSwapOrientation, self.splitter )
		bsMain.Add( self.splitter, 1, flag=wx.EXPAND | wx.ALL, border = 4 )
				
		self.historyGrid.Reset()
		self.expectedGrid.Reset()
		
		self.SetSizer( bsMain )
		self.refresh()
		self.Layout()
		
	def setSash( self ):
		size = self.GetClientSize()
		if self.splitter.GetSplitMode() == wx.SPLIT_VERTICAL:
			self.splitter.SetSashPosition( size.width // 2 )
		else:
			self.splitter.SetSashPosition( size.height // 2 )

	def swapOrientation( self ):
		width = 285
		if self.splitter.GetSplitMode() == wx.SPLIT_VERTICAL:
			self.splitter.SetSplitMode( wx.SPLIT_HORIZONTAL )
			mainWin = Utils.getMainWin()
			if mainWin:
				mainWin.splitter.SetSashPosition( width )
		else:
			self.splitter.SetSplitMode( wx.SPLIT_VERTICAL )
			mainWin = Utils.getMainWin()
			if mainWin:
				mainWin.splitter.SetSashPosition( width * 2 )
		self.setSash()
		
	def doSwapOrientation( self, event ):
		self.swapOrientation()
	
	def doNumDrilldown( self, event ):
		with Model.LockRace() as race:
			if not race or not race.isRunning():
				return
		grid = event.GetEventObject()
		row = event.GetRow()
		value = ''
		if row < grid.GetNumberRows():
			value = grid.GetCellValue( row, 0 )
		if not value:
			return
		numSelect = value
		mainWin = Utils.getMainWin()
		if mainWin:
			mainWin.setNumSelect( numSelect )
			mainWin.showPageName( _('RiderDetail') )
	
	def doHistoryPopup( self, event ):
		r = event.GetRow()
		with Model.LockRace() as race:
			if r >= len(self.quickRecorded) or not race or not race.isRunning():
				return
		value = ''
		if r < self.historyGrid.GetNumberRows():
			value = self.historyGrid.GetCellValue( r, 0 )
		if not value:
			return
		
		self.entryCur = self.quickRecorded[r]
		if not hasattr(self, 'historyPopupInfo'):
			self.historyPopupInfo = [
				(_('Correct...'),	wx.NewId(), self.OnPopupHistoryCorrect),
				(_('Split...'),		wx.NewId(), self.OnPopupHistorySplit),
				(_('Shift...'),		wx.NewId(), self.OnPopupHistoryShift),
				(_('Insert...'),	wx.NewId(), self.OnPopupHistoryInsert),
				(_('Delete...'),	wx.NewId(), self.OnPopupHistoryDelete),
				(None,				None,		None),
				(_('DNF...'),		wx.NewId(), self.OnPopupHistoryDNF),
				(None,				None,		None),
				(_('RiderDetail'),	wx.NewId(),self.OnPopupHistoryRiderDetail),
			]
			for p in self.historyPopupInfo:
				if p[2]:
					self.Bind( wx.EVT_MENU, p[2], id=p[1] )

		menu = wx.Menu()
		for i, p in enumerate(self.historyPopupInfo):
			if p[2]:
				menu.Append( p[1], p[0] )
			else:
				menu.AppendSeparator()
		
		self.PopupMenu( menu )
		menu.Destroy()
		
	def OnPopupHistoryCorrect( self, event ):
		if self.entryCur:
			CorrectNumber( self, self.entryCur )
		
	def OnPopupHistorySplit( self, event ):
		if self.entryCur:
			SplitNumber( self, self.entryCur )
		
	def OnPopupHistoryShift( self, event ):
		if self.entryCur:
			ShiftNumber( self, self.entryCur )
		
	def OnPopupHistoryInsert( self, event ):
		if self.entryCur:
			InsertNumber( self, self.entryCur )
		
	def OnPopupHistoryDelete( self, event ):
		if self.entryCur:
			DeleteEntry( self, self.entryCur )
			
	def OnPopupHistoryDNF( self, event ):
		try:
			num = self.entryCur.num
			NumKeypad.DoDNF( self, num )
		except:
			pass
	
	def OnPopupHistoryRiderDetail( self, event ):
		try:
			num = self.entryCur.num
			mainWin = Utils.getMainWin()
			mainWin.setNumSelect( num )
			mainWin.showPageName( _('RiderDetail') )
		except:
			pass
				
	#--------------------------------------------------------------------
	
	def doExpectedSelect( self, event ):
		r = event.GetRow()
		try:
			if self.quickExpected[r].lap == 0:
				return
		except:
			pass
		if r < self.expectedGrid.GetNumberRows():
			self.logNum( self.expectedGrid.GetCellValue(r, 0) )
		
	def doExpectedPopup( self, event ):
		r = event.GetRow()
		with Model.LockRace() as race:
			if r >= len(self.quickExpected) or not race or not race.isRunning():
				return
		value = ''
		if r < self.expectedGrid.GetNumberRows():
			value = self.expectedGrid.GetCellValue( r, 0 )
		if not value:
			return
			
		self.entryCur = self.quickRecorded[r]
		if not hasattr(self, 'expectedPopupInfo'):
			self.expectedPopupInfo = [
				(_('Enter'),		wx.NewId(), self.OnPopupExpectedEnter),
				(_('DNF...'),		wx.NewId(), self.OnPopupExpectedDNF),
				(_('Pull...'),		wx.NewId(), self.OnPopupExpectedPull),
				(None,				None,		None),
				(_('RiderDetail'),	wx.NewId(),	self.OnPopupExpectedRiderDetail),
			]
			for p in self.expectedPopupInfo:
				if p[2]:
					self.Bind( wx.EVT_MENU, p[2], id=p[1] )

		menu = wx.Menu()
		for i, p in enumerate(self.expectedPopupInfo):
			if p[2]:
				menu.Append( p[1], p[0] )
			else:
				menu.AppendSeparator()
		
		self.PopupMenu( menu )
		menu.Destroy()
		
	def OnPopupExpectedEnter( self, event ):
		try:
			num = self.entryCur.num
			self.logNum( num )
		except:
			pass
		
	def OnPopupExpectedDNF( self, event ):
		try:
			num = self.entryCur.num
			NumKeypad.DoDNF( self, num )
		except:
			pass
		
	def OnPopupExpectedPull( self, event ):
		try:
			num = self.entryCur.num
			NumKeypad.DoPull( self, num )
		except:
			pass

	def OnPopupExpectedRiderDetail( self, event ):
		try:
			num = self.entryCur.num
			mainWin = Utils.getMainWin()
			mainWin.setNumSelect( num )
			mainWin.showPageName( _('RiderDetail') )
		except:
			pass
				
	#--------------------------------------------------------------------
	
	def logNum( self, nums ):
		if nums is None:
			return
		if not isinstance(nums, (list, tuple)):
			nums = [nums]
			
		with Model.LockRace() as race:
			if race is None or not race.isRunning():
				return
				
			t = race.curRaceTime()
			
			# Take the picture first to reduce latency to capturing the riders as they cross the line.
			if getattr(race, 'enableUSBCamera', False):
				for num in nums:
					try:
						num = int(num)
					except:
						continue
					try:
						race.photoCount = getattr(race,'photoCount',0) + VideoBuffer.ModelTakePhoto( num, t )
					except Exception as e:
						logException( e, sys.exc_info() )
			
			# Add the times to the model and write to the log.
			for num in nums:
				try:
					num = int(num)
				except:
					continue
				race.addTime( num, t )
				OutputStreamer.writeNumTime( num, t )
				
		mainWin = Utils.getMainWin()
		if mainWin:
			mainWin.record.keypad.numEdit.SetValue( '' )
			mainWin.record.refreshLaps()
			wx.CallAfter( mainWin.refresh )
		if getattr(race, 'ftpUploadDuringRace', False):
			realTimeFtpPublish.publishEntry()
		
	def clearGrids( self ):
		self.historyGrid.Set( data = [] )
		self.historyGrid.Reset()
		self.expectedGrid.Set( data = [] )
		self.expectedGrid.Reset()
	
	def updatedExpectedTimes( self, tRace = None ):
		if not self.quickExpected:
			return
		if not tRace:
			tRace = Model.race.curRaceTime()
		self.expectedGrid.SetColumn( iTimeCol, [formatTime(e.t - tRace) if e.lap > 0 else ('[{}]'.format(formatTime(max(0.0, e.t - tRace + 0.99999999))))\
										for e in self.quickExpected] )
	
	def refresh( self ):
		with Model.LockRace() as race:
			if race is None or not race.isRunning():
				self.quickExpected = None
				self.clearGrids()
				return
				
			try:
				externalInfo = race.excelLink.read( True )
			except:
				externalInfo = {}
						
			tRace = race.curRaceTime()
			tRaceLength = race.minutes * 60.0
			
			entries = interpolateNonZeroFinishers()
			
			isTimeTrial = getattr(race, 'isTimeTrial', False)
			if isTimeTrial:
				# Update the start times in as recorded times.
				startTimes = [(rider.firstTime, rider.num) for rider in race.riders.itervalues() \
								if rider.status == Model.Rider.Finisher and rider.firstTime]
				startTimes.sort()
				
				# Find the next start time so we can update the display.
				iClosestStartTime = bisect.bisect_left( startTimes, (tRace, 0) )
				if iClosestStartTime < len(startTimes):
					tClosestStartTime = startTimes[iClosestStartTime][0]
					milliSeconds = max( 0, int((tClosestStartTime - tRace)*1000.0 + 10.0) )
					if self.callLaterRefresh is None:
						self.callLaterRefresh = wx.CallLater( milliSeconds, self.refresh )
					self.callLaterRefresh.Restart( milliSeconds )
				
				startTimeEntries = [Model.Entry(st[1], 0, st[0], False) for st in startTimes]
				
				# Add the rider firstTime to correct the times back to race times.
				correctedEntries = [Model.Entry(e.num, e.lap, race.riders[e.num].firstTime + e.t, e.interp) for e in entries]
				startTimeEntries.extend( correctedEntries )
				entries = startTimeEntries
			
			#------------------------------------------------------------------
			# Select the interpolated entries around now.
			leaderPrev, leaderNext = race.getPrevNextLeader( tRace )
			averageLapTime = race.getAverageLapTime()
			backSecs = averageLapTime
			
			expectedShowMax = 80
			
			tMin = tRace - backSecs
			tMax = tRace + averageLapTime
			iCur = bisect.bisect_left( entries, Model.Entry(0, 0, tRace, True) )
			iLeft = max(0, iCur - expectedShowMax/2)
			seen = {}
			expected = [ seen.setdefault(e.num, e) for e in entries[iLeft:] if e.interp and tMin <= e.t <= tMax and e.num not in seen ]
			if isTimeTrial:
				# Update the expected start times.
				expectedStarters = [(rider.firstTime, rider.num) for rider in race.riders.itervalues() \
								if rider.status == Model.Rider.Finisher and rider.firstTime and rider.firstTime >= tRace]
				expectedStarters.sort()
				expectedStarterEntries = [Model.Entry(st[1], 0, st[0], False) for st in expectedStarters]
				expectedStarterEntries.extend( expected )
				expected = expectedStarterEntries
				
			expected = expected[:expectedShowMax]
			
			prevCatLeaders, nextCatLeaders = race.getCatPrevNextLeaders( tRace )
			prevRiderPosition, nextRiderPosition = race.getPrevNextRiderPositions( tRace )
			prevRiderGap, nextRiderGap = race.getPrevNextRiderGaps( tRace )
			
			backgroundColour = {}
			textColour = {}
			#------------------------------------------------------------------
			# Highlight the missing riders.
			tMissing = tRace - averageLapTime / 8.0
			iNotMissing = 0
			for r in (i for i, e in enumerate(expected) if e.t < tMissing):
				for c in xrange(iColMax):
					backgroundColour[(r, c)] = self.orangeColour
				iNotMissing = r + 1
				
			#------------------------------------------------------------------
			# Highlight the leaders in the expected list.
			iBeforeLeader = None
			# Highlight the leader by category.
			catNextTime = {}
			outsideTimeBound = set()
			for r, e in enumerate(expected):
				if e.num in nextCatLeaders:
					backgroundColour[(r, iNoteCol)] = wx.GREEN
					catNextTime[nextCatLeaders[e.num]] = e.t
					if e.num == leaderNext:
						backgroundColour[(r, iNumCol)] = wx.GREEN
						iBeforeLeader = r
				elif tRace < tRaceLength and race.isOutsideTimeBound(e.num):
					backgroundColour[(r, iNumCol)] = backgroundColour[(r, iNoteCol)] = self.redColour
					textColour[(r, iNumCol)] = textColour[(r, iNoteCol)] = wx.WHITE
					outsideTimeBound.add( e.num )
			
			data = [None] * iColMax
			data[iNumCol] = ['{}'.format(e.num) for e in expected]
			data[iTimeCol] = [formatTime(e.t - tRace) if e.lap > 0 else ('[%s]' % formatTime(max(0.0, e.t - tRace + 0.99999999)))\
										for e in expected]
			data[iLapCol] = ['{}'.format(e.lap) for e in expected]
			def getNoteExpected( e ):
				if e.lap == 0:
					return _('Start')
				try:
					position = prevRiderPosition.get(e.num, -1) if e.t < catNextTime[race.getCategory(e.num)] else \
							   nextRiderPosition.get(e.num, -1)
				except KeyError:
					position = prevRiderPosition.get(e.num, -1)
					
				if position == 1:
					return _('Lead')
				elif e.t < tMissing:
					return _('miss')
				elif position >= 0:
					return Utils.ordinal(position)
				else:
					return ' '
			data[iNoteCol] = [getNoteExpected(e) for e in expected]
			def getGapExpected( e ):
				try:
					gap = prevRiderGap.get(e.num, ' ') if e.t < catNextTime[race.getCategory(e.num)] else \
							   nextRiderGap.get(e.num, ' ')
				except KeyError:
					gap = prevRiderGap.get(e.num, ' ')
				return gap
			data[iGapCol] = [getGapExpected(e) for e in expected]
			def getName( e ):
				info = externalInfo.get(e.num, {})
				last = info.get('LastName','')
				first = info.get('FirstName','')
				if last and first:
					return u'{}, {}'.format(last, first)
				return last or first or ' '
			data[iNameCol] = [getName(e) for e in expected]
			
			self.quickExpected = expected
			
			self.expectedGrid.Set( data = data, backgroundColour = backgroundColour, textColour = textColour )
			self.expectedGrid.AutoSizeColumns()
			self.expectedGrid.AutoSizeRows()
			
			if iBeforeLeader:
				Utils.SetLabel( self.expectedName, _('Expected: {} before Race Leader').format(iBeforeLeader) )
			else:
				Utils.SetLabel( self.expectedName, _('Expected:') )
			
			#------------------------------------------------------------------
			# Update recorded.
			recordedDisplayMax = 64
			recorded = [ e for e in entries if not e.interp and e.t <= tRace ]
			recorded = recorded[-recordedDisplayMax:]
			self.quickRecorded = recorded
				
			backgroundColour = {}
			textColour = {}
			outsideTimeBound = set()
			# Highlight the leader in the recorded list.
			for r, e in enumerate(recorded):
				if prevRiderPosition.get(e.num,-1) == 1:
					backgroundColour[(r, iNoteCol)] = wx.GREEN
					if e.num == leaderPrev:
						backgroundColour[(r, iNumCol)] = wx.GREEN
				elif tRace < tRaceLength and race.isOutsideTimeBound(e.num):
					backgroundColour[(r, iNumCol)] = backgroundColour[(r, iNoteCol)] = self.redColour
					textColour[(r, iNumCol)] = textColour[(r, iNoteCol)] = wx.WHITE
					outsideTimeBound.add( e.num )
									
			data = [None] * iColMax
			data[iNumCol] = ['{}'.format(e.num) for e in recorded]
			data[iTimeCol] = [formatTime(e.t) if e.lap > 0 else '[{}]'.format(formatTime(e.t)) for e in recorded]
			data[iLapCol] = ['{}'.format(e.lap) for e in recorded]
			def getNoteHistory( e ):
				if e.lap == 0:
					return 'Start'

				position = nextRiderPosition.get(e.num, -1)
				if position == 1:
					return 'Lead'
				elif position >= 0:
					return Utils.ordinal(position)
				else:
					return ' '
			data[iNoteCol] = [getNoteHistory(e) for e in recorded]
			def getGapHistory( e ):
				if e.lap == 0:
					return ' '
				return prevRiderGap.get(e.num, ' ')
			data[iGapCol] = [getGapHistory(e) for e in recorded]
			data[iNameCol] = [getName(e) for e in recorded]

			self.historyGrid.Set( data = data, backgroundColour = backgroundColour, textColour = textColour )
			self.historyGrid.AutoSizeColumns()
			self.historyGrid.AutoSizeRows()
			
			# Show the relevant cells in each table.
			if recorded:
				self.historyGrid.MakeCellVisible( len(recorded)-1, 0 )
			if iNotMissing < self.expectedGrid.GetNumberRows():
				self.expectedGrid.MakeCellVisible( iNotMissing, 0 )

if __name__ == '__main__':
	app = wx.PySimpleApp()
	mainWin = wx.Frame(None,title="CrossMan", size=(600,400))
	
	fh = ForecastHistory(mainWin)
	Model.setRace( Model.Race() )
	Model.getRace()._populate()
	for i, rider in enumerate(Model.getRace().riders.itervalues()):
		rider.firstTime = i * 30.0
	Model.getRace().isTimeTrial = True
	fh.refresh()
	mainWin.Show()
	fh.setSash()
	fh.swapOrientation()
	app.MainLoop()
