# Author: Johan Hanssen Seferidis
# License: MIT
# https://github.com/Pithikos/python-websocket-server

import re
import sys
import six
import time
import struct
from base64 import b64encode
from hashlib import sha1

if sys.version_info[0] < 3:
    from SocketServer import ThreadingMixIn, TCPServer, StreamRequestHandler
else:
    from socketserver import ThreadingMixIn, TCPServer, StreamRequestHandler

#import logging
#logger = logging.getLogger(__name__)
#logging.basicConfig()
import Utils
class logging( object ):
	NONE = 0
	ERROR = 1
	WARNING = 2
	INFO = 3
	
class Logger( object ):
	def __init__( self ):
		self.level = 0

	def setLevel( self, level ):
		self.level = level
		
	def warning( self, message ):
		if self.level >= logging.WARNING:
			msg = 'Websocket Warning: ' + message
			six.print_( msg )
			Utils.writeLog( msg )
	
	def warn( self, message ):
		return self.warning( message )
	
	def info( self, message ):
		if self.level >= logging.INFO:
			msg = 'Websocket Info: '
			six.print_( msg )
			Utils.writeLog( msg )
	
	def error( self, message, exc_info=False ):
		if self.level >= logging.ERROR:
			msg = 'Websocket Error: '
			six.print_( msg )
			Utils.writeLog( msg )

logger = Logger()

'''
+-+-+-+-+-------+-+-------------+-------------------------------+
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
|     Extended payload length continued, if payload len == 127  |
+ - - - - - - - - - - - - - - - +-------------------------------+
|                     Payload Data continued ...                |
+---------------------------------------------------------------+
'''

FIN    = 0x80
OPCODE = 0x0f
MASKED = 0x80
PAYLOAD_LEN = 0x7f
PAYLOAD_LEN_EXT16 = 0x7e
PAYLOAD_LEN_EXT64 = 0x7f

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT         = 0x1
OPCODE_BINARY       = 0x2
OPCODE_CLOSE_CONN   = 0x8
OPCODE_PING         = 0x9
OPCODE_PONG         = 0xA


# -------------------------------- API ---------------------------------

class API():

    def run_forever(self):
        try:
            logger.info("Listening on port %d for clients.." % self.port)
            self.serve_forever()
        except KeyboardInterrupt:
            self.server_close()
            logger.info("Server terminated.")
        except Exception as e:
            logger.error(str(e), exc_info=True)
            exit(1)

    def new_client(self, client, server):
        pass

    def client_left(self, client, server):
        pass

    def message_received(self, client, server, message):
        pass

    def set_fn_new_client(self, fn):
        self.new_client = fn

    def set_fn_client_left(self, fn):
        self.client_left = fn

    def set_fn_message_received(self, fn):
        self.message_received = fn

    def send_message(self, client, msg):
        self._unicast_(client, msg)

    def send_message_to_all(self, msg):
        self._multicast_(msg)

# ------------------------- Implementation -----------------------------

class WebsocketServer(ThreadingMixIn, TCPServer, API):
	"""
	A websocket server waiting for clients to connect.

	Args:
		port(int): Port to bind to
		host(str): Hostname or IP to listen for connections. By default 127.0.0.1
			is being used. To accept connections from any client, you should use
			0.0.0.0.
		loglevel: Logging level from logging module to use for logging. By default
			warnings and errors are being logged.

	Properties:
		clients(dict): A dict of connected clients indexed by handler. A client is a dictionary
			like below.
				{
				 'id'      : id,
				 'handler' : handler,
				 'address' : (addr, port)
				}
	"""

	allow_reuse_address = True
	daemon_threads = True  # comment to keep threads alive until finished

	def __init__(self, port, host='127.0.0.1', loglevel=logging.WARNING):
		logger.setLevel(loglevel)
		self.port = port
		self.clients = {}
		self.id_counter = 0
		TCPServer.__init__(self, (host, port), WebSocketHandler)

	def hasClients( self ):
		return bool(self.clients)
		
	def _message_received_(self, handler, msg):
		try:
			client = self.handler_to_client(handler)
		except KeyError:
			self._client_left( handler )
			return			
		self.message_received(client, self, msg)

	def _ping_received_(self, handler, msg):
		handler.send_pong(msg)

	def _pong_received_(self, handler, msg):
		pass

	def _new_client_(self, handler):
		self.id_counter += 1
		self.clients[handler] = self.id_counter
		self.new_client( self.handler_to_client(handler), self )

	def _client_left_(self, handler):
		try:
			client = self.handler_to_client(handler)
		except KeyError:
			client = None
		if client:
			self.client_left(client, self)
		self.clients.pop(handler, None)

	def _unicast_(self, to_client, msg):
		to_client['handler'].send_message(msg)

	def _multicast_(self, msg):
		# Handle the case where clients might be dropped during the multicast.
		while 1:
			try:
				for handler in list(self.clients.keys()):
					handler.send_message( msg )
				break
			except RuntimeError:
				time.sleep( 0.25 )

	def handler_to_client(self, handler):
		return {'id':self.clients[handler], 'handler':handler, 'address': handler.client_address}

class WebSocketHandler(StreamRequestHandler):

	def __init__(self, socket, addr, server):
		self.server = server
		StreamRequestHandler.__init__(self, socket, addr, server)

	def setup(self):
		StreamRequestHandler.setup(self)
		self.keep_alive = True
		self.handshake_done = False
		self.valid_client = False

	def handle(self):
		while self.keep_alive:
			if not self.handshake_done:
				self.handshake()
			elif self.valid_client:
				self.read_next_message()

	if sys.version_info[0] < 3:
		def read_bytes(self, num):
			return map(ord, self.rfile.read(num))
	else:
		def read_bytes(self, num):
			# python3 gives ordinal of byte directly
			return self.rfile.read(num)

	def read_next_message(self):
		try:
			b1, b2 = self.read_bytes(2)
		except ValueError as e:
			b1, b2 = 0, 0

		fin    = b1 & FIN
		opcode = b1 & OPCODE
		masked = b2 & MASKED
		payload_length = b2 & PAYLOAD_LEN

		if not b1:
			logger.info("Client closed connection.")
			self.keep_alive = 0
			return
		if opcode == OPCODE_CLOSE_CONN:
			logger.info("Client asked to close connection.")
			self.keep_alive = 0
			return
		if not masked:
			logger.warn("Client must always be masked.")
			self.keep_alive = 0
			return
		if opcode == OPCODE_CONTINUATION:
			logger.warn("Continuation frames are not supported.")
			return
		elif opcode == OPCODE_BINARY:
			logger.warn("Binary frames are not supported.")
			return
		elif opcode == OPCODE_TEXT:
			opcode_handler = self.server._message_received_
		elif opcode == OPCODE_PING:
			opcode_handler = self.server._ping_received_
		elif opcode == OPCODE_PONG:
			opcode_handler = self.server._pong_received_
		else:
			logger.warn("Unknown opcode %#x." + opcode)
			self.keep_alive = 0
			return

		if payload_length == 126:
			payload_length = struct.unpack(">H", self.rfile.read(2))[0]
		elif payload_length == 127:
			payload_length = struct.unpack(">Q", self.rfile.read(8))[0]

		masks = self.read_bytes(4)
		decoded = ""
		for char in self.read_bytes(payload_length):
			char ^= masks[len(decoded) % 4]
			decoded += chr(char)
		opcode_handler(self, decoded)

	def send_message(self, message):
		self.send_text(message)

	def send_pong(self, message):
		self.send_text(message, OPCODE_PONG)

	def send_text(self, message, opcode=OPCODE_TEXT):
		"""
		Important: Fragmented(=continuation) messages are not supported since
		their usage cases are limited - when we don't know the payload length.
		"""

		# Validate message
		if isinstance(message, bytes):
			message = try_decode_UTF8(message)  # this is slower but ensures we have UTF-8
			if not message:
				logger.warning("Can\'t send message, message is not valid UTF-8")
				return False
		elif isinstance(message, six.string_types):
			pass
		else:
			logger.warning('Can\'t send message, message has to be a string or bytes. Given type is %s' % type(message))
			return False

		header  = bytearray()
		payload = encode_to_UTF8(message)
		payload_length = len(payload)

		# Normal payload
		if payload_length <= 125:
			header.append(FIN | opcode)
			header.append(payload_length)

		# Extended payload
		elif payload_length >= 126 and payload_length <= 65535:
			header.append(FIN | opcode)
			header.append(PAYLOAD_LEN_EXT16)
			header.extend(struct.pack(">H", payload_length))

		# Huge extended payload
		elif payload_length < 18446744073709551616:
			header.append(FIN | opcode)
			header.append(PAYLOAD_LEN_EXT64)
			header.extend(struct.pack(">Q", payload_length))

		else:
			raise Exception("Message is too big. Consider breaking it into chunks.")
			return

		self.request.send(header + payload)

	def handshake(self):
		message = self.request.recv(1024).decode().strip()
		upgrade = re.search('\nupgrade[\s]*:[\s]*websocket', message.lower())
		if not upgrade:
			self.keep_alive = False
			return
		key = re.search('\n[sS]ec-[wW]eb[sS]ocket-[kK]ey[\s]*:[\s]*(.*)\r\n', message)
		if key:
			key = key.group(1)
		else:
			logger.warning("Client tried to connect but was missing a key")
			self.keep_alive = False
			return
		response = self.make_handshake_response(key)
		self.handshake_done = self.request.send(response.encode())
		self.valid_client = True
		self.server._new_client_(self)

	def make_handshake_response(self, key):
		return \
		  'HTTP/1.1 101 Switching Protocols\r\n'\
		  'Upgrade: websocket\r\n'              \
		  'Connection: Upgrade\r\n'             \
		  'Sec-WebSocket-Accept: %s\r\n'        \
		  '\r\n' % self.calculate_response_key(key)

	def calculate_response_key(self, key):
		GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
		hash = sha1(key.encode() + GUID.encode())
		response_key = b64encode(hash.digest()).strip()
		return response_key.decode('ASCII')

	def finish(self):
		self.server._client_left_(self)


def encode_to_UTF8(data):
	try:
		return data.encode()
	except UnicodeEncodeError as e:
		logger.error("Could not encode data to UTF-8 -- %s" % e)
		return False
	except Exception as e:
		raise(e)
		return False


def try_decode_UTF8(data):
	try:
		return data.decode('utf-8')
	except UnicodeDecodeError:
		return False
	except Exception as e:
		raise(e)
