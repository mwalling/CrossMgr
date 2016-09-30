
import os
import operator
import GetModelInfo
import StringIO

def RaceNameFromPath( p ):
	raceName = os.path.basename( p )
	raceName = os.path.splitext( raceName )[0]
	while raceName.endswith('-'):
		raceName = raceName[:-1]
	raceName = raceName.replace( '-', ' ' )
	raceName = raceName.replace( ' ', '-', 2 )
	return raceName

class PointStructure( object ):

	participationPoints = 0
	dnfPoints = 0

	def __init__( self, name, pointsStr=None, participationPoints=0, dnfPoints=0 ):
		self.name = name
		if pointsStr is not None:
			self.setStr( pointsStr )
		else:
			self.setOCAOCup()
		self.participationPoints = participationPoints
		self.dnfPoints = dnfPoints
		
	def __getitem__( self, rank ):
		rank = int(rank)
		return self.dnfPoints if rank == 999999 else self.pointsForPlace.get( rank, self.participationPoints )
	
	def __len__( self ):
		return len(self.pointsForPlace)
	
	def setUCIWorldTour( self ):
		self.pointsForPlace = { 1:100, 2:80, 3:70, 4:60, 5:50, 6:40, 7:30, 8:20, 9:10, 10:4 }
		
	def setOCAOCup( self ):
		self.pointsForPlace = { 1:25, 2:20, 3:16, 4:13, 5:11, 6:10, 7:9, 8:8, 9:7, 10:6, 11:5, 12:4, 13:3, 14:2, 15:1 }
	
	def getStr( self ):
		return ', '.join( str(points) for points in sorted(self.pointsForPlace.values(), reverse=True) )
	
	def getHtml( self ):
		values = [(pos, points) for pos, points in self.pointsForPlace.iteritems()]
		values.sort()
		
		html = StringIO.StringIO()
		html.write( '<table>\n' )
		
		for pos, points in values:
			html.write( '<tr>' )
			html.write( '<td style="text-align:right;">{}.</td>'.format(pos) )
			html.write( '<td style="text-align:right;">{}</td>'.format(points) )
			html.write( '</tr>\n' )
			
		if self.participationPoints != 0:
			html.write( '<tr>' )
			html.write( '<td style="text-align:right;">Participation:</td>' )
			html.write( '<td style="text-align:right;">{}</td>'.format(self.participationPoints) )
			html.write( '</tr>\n' )
			
		if self.dnfPoints != 0:
			html.write( '<tr>' )
			html.write( '<td style="text-align:right;">DNF:</td>' )
			html.write( '<td style="text-align:right;">{}</td>'.format(self.dnfPoints) )
			html.write( '</tr>\n' )
			
		html.write( '</table>\n' )
		return html.getvalue()
	
	def setStr( self, s ):
		s = s.replace( ',', ' ' )
		values = []
		for v in s.split():
			try:
				values.append( int(v) )
			except:
				continue
		self.pointsForPlace = dict( (i+1, v) for i, v in enumerate(sorted(values, reverse=True)) )
		
	def __repr__( self ):
		return u'({}: {} + {}, dnf={})'.format( self.name, self.getStr(), self.participationPoints, self.dnfPoints )

class Race( object ):
	def __init__( self, fileName, pointStructure ):
		self.fileName = fileName
		self.pointStructure = pointStructure
		
	def getRaceName( self ):
		return RaceNameFromPath( self.fileName )
		
	def postReadFix( self ):
		if getattr( self, 'fname', None ):
			self.fileName = getattr(self, 'fname')
			delattr( self, 'fname' )
				
	def getFileName( self ):
		return self.fileName
		
	def __repr__( self ):
		return ', '.join( '{}={}'.format(a, repr(getattr(self, a))) for a in ['fileName', 'pointStructure'] )
		
class SeriesModel( object ):
	DefaultPointStructureName = 'Regular'
	useMostEventsCompleted = False
	scoreByTime = False
	scoreByPercent = False
	scoreByTrueSkill = False
	considerPrimePointsOrTimeBonus = True
	licenseLinkTemplate = u''	# Used to create an html link from the rider's license number in the html output.
	bestResultsToConsider = 0	# 0 == all
	mustHaveCompleted = 0		# Number of events to complete to be eligible for results.
	organizer = u''
	upgradePaths = []
	upgradeFactors = []
	showLastToFirst = True		# If True, show the latest races first in the output.
	postPublishCmd = ''
	categorySequence = {}
	categorySequencePrevious = {}

	def __init__( self ):
		self.name = '<Series Name>'
		self.races = []
		self.pointStructures = [PointStructure(self.DefaultPointStructureName)]
		self.numPlacesTieBreaker = 5
		self.errors = []
		self.changed = False
		
	def postReadFix( self ):
		for r in self.races:
			r.postReadFix()
	
	def setPoints( self, pointsList ):
		oldPointsList = [(p.name, p.name, p.getStr(), u'{}'.format(p.participationPoints), u'{}'.format(p.dnfPoints))
			for p in self.pointStructures]
		if oldPointsList == pointsList:
			return
			
		self.changed = True
		
		newPointStructures = []
		oldToNewName = {}
		newPS = {}
		for name, oldName, points, participationPoints, dnfPoints in pointsList:
			name = name.strip()
			oldName = oldName.strip()
			points = points.strip()
			if not name or name in newPS:
				continue
			participationPoints = int(participationPoints or '0')
			dnfPoints = int(dnfPoints or '0')
			ps = PointStructure( name, points, participationPoints, dnfPoints )
			oldToNewName[oldName] = name
			newPS[name] = ps
			newPointStructures.append( ps )
			
		if not newPointStructures:
			newPointStructures = [PointStructure(self.DefaultPointStructureName)]
			
		for r in self.races:
			r.pointStructure = newPS.get( oldToNewName.get(r.pointStructure.name, ''), newPointStructures[0] )
			
		self.pointStructures = newPointStructures
	
	def setRaces( self, raceList ):
		oldRaceList = [(r.fileName, r.pointStructure.name) for r in self.races]
		if oldRaceList == raceList:
			return
		
		self.changed = True
		
		newRaces = []
		ps = dict( (p.name, p) for p in self.pointStructures )
		for fileName, pname in raceList:
			fileName = fileName.strip()
			pname = pname.strip()
			if not fileName:
				continue
			try:
				p = ps[pname]
			except KeyError:
				continue
			newRaces.append( Race(fileName, p) )
			
		self.races = newRaces
	
	def setCategorySequence( self, categoryList ):
		categorySequenceNew = { c:i for i, c in enumerate(categoryList) }
		if self.categorySequence != categorySequenceNew:
			self.categorySequence = categorySequenceNew
			self.changed = True
	
	def harmonizeCategorySequence( self, raceResults ):
		categorySequenceSave = self.categorySequence
		
		categoriesFromRaces = set(rr.categoryName for rr in raceResults)
		if not categoriesFromRaces:
			if self.categorySequence:
				self.categorySequence = {}
				self.changed = True
			return
		
		categorySequence = (self.categorySequence or self.categorySequencePrevious)
		categoriesCur = set( categorySequence.iterkeys() )
		categoriesNew = categoriesFromRaces - categoriesCur
		categoriesDel = categoriesCur - categoriesFromRaces

		categoriesCur = sorted( categoriesCur, key=lambda c: categorySequence[c] )
		categoriesCur = [c for c in categoriesCur if c not in categoriesDel]
		categoriesCur.extend( sorted(categoriesNew) )
		
		self.categorySequence = { c:i for i, c in enumerate(categoriesCur) }
		self.categorySequencePrevious = self.categorySequence
		if categorySequenceSave != self.categorySequence:
			self.changed = True
	
	def getCategoryNamesSorted( self ):
		cs = self.categorySequence
		return sorted( (c for c in cs.iterkeys()), key=lambda c: cs[c] )
	
	def setRootFolder( self, path ):
		raceFileNames = set( os.path.basename(r.fileName) for r in self.races )
		for top, directories, files in os.walk(path):
			for f in files:
				if f not in raceFileNames:
					continue
				for r in self.races:
					if os.path.basename(r.fileName) == f:
						r.fileName = os.path.join( top, f )
						self.changed = True
	
	def setChanged( self, changed = True ):
		self.changed = changed
	
	def addRace( self, name ):
		self.changed = True
		race = Race( name, self.pointStructures[0] )
		self.races.append( race )
		
	def removeRace( self, name ):
		raceCount = len(self.races)
		self.races = [r for r in self.races if r.fileName != name]
		if raceCount != len(self.races):
			self.changed = True
			
	def removeAllRaces( self ):
		if self.races:
			self.races = []
			self.changed = True
	
	def extractAllRaceResults( self ):
		raceResults = []
		oldErrors = self.errors
		self.errors = []
		for r in self.races:
			success, ex, results = GetModelInfo.ExtractRaceResults( r )
			if success:
				raceResults.extend( results )
			else:
				self.errors.append( (r, ex) )
				
		GetModelInfo.AdjustForUpgrades( raceResults )
		self.harmonizeCategorySequence( raceResults )
		
		if oldErrors != self.errors:
			self.changed = True
		return raceResults
			
model = SeriesModel()
