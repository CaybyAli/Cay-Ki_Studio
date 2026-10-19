"""Files read from the Windows drive (0.19 robustness).

Films, voices and pictures live on D: (/mnt/d in WSL2). That link sometimes answers a read with EIO
('OSError: [Errno 5] Input/output error', Cay's dashboard.log in the 0.18.2 diagnosis), for example while
Windows scans a freshly written MP4 or the drive wakes up. Starlette then printed a full traceback for every
such request, and a film in the app asks for many byte ranges while it plays and seeks.

Two layers keep such a read clean (install() adds both):
- SteadyFiles, innermost (right around the routes, inside the dashboard's guard layers, which would otherwise
  end a broken answer early as if it were complete): during a file answer the rest is asked for again from the
  next byte (three tries, short pauses), so the player gets the whole film; before an answer started, a short
  German 503 that the app shows as it is.
- QuietEnd, outermost: if the drive stays silent, only that one answer ends, without a traceback (the player
  asks again).
Each case is one line in the log (at most one per address and minute). Every other error, and every request
that is not a GET or HEAD, passes through unchanged.
"""
import asyncio
import errno
import json
import re
import time

READ_ERRORS = {errno.EIO, errno.ETIMEDOUT, errno.ESTALE, errno.ENXIO}
MESSAGE = 'Das Laufwerk mit deinen Filmen antwortet gerade nicht. In ein paar Sekunden noch einmal versuchen.'
TRIES = 3
GAVE_UP = 'cay.drive_gave_up'          # set in the request scope once SteadyFiles stops trying


def read_error(error):
    """The drive's read error in `error` (also inside an exception group), else None."""
    if isinstance(error, OSError) and error.errno in READ_ERRORS: return error
    for inner in getattr(error, 'exceptions', None) or ():
        found = read_error(inner)
        if found is not None: return found
    return None


def header(headers, name):
    return next((v.decode('latin-1') for k, v in headers if k.decode('latin-1').lower() == name), None)


def span(start):
    """(first byte, last byte) of a plain file answer from its start message, else None (multipart, unknown size)."""
    headers = start.get('headers') or []
    if start['status'] == 206:
        m = re.fullmatch(r'bytes (\d+)-(\d+)/\d+', header(headers, 'content-range') or '')
        return (int(m.group(1)), int(m.group(2))) if m else None
    size = header(headers, 'content-length')
    return (0, int(size) - 1) if start['status'] == 200 and size and size.isdigit() and int(size) > 0 else None


class SteadyFiles:
    def __init__(self, app, log=None, pause=.3):
        self.app = app; self.pause = pause; self.noted = {}
        self.log = log or (lambda text: print(text, flush=True))

    def note(self, path, error, what):
        now = time.monotonic()
        if now - self.noted.get(path, -1e9) < 60: return
        self.noted[path] = now
        self.log(f'Laufwerk-Lesefehler (Errno {error.errno}) bei {path}: {what}')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in ('GET', 'HEAD'):
            return await self.app(scope, receive, send)
        state = {'start': None, 'sent': 0, 'done': False}

        async def forward(message):
            if message['type'] == 'http.response.start': state['start'] = message
            elif message['type'] == 'http.response.body':
                state['sent'] += len(message.get('body', b'')); state['done'] = not message.get('more_body', False)
            await send(message)
        try:
            return await self.app(scope, receive, forward)
        except Exception as error:
            failure = read_error(error)
            if failure is None: raise
        path = scope.get('path', '')
        if state['start'] is None:
            self.note(path, failure, 'Antwort 503, die App versucht es erneut')
            body = json.dumps({'detail': MESSAGE}, ensure_ascii=False).encode()
            await send({'type': 'http.response.start', 'status': 503, 'headers': [
                (b'content-type', b'application/json'), (b'content-length', str(len(body)).encode()), (b'retry-after', b'3'), (b'cache-control', b'no-store')]})
            await send({'type': 'http.response.body', 'body': body, 'more_body': False})
            return
        whole = span(state['start']) if scope['method'] == 'GET' else None
        for attempt in range(TRIES if whole else 0):
            if state['done']: return
            first = whole[0] + state['sent']
            await asyncio.sleep(self.pause * (attempt + 1))
            # The same request once more, only for the bytes the player has not got yet; its start is not sent again.
            headers = [(k, v) for k, v in scope.get('headers', []) if k.lower() not in (b'range', b'if-range')]
            again = {**scope, 'headers': headers + [(b'range', f'bytes={first}-{whole[1]}'.encode())]}

            async def rest(message):
                if message['type'] == 'http.response.start':
                    if message['status'] != 206 or (span(message) or (None,))[0] != first: raise OSError(errno.EIO, 'Antwort passt nicht zum Rest')
                    return
                await forward(message)
            try:
                await self.app(again, receive, rest)
                self.note(path, failure, f'ab Byte {first} neu gelesen, Wiedergabe läuft weiter'); return
            except Exception as error:
                failure = read_error(error) or failure
                if read_error(error) is None and not isinstance(error, OSError): raise
        if not state['done']:
            self.note(path, failure, 'diese Antwort endet, der Player fragt neu an')
            scope[GAVE_UP] = True; raise failure


class QuietEnd:
    """Outermost: an answer the drive broke off ends here quietly instead of with a traceback per request."""
    def __init__(self, app, log=None):
        self.app = app; self.log = log or (lambda text: print(text, flush=True))

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in ('GET', 'HEAD'):
            return await self.app(scope, receive, send)
        started = False

        async def tracked(message):
            nonlocal started
            if message['type'] == 'http.response.start': started = True
            await send(message)
        try:
            await self.app(scope, receive, tracked)
        except Exception as error:
            # The server itself may refuse the short ending ('Response content shorter than Content-Length').
            if not started or not (scope.get(GAVE_UP) or read_error(error) is not None): raise
            if not scope.get(GAVE_UP): self.log(f'Laufwerk-Lesefehler bei {scope.get("path", "")}: diese Antwort endet, der Player fragt neu an')


def install(app):
    """SteadyFiles now (call right after creating the app, before any other layer), QuietEnd as the last layer."""
    app.add_middleware(SteadyFiles)
    return lambda: app.add_middleware(QuietEnd)
