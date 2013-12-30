#!/usr/bin/env python
import os
import sys
import time
import socket
import datetime
from pyllrp import *
from LLRPConnector import LLRPConnector

class TagInventory( object ):
	roSpecID = 123					# Arbitrary roSpecID.
	inventoryParameterSpecID = 1234	# Arbitrary inventory parameter spec id.
	readWaitMilliseconds = 100

	def __init__( self, host = '192.168.10.102', antennas = None ):
		self.host = host
		self.connector = None
		self.antennas = antennas if antennas else [0]
		self.resetTagInventory()
		
	def resetTagInventory( self ):
		self.tagInventory = set()
		self.otherMessages = []

	def AccessReportHandler( self, connector, accessReport ):
		for tag in accessReport.getTagData():
			tagID = HexFormatToStr( tag['EPC'] )
			discoveryTime = self.connector.tagTimeToComputerTime( tag['Timestamp'] )
			self.tagInventory.add( tagID )

	def DefaultHandler( self, connector, message ):
		print 'Unknown Message:'
		print message
		self.otherMessages.append( message )

	def Connect( self ):
		# Create the reader connection.
		self.connector = LLRPConnector()

		# Connect to the reader.
		try:
			response = self.connector.connect( self.host )
		except socket.timeout:
			print '**** Connect timed out.  Check reader hostname and connection. ****'
			raise

	def Disconnect( self ):
		response = self.connector.disconnect()
		self.connector = None

	def GetROSpec( self ):
		# Create an rospec that reports reads.
		return ADD_ROSPEC_Message( Parameters = [
				ROSpec_Parameter(
					ROSpecID = self.roSpecID,
					CurrentState = ROSpecState.Disabled,
					Parameters = [
						ROBoundarySpec_Parameter(		# Configure boundary spec (start and stop triggers for the reader).
							Parameters = [
								ROSpecStartTrigger_Parameter(ROSpecStartTriggerType = ROSpecStartTriggerType.Immediate),
								ROSpecStopTrigger_Parameter(ROSpecStopTriggerType = ROSpecStopTriggerType.Null),
							]
						), # ROBoundarySpec
						AISpec_Parameter(				# Antenna Inventory Spec (specifies which antennas and protocol to use)
							AntennaIDs = self.antennas,
							Parameters = [
								AISpecStopTrigger_Parameter(
									AISpecStopTriggerType = AISpecStopTriggerType.Tag_Observation,
									Parameters = [
										TagObservationTrigger_Parameter(
											TriggerType = TagObservationTriggerType.N_Attempts_To_See_All_Tags_In_FOV_Or_Timeout,
											NumberOfAttempts = 10,
											Timeout = self.readWaitMilliseconds,
										),
									]
								),
								InventoryParameterSpec_Parameter(
									InventoryParameterSpecID = self.inventoryParameterSpecID,
									ProtocolID = AirProtocols.EPCGlobalClass1Gen2,
								),
							]
						), # AISpec
						ROReportSpec_Parameter(			# Report spec (specifies how often and what to send from the reader)
							ROReportTrigger = ROReportTriggerType.Upon_N_Tags_Or_End_Of_ROSpec,
							N = 10000,
							Parameters = [
								TagReportContentSelector_Parameter(
									EnableAntennaID = True,
									EnableFirstSeenTimestamp = True,
								),
							]
						), # ROReportSpec
					]
				), # ROSpec_Parameter
			]
		)	# ADD_ROSPEC_Message

	def _prolog( self ):
		# Disable all the rospecs.  This command may fail so we ignore the response.
		response = self.connector.transact( DISABLE_ROSPEC_Message(ROSpecID = 0) )
		# Delete our old rospec if it exists.  This command might fail so we ignore the return.
		response = self.connector.transact( DELETE_ROSPEC_Message(ROSpecID = self.roSpecID) )

		# Add callbacks so we can record the tag reads and any other messages from the reader.
		self.resetTagInventory()
		self.connector.addHandler( RO_ACCESS_REPORT_Message, self.AccessReportHandler )
		self.connector.addHandler( 'default', self.DefaultHandler )

		# Add and enable our ROSpec
		response = self.connector.transact( self.GetROSpec() )
		assert response.success(), 'Add ROSpec Fails'
		
	def _execute( self ):
		response = self.connector.transact( ENABLE_ROSPEC_Message(ROSpecID = self.roSpecID) )
		assert response.success(), 'Enable ROSpec Fails'
		
		# Wait for the reader to do its work.
		time.sleep( (1.5*self.readWaitMilliseconds) / 1000.0 )
		
		response = self.connector.transact( DISABLE_ROSPEC_Message(ROSpecID = self.roSpecID) )
		assert response.success(), 'Disable ROSpec Fails'
		
	def _epilog( self ):
		# Cleanup.
		response = self.connector.transact( DELETE_ROSPEC_Message(ROSpecID = self.roSpecID) )
		assert response.success(), 'Delete ROSpec Fails'
		self.connector.removeAllHandlers()
		
	def GetTagInventory( self ):
		self._prolog()
		self._execute()
		self._epilog()
		return self.tagInventory, self.otherMessages

if __name__ == '__main__':
	'''Read a tag inventory from the reader and shutdown.'''
	host = '192.168.10.102'
	ti = TagInventory( host )
	ti.Connect()
	tagInventory, otherMessages = ti.GetTagInventory()
	print '\n'.join( tagInventory )
	ti.Disconnect()