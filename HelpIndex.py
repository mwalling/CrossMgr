
from whoosh.index import create_in
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import *

import HTMLParser
import os
import sys
import shutil
import glob
import re
from bs4 import BeautifulSoup

htmlDocDir = 'CrossMgrHtmlDoc'
indexDir = os.path.join( htmlDocDir, 'HelpIndex' )

if os.path.exists( indexDir ):
	shutil.rmtree( indexDir, ignore_errors = True )
os.mkdir( indexDir )

stemmingAnalyzer = StemmingAnalyzer()
schema = Schema( path=ID(stored=True, unique=True), section=TEXT(stored=True), title=TEXT(stored=True, analyzer=stemmingAnalyzer),
				level=NUMERIC(stored=True), content=TEXT(stored=True, analyzer=stemmingAnalyzer) )
ix = create_in( indexDir, schema )
writer = ix.writer()

titleTags = set([u'h1', u'h2', u'h3', u'h4', u'h5'])

newLines = re.compile( '\n+' )
nonNumeric = re.compile( r'[^\d]' )

def addDocument( fname, section, lastTitle, textCur ):
	if lastTitle and textCur:
		section = '|'.join( section ) if section else lastTitle.get_text()
		print 'Indexing: %s: %s' % (os.path.basename(fname), section)
		content = newLines.sub( '\n', '\n'.join(textCur) )
		writer.add_document(	path = os.path.basename(fname) + '#' + lastTitle['id'],
								title = lastTitle.get_text(),
								section = section,
								level = int(nonNumeric.sub('', lastTitle.name)),
								content = content )

# Extract content sections from the html pages.
for f in glob.iglob( os.path.join(htmlDocDir, '*.html') ):
	doc = BeautifulSoup( open(f).read() )
	div = doc.find('div', class_='content')
	if not div:
		continue
			
	lastTitle = None
	textCur = []
	section = []
	for child in div.children:
		try:
			tag = child.name
		except:
			tag = None
			
		if tag not in titleTags:
			try:
				textCur.append( child.get_text() )
			except:
				pass
			continue
		
		addDocument( f, section, lastTitle, textCur )
		
		iSection = int(int(nonNumeric.sub('', tag))) - 1
		section = section[:iSection]
		section.append( child.get_text() )
		
		lastTitle = child
		textCur = []
			
	addDocument( f, section, lastTitle, textCur )

writer.commit()

#---------------------------------------------------------------------------------------------

from whoosh.qparser import QueryParser
with ix.searcher() as searcher, open('search.html', 'w') as f:
	query = QueryParser('content', ix.schema).parse(u'fastest lap')
	results = searcher.search(query, limit=20)
	f.write( '<table><tr><th></th><th align="left">Section</th><th align="left">Match</th></tr>\n' )
	for i, hit in enumerate(results):
		f.write( '<tr><td align="left">%d.</td><td><a href="%s">%s</a></td><td>%s</td></tr>\n' % ((i+1), hit['path'], hit['section'], hit.highlights('content')) )
	f.write( '</table>\n' )

