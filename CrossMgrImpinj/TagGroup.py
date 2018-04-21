
from datetime import datetime, timedelta
from QuadReg import QuadRegExtreme
from time import sleep
import random
import sys
import operator

# Use a reference time to convert given times to float seconds.
tRef = datetime.now()

tQuiet = 0.5		# Seconds of quiet after which the tag is considered read.
tStray = 8.0		# Seconds of continuous reads for tag to be considered a stray.

def datetimeToTr( t ):
	return (t - tRef).total_seconds()

def trToDatetime( tr ):
	return tRef + timedelta(seconds=tr)

class AntennaReads( object ):
	__slots__ = ('firstRead', 'reads', 'dbMax')
	
	def __init__( self, tr, db ):
		self.firstRead = tr
		self.reads = [(tr, db)]
		self.dbMax = db
	
	def add( self, tr, db ):
		if self.isStray:
			# if a stray, just replace the last entry.
			if len(self.reads) > 1:
				del self.reads[:-1]		
			self.reads[-1] = (tr, db)
		else:
			self.reads.append( (tr, db) )
			if db > self.dbMax: self.dbMax = db
	
	@property
	def isStray( self ):
		return self.reads[-1][0] - self.firstRead > tStray
	
	@property
	def lastRead( self ):
		return self.reads[-1][0]
	
	def getBestEstimate( self ):
		if self.isStray:
			return self.firstRead, 1
		try:
			trEst, sampleSize = QuadRegExtreme(self.reads), len(self.reads)
		except Exception as e:
			# If error, return the first read.
			trEst, sampleSize = self.firstRead, 1
		
		# If the estimate lies outside the data, return the first read.
		if not self.reads[0][0] <= trEst <= self.reads[-1][0]:
			trEst, sampleSize = self.firstRead, 1
		return trEst, sampleSize
		
class TagGroupEntry( object ):
	__slots__ = ('antennaReads', 'firstReadMin', 'lastReadMax', 'isStray')
	
	def __init__( self, antenna, t, db ):
		self.antennaReads = [None, None, None, None]
		self.firstReadMin, self.lastReadMax = sys.float_info.max, -sys.float_info.max
		self.isStray = False
		self.add( antenna, t, db )
		
	def add( self, antenna, t, db ):
		tr = datetimeToTr(t)
		iAntenna = antenna - 1
		if not self.antennaReads[iAntenna]:
			self.antennaReads[iAntenna] = AntennaReads(tr, db)
		else:
			self.antennaReads[iAntenna].add( tr, db )
		
		if tr < self.firstReadMin: self.firstReadMin = tr
		if tr > self.lastReadMax:  self.lastReadMax = tr
	
	def setStray( self ):
		for ar in self.antennaReads:
			if ar:
				del ar.reads[:-1]	# Delete all but last read.
		self.isStray = True
	
	def getBestEstimate( self ):
		if self.isStray:
			return trToDatetime( self.firstReadMin ), 1
		
		# Compute the best estimate using the antenna with the most of reads.  Break ties with dbMax.
		tr, sampleSize = max( (ar for ar in self.antennaReads if ar), key=lambda x: (len(x.reads), x.dbMax) ).getBestEstimate()
		return trToDatetime(tr), sampleSize
		
	def __repr__( self ):
		return 'TagGroupEntry({},{})'.format(self.firstReadMin, self.lastReadMax)
	
class TagGroup( object ):
	'''
		Process groups of tag reads and return the best time estimated using quadratic regression.
		Stray reads are also detected if there is no quiet period for the tag.
		The first read time of each stray read is returned.
	'''
	def __init__( self ):
		self.tagInfo = {}
		
	def add( self, antenna, tag, t, db ):
		try:
			self.tagInfo[tag].add( antenna, t, db )
			return False
		except KeyError:
			self.tagInfo[tag] = TagGroupEntry( antenna, t, db )
			return True

	def getReadsStrays( self, tNow=None ):
		'''
			Returns two lists:
				reads = [(tag1, t1, sampleSize1), (tag2, t2, sampleSize2), ...]
				strays = [(tagA, tFirstReadA), (tagB, tFirstReadB), ...]
				
			Each stray will be reported as a read the first time it is detected.
		'''
		trNow = datetimeToTr( tNow or datetime.now() )
		reads, strays = [], []
		toDelete = []
		for tag, tge in self.tagInfo.iteritems():
			if trNow - tge.lastReadMax >= tQuiet:				# Tag has left read range.
				if not tge.isStray:
					t, sampleSize = tge.getBestEstimate()
					reads.append( (tag, t, sampleSize) )
				toDelete.append( tag )
			elif tge.lastReadMax - tge.firstReadMin >= tStray:	# This is a stray.
				t = trToDatetime( tge.firstReadMin )
				if not tge.isStray:
					tge.setStray()
					reads.append( (tag, t, 1) )					# Report stray first read time.
				strays.append( (tag, t) )
				
		for tag in toDelete:
			del self.tagInfo[tag]
		
		reads.sort( key=operator.itemgetter(1,0))
		strays.sort( key=operator.itemgetter(1,0) )
		return reads, strays
	
if __name__ == '__main__':
	
	def genReadProfile( tg, t, tag, stddev=10.0 ):
		#pointCount = 15
		pointCount = 18
		xRange = 0.5
		yRange = 25
		yTop = -47
		
		yMult = yRange / ((pointCount/2.0) ** 2)
		tDelta = xRange / pointCount
		for i in xrange(pointCount):
			x = i - pointCount/2.0
			noise = random.normalvariate( 0.0, stddev )
			y = yTop - x * x * yMult
			# Report integer values, just like the reader would.
			tg.add( 1, tag, t + timedelta( seconds=x*tDelta ), round(y+noise)  )
	
	t = datetime.now()
	for stddev in xrange(10+1):
		variance = 0.0
		samples = 1000
		for k in xrange(samples):
			tg = TagGroup()
			genReadProfile( tg, t, '111', float(stddev) )
			tEst, sampleSize = tg.tagInfo['111'].getBestEstimate()
			variance += (t - tEst).total_seconds() ** 2
		print '{},{}'.format( stddev, (variance / samples)**0.5 )
	
	print
	tg = TagGroup()
	genReadProfile( tg, t, '111' )
	genReadProfile( tg, t-timedelta(seconds=3), '222' )
	sleep( 1.0 )
	print t, t-timedelta(seconds=3)
	reads, strays = tg.getReadsStrays()
	for tag, t, sampleSize in reads:
		print t, tag, sampleSize