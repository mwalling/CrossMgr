#from distutils.core import setup
#import py2exe
import os
import sys
import shutil
import zipfile
import subprocess

if os.path.exists('build'):
	shutil.rmtree( 'build' )

# Compile the help files
from helptxt.compile import CompileHelp
CompileHelp( 'helptxt' )

# Index the help files.
from HelpIndex import BuildHelpIndex
BuildHelpIndex()

distDir = r'dist\CrossMgr'
distDirParent = os.path.dirname(distDir)
if os.path.exists(distDirParent):
	shutil.rmtree( distDirParent )
if not os.path.exists( distDirParent ):
	os.makedirs( distDirParent )

subprocess.call( [
	'pyinstaller',
	
	'CrossMgr.pyw',
	'--icon=CrossMgrImages\CrossMgr.ico',
	'--clean',
	'--windowed',
	'--noconfirm',
	
	'--exclude-module=tcl',
	'--exclude-module=tk',
	'--exclude-module=Tkinter',
	'--exclude-module=_tkinter',
] )

# Copy additional dlls to distribution folder.
wxHome = r'C:\Python27\Lib\site-packages\wx-3.0-msw\wx'
try:
	shutil.copy( os.path.join(wxHome, 'MSVCP71.dll'), distDir )
except:
	pass
try:
	shutil.copy( os.path.join(wxHome, 'gdiplus.dll'), distDir )
except:
	pass

# Add images and reference data to the distribution folder.
def copyDir( d ):
	destD = os.path.join(distDir, d)
	if os.path.exists( destD ):
		shutil.rmtree( destD )
	os.mkdir( destD )
	for i in os.listdir( d ):
		if not i.endswith( '.db' ):	# Ignore .db files.
			shutil.copy( os.path.join(d, i), os.path.join(destD,i) )
			
for dir in ['CrossMgrImages', 'data', 'CrossMgrHtml', 'CrossMgrHtmlDoc', 'CrossMgrHelpIndex']: 
	copyDir( dir )

# Copy the locale.
localeD = 'CrossMgrLocale'
destD = os.path.join(distDir, localeD)
if os.path.exists( destD ):
	shutil.rmtree( destD )
shutil.copytree( localeD, destD )

# Create the installer
inno = r'\Program Files\Inno Setup 5\ISCC.exe'
# Find the drive inno is installed on.
for drive in ['C', 'D']:
	innoTest = drive + ':' + inno
	if os.path.exists( innoTest ):
		inno = innoTest
		break
cmd = '"' + inno + '" ' + 'CrossMgr.iss'
print cmd
os.system( cmd )

# Create versioned executable.
from Version import AppVerName
vNum = AppVerName.split()[1]
vNum = vNum.replace( '.', '_' )
newExeName = 'CrossMgr_Setup_v' + vNum + '.exe'

try:
	os.remove( 'install\\' + newExeName )
except:
	pass

shutil.copy( 'install\\CrossMgr_Setup.exe', 'install\\' + newExeName )
print 'executable copied to: ' + newExeName

# Create compressed executable.
os.chdir( 'install' )
newExeName = os.path.basename( newExeName )
newZipName = newExeName.replace( '.exe', '.zip' )

try:
	os.remove( newZipName )
except:
	pass

z = zipfile.ZipFile(newZipName, "w")
z.write( newExeName )
z.close()
print 'executable compressed to: ' + newZipName

shutil.copy( newZipName, r"c:\GoogleDrive\Downloads\Windows\CrossMgr"  )
