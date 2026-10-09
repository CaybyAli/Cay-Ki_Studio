"""Small read-only RFC6455 client; no new package in the user's installation.

Only ComfyUI's existing socket is consumed. No workflows, interrupts or service
configuration are sent. Binary previews are discarded, with bounded buffering.
"""
import asyncio
import base64
import hashlib
import json
import os
import ssl
import struct
from urllib.parse import urlsplit, urlencode


async def messages(url, client_id, connected):
    address = urlsplit(url)
    secure = address.scheme in ('https', 'wss')
    reader, writer = await asyncio.wait_for(asyncio.open_connection(
        address.hostname, address.port or (443 if secure else 80),
        ssl=ssl.create_default_context() if secure else None), 8)
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        path = address.path.rstrip('/') + '/ws?' + urlencode({'clientId': client_id})
        writer.write((f'GET {path} HTTP/1.1\r\nHost: {address.netloc}\r\n'
                      f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                      'Sec-WebSocket-Version: 13\r\n\r\n').encode())
        await writer.drain()
        headers = (await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 8)).decode('latin1').split('\r\n')
        fields = {line.split(':',1)[0].lower():line.split(':',1)[1] for line in headers[1:] if ':' in line}
        accept = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if ' 101 ' not in headers[0] or fields.get('sec-websocket-accept', '').strip() != accept:
            raise OSError('ComfyUI bietet derzeit keine Fortschrittsverbindung an.')
        connected.set()
        pending = bytearray(); kind = None
        while True:
            first, second = await asyncio.wait_for(reader.readexactly(2), 90)
            final = bool(first & 128); opcode = first & 15; size = second & 127
            if first & 112 or second & 128:
                raise OSError('Ungültiger WebSocket-Frame')
            if size == 126: size = struct.unpack('!H', await reader.readexactly(2))[0]
            elif size == 127: size = struct.unpack('!Q', await reader.readexactly(8))[0]
            if size > 16*1024**2 or (opcode >= 8 and (not final or size > 125)):
                raise OSError('WebSocket-Nachricht zu groß')
            payload = await reader.readexactly(size)
            if opcode == 8: return
            if opcode == 9:
                mask = os.urandom(4)
                writer.write(bytes([138, 128 | len(payload)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
                await writer.drain(); continue
            if opcode == 10: continue
            if opcode in (1, 2):
                if kind is not None: raise OSError('Unerwarteter WebSocket-Fragmentbeginn')
                kind = opcode
            elif opcode != 0 or kind is None:
                raise OSError('Unerwartetes WebSocket-Fragment')
            if kind == 1:
                pending.extend(payload)
                if len(pending) > 2*1024**2: raise OSError('Fortschrittsnachricht zu groß')
            if final:
                if kind == 1:
                    try:
                        value = json.loads(pending)
                        if isinstance(value, dict): yield value
                    except (ValueError, UnicodeError): pass
                pending.clear(); kind = None
    finally:
        connected.clear()
        writer.close()
        try: await writer.wait_closed()
        except OSError: pass
