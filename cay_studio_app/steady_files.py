"""Files read from the Windows drive (0.19 robustness).

Films, voices and pictures live on D: (/mnt/d in WSL2). That link sometimes answers a read with EIO
('OSError: [Errno 5] Input/output error' with a Starlette traceback per range read, Cay's dashboard.log in the
0.19 diagnosis), for example while Windows scans a freshly written MP4 or the drive wakes up. A film in the app asks
for many byte ranges while it plays and seeks, so one bad moment of the drive filled the log.

Two layers keep such a read clean (install() adds both):
- SteadyFiles, innermost (right around the routes, inside the dashboard's guard layers): a failed read is tried once
  more after a short pause. Before the answer started that is the whole request; while a file streams it is only the
  rest from the next byte (a Range request whose start is not sent again), so the player gets the whole film. When the
  same read fails twice: before the answer a short German 503 that the app shows as it is; during a film the answer
  ends.
- QuietEnd, outermost: an answer that had to end early closes the connection, so the player asks again for the rest.
  Without it the guard layers end the answer short as if it were complete, the server refuses that ('Too little data
  for declared Content-Length') and the connection stays stuck, the player waits.
Each case is one line in the log (at most one per address and minute), never a traceback. Every other error, and every
request that is not a GET or HEAD, passes through unchanged.
"""
import asyncio
import contextvars
import errno
import json
import logging
import re
import time

READ_ERRORS = {errno.EIO, errno.ETIMEDOUT, errno.ESTALE, errno.ENXIO}
MESSAGE = 'Das Laufwerk mit deinen Filmen antwortet gerade nicht. Versuch es in ein paar Sekunden noch einmal.'
GAVE_UP = 'cay.drive_gave_up'          # set in the request scope when SteadyFiles ends an answer that already started
ENDED = contextvars.ContextVar('cay_drive_ended', default=False)   # QuietEnd ended this answer on purpose (Hush)


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


class Changed(Exception):
    """The second try answered something else than the rest of the first answer (the file changed meanwhile)."""


class SteadyFiles:
    def __init__(self, app, log=None, pause=.3):
        self.app = app; self.pause = pause; self.noted = {}
        self.log = log or (lambda text: print(text, flush=True))

    def note(self, path, error, what):
        now = time.monotonic()
        if now - self.noted.get(path, -1e9) < 60: return
        if len(self.noted) > 200: self.noted = {p: t for p, t in self.noted.items() if now - t < 60}
        self.noted[path] = now
        self.log(f'Laufwerk-Lesefehler (Errno {error.errno}) bei {path}: {what}')

    def rest(self, scope, start, first, last, forward):
        """The same request once more, only for the bytes the player has not got yet; its start is not sent again."""
        headers = [(k, v) for k, v in scope.get('headers', []) if k.lower() not in (b'range', b'if-range')]
        again, tag = {**scope, 'headers': headers + [(b'range', f'bytes={first}-{last}'.encode())]}, header(start['headers'], 'etag')

        async def deliver(message):
            if message['type'] == 'http.response.start':
                if message['status'] != 206 or span(message) != (first, last) or header(message.get('headers') or [], 'etag') != tag:
                    raise Changed(scope.get('path', ''))
                return
            await forward(message)
        return again, deliver

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in ('GET', 'HEAD'):
            return await self.app(scope, receive, send)
        path, state = scope.get('path', ''), {'start': None, 'sent': 0, 'done': False}

        async def forward(message):
            if message['type'] == 'http.response.start': state['start'] = message
            elif message['type'] == 'http.response.body':
                state['sent'] += len(message.get('body', b'')); state['done'] = not message.get('more_body', False)
            await send(message)
        request, deliver, failure, tried, resumed = scope, forward, None, None, []
        while True:
            try:
                await self.app(request, receive, deliver)
                if failure is not None:
                    self.note(path, failure, f'ab Byte {" und ".join(map(str, resumed))} neu gelesen, Wiedergabe läuft weiter' if resumed else 'beim zweiten Versuch gelesen')
                return
            except Exception as error:
                found = read_error(error)
                if found is None and not resumed: raise          # not the drive's: unchanged
                if found is None: break                          # the rest came back otherwise (file changed): end like a read error
                failure = found
            if state['done']:                                    # the answer is complete, the error came after it
                return self.note(path, failure, 'nach der vollständigen Antwort, nichts verloren')
            whole = span(state['start']) if state['start'] and scope['method'] == 'GET' else None
            at = state['sent'] if state['start'] else -1
            if at == tried or (state['start'] and whole is None): break   # the same read failed twice, or nothing to resume
            tried = at
            await asyncio.sleep(self.pause)
            if state['start'] is None: request, deliver = scope, forward
            else:
                resumed.append(whole[0] + state['sent'])
                request, deliver = self.rest(scope, state['start'], resumed[-1], whole[1], forward)
        if state['start'] is None:
            self.note(path, failure, 'Antwort 503 mit Hinweis')
            body = json.dumps({'detail': MESSAGE}, ensure_ascii=False).encode()
            await send({'type': 'http.response.start', 'status': 503, 'headers': [
                (b'content-type', b'application/json'), (b'content-length', str(len(body)).encode()), (b'retry-after', b'3'), (b'cache-control', b'no-store')]})
            await send({'type': 'http.response.body', 'body': body, 'more_body': False})
            return
        self.note(path, failure, f'diese Antwort endet nach {state["sent"]} Byte, der Player fragt neu an')
        scope[GAVE_UP] = True
        raise failure


class QuietEnd:
    """Outermost: an answer SteadyFiles gave up ends with a closed connection (the player asks again), no traceback."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'GET':          # a HEAD answer has no body to break off
            return await self.app(scope, receive, send)
        state = {'started': False, 'left': None}

        async def guarded(message):
            if message['type'] == 'http.response.start':
                size = header(message.get('headers') or [], 'content-length')
                state.update(started=True, left=int(size) if size and size.isdigit() else None)
            elif message['type'] == 'http.response.body' and state['left'] is not None:
                state['left'] -= len(message.get('body', b''))
                # A guard layer ends the broken answer as if it were complete: not sent, the connection closes below.
                if state['left'] > 0 and not message.get('more_body', False) and scope.get(GAVE_UP): return
            await send(message)
        try:
            await self.app(scope, receive, guarded)
        except Exception:
            if not (state['started'] and scope.get(GAVE_UP)): raise
        if scope.get(GAVE_UP): ENDED.set(True)


class Hush(logging.Filter):
    """uvicorn's own line for an answer QuietEnd ended on purpose: SteadyFiles has already said what happened."""
    def filter(self, record):
        return not (ENDED.get() and 'without completing response' in str(record.msg))


def install(app):
    """SteadyFiles now (call right after creating the app, before any other layer), QuietEnd as the last layer."""
    app.add_middleware(SteadyFiles)
    server_log = logging.getLogger('uvicorn.error')
    if not any(isinstance(f, Hush) for f in server_log.filters): server_log.addFilter(Hush())
    return lambda: app.add_middleware(QuietEnd)
