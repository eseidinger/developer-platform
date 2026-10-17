"""Bounded Bolt 5.4 authentication fence; queries are forwarded unchanged.

SSH or the console's WSS endpoint supplies transport encryption. Never log
protocol data. TLS, impersonation and unreviewed protocol versions fail closed.
"""
import asyncio
import contextlib
import struct
from . import catalog
from .neo4j import admission

MAX_MESSAGE = 1024 * 1024
VERSION = b'\0\0\x04\x05'


class Decoder:
    def __init__(self, data):
        self.data, self.offset, self.items = data, 0, 0

    def take(self, count):
        if count < 0 or self.offset + count > len(self.data): raise ValueError('Truncated frame')
        value = self.data[self.offset:self.offset + count]
        self.offset += count
        return value

    def number(self, size):
        return int.from_bytes(self.take(size), 'big')

    def value(self, depth=0):
        self.items += 1
        if depth > 32 or self.items > 16384: raise ValueError('Protocol nesting limit')
        marker = self.number(1)
        if marker < 0x80: return marker
        if marker >= 0xf0: return marker - 256
        if marker in (0xc0, 0xc2, 0xc3): return {0xc0: None, 0xc2: False, 0xc3: True}[marker]
        if marker == 0xc1: return struct.unpack('!d', self.take(8))[0]
        if 0xc8 <= marker <= 0xcb: return int.from_bytes(self.take(1 << (marker - 0xc8)), 'big', signed=True)
        if 0x80 <= marker <= 0x8f or marker in (0xd0, 0xd1, 0xd2):
            size = marker & 15 if marker < 0x90 else self.number(1 << (marker - 0xd0))
            return self.take(size).decode('utf-8')
        if marker in (0xcc, 0xcd, 0xce): return self.take(self.number(1 << (marker - 0xcc)))
        if 0x90 <= marker <= 0x9f or marker in (0xd4, 0xd5, 0xd6):
            size = marker & 15 if marker < 0xa0 else self.number(1 << (marker - 0xd4))
            if size > 16384: raise ValueError('Protocol list limit')
            return [self.value(depth + 1) for _ in range(size)]
        if 0xa0 <= marker <= 0xaf or marker in (0xd8, 0xd9, 0xda):
            size = marker & 15 if marker < 0xb0 else self.number(1 << (marker - 0xd8))
            if size > 1024: raise ValueError('Protocol map limit')
            result = {}
            for _ in range(size):
                key = self.value(depth + 1)
                if not isinstance(key, str) or key in result: raise ValueError('Ambiguous map')
                result[key] = self.value(depth + 1)
            return result
        if 0xb0 <= marker <= 0xbf:
            tag = self.number(1)
            return (tag, [self.value(depth + 1) for _ in range(marker & 15)])
        raise ValueError('Unsupported PackStream value')


def validate(data, lease, state):
    decoder = Decoder(data)
    message = decoder.value()
    if decoder.offset != len(data) or not isinstance(message, tuple): raise ValueError('Invalid message')
    tag, fields = message
    expected = {1: 1, 0x6a: 1, 0x6b: 0, 0x10: 3, 0x11: 1, 0x12: 0, 0x13: 0,
        0x2f: 1, 0x3f: 1, 0x0f: 0, 2: 0, 0x66: 3, 0x54: 1}
    if tag not in expected or len(fields) != expected[tag]: raise ValueError('Unreviewed message')
    if tag == 1:
        if state['hello'] or not isinstance(fields[0], dict): raise ValueError('Repeated HELLO')
        if set(fields[0]) & {'scheme', 'principal', 'credentials', 'imp_user'}: raise ValueError('Unexpected auth')
        state['hello'] = True
    elif tag == 0x6a:
        if not state['hello'] or state['auth']: raise ValueError('Invalid LOGON state')
        auth = fields[0]
        if (not isinstance(auth, dict) or set(auth) != {'scheme', 'principal', 'credentials'}
                or auth['scheme'] != 'basic' or auth['principal'] != catalog.login(lease['credential_id'])
                or not isinstance(auth['credentials'], str)):
            raise ValueError('Lease identity mismatch')
        admission(auth['credentials'], lease)
        state['auth'] = True
    elif tag == 0x6b:
        if not state['auth']: raise ValueError('Invalid LOGOFF')
        state['auth'] = False
    elif tag != 2 and not state['auth']:
        raise ValueError('Authentication required')
    if tag in {0x10, 0x11}:
        extra = fields[-1]
        if not isinstance(extra, dict) or 'imp_user' in extra: raise ValueError('Impersonation unavailable')
        if extra.get('db', 'neo4j') not in {'neo4j', 'system'}: raise ValueError('Database unavailable')


async def message(reader):
    data, wire = bytearray(), bytearray()
    while True:
        header = await reader.readexactly(2)
        size = int.from_bytes(header, 'big')
        wire.extend(header)
        if len(wire) > MAX_MESSAGE + 8192: raise ValueError('Framing limit')
        if size == 0:
            if not data: return None, bytes(wire)  # Bolt keep-alive NOOP.
            return bytes(data), bytes(wire)
        if len(data) + size > MAX_MESSAGE: raise ValueError('Message limit')
        chunk = await reader.readexactly(size)
        data.extend(chunk)
        wire.extend(chunk)


async def exchange(reader, writer, lease, backend, observe=None):
    upstream = None
    tasks = []
    phase = 'handshake'
    try:
        handshake = await asyncio.wait_for(reader.readexactly(20), 5)
        if handshake[:4] != b'\x60\x60\xb0\x17': raise ValueError('Plain Bolt required')
        offers = [handshake[i:i+4] for i in range(4, 20, 4)]
        if observe: observe('version-offers',','.join(str(v[3])+'.'+str(v[2])+'-range'+str(v[1]) for v in offers))
        if not any(v[0] == 0 and v[3] == 5 and v[2] - v[1] <= 4 <= v[2] for v in offers):
            raise ValueError('Bolt 5.4 support required')
        remote, upstream = await asyncio.wait_for(asyncio.open_connection(*backend), 3)
        upstream.write(handshake[:4] + VERSION + b'\0' * 12)
        await upstream.drain()
        if await asyncio.wait_for(remote.readexactly(4), 5) != VERSION: raise ValueError('Native version mismatch')
        writer.write(VERSION)
        await writer.drain()
        phase = 'authenticated-messages'
        state = {'hello': False, 'auth': False}
        async def requests():
            while True:
                data, wire = await asyncio.wait_for(message(reader), 120)
                if data is not None: validate(data, lease, state)
                upstream.write(wire)
                await upstream.drain()
        async def responses():
            while chunk := await remote.read(65536):
                writer.write(chunk)
                await writer.drain()
        tasks = [asyncio.create_task(requests()), asyncio.create_task(responses())]
        done,_=await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if observe:
            for task in done:
                error=task.exception()
                observe(phase,type(error).__name__ if error else 'Completed')
    except Exception as error:
        if observe: observe(phase,type(error).__name__)
        raise
    finally:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if upstream:
            upstream.close()
            with contextlib.suppress(Exception): await upstream.wait_closed()
