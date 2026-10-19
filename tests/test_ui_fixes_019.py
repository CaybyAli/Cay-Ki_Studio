"""0.19 app fixes from Cay's notes: own figure pictures that did not take effect (B4), the trash (B1) and
films read from a Windows drive that answers with an I/O error.

A real Factory on a temporary database (tests/studio_fakes.py) with a fake ComfyUI that finishes every image
at once; routes are called through FastAPI's TestClient like the app calls them."""
import asyncio

import pytest

from studio_fakes import client, factory as studio, project
from test_episode_looks import finishing, png, references, staged

RID = 'b' * 32
CAST = [{'name': 'Lena', 'appearance': 'young woman, red coat', 'personality': 'klug', 'voice_preset': 'young_woman'},
        {'name': 'Markus', 'appearance': 'man, grey suit', 'personality': 'stur', 'voice_preset': 'man'}]


def scene(cast):
    return {'title': 'Szene', 'action': 'Lena hält den Keks.', 'still': 'Lena holds a cookie', 'kind': 'line', 'location': 'Küche', 'camera': 'medium shot',
            'cast': cast, 'dialogues': [{'speaker': cast[0], 'text': 'Hallo, Markus!', 'emotion': 'ruhig', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'attempt', 'variants': [], 'selected': None, 'round': 0}


def figures(tmp_path, monkeypatch, state='cast_review', **extra):
    """Two designed figures (the check stop), a fake ComfyUI that draws at once."""
    import factory
    f = studio(tmp_path, monkeypatch); finishing(f)
    monkeypatch.setattr(factory, 'validate_nodes', lambda info: {})

    async def info(): return {}
    f.object_info = info
    folder = f.g['ROOT'] / '01_Projekte/Studio' / RID / '02_Bilder'
    refs = {'Lena': str(png(folder / 'lena.png', 'Lena design')), 'Markus': str(png(folder / 'markus.png', 'Markus design'))}
    project(f, RID, state, {'plan': {'title': 'Keks', 'cast': [dict(p) for p in CAST], 'style': 'Bright cartoon look.', 'mood': 'playful'},
                            'episodes': [{'title': 'Keks', 'scenes': [scene(['Lena', 'Markus']), scene(['Lena'])]}], 'cast_refs': refs, **extra},
            {'cast_check': True, 'look': 'cartoon'})
    return f, client(f)


def upload(http, tmp_path, text):
    picture = png(tmp_path / (text.replace(' ', '_') + '.png'), text)
    answer = http.post('/api/factory/assets?kind=image&name=' + picture.name, content=picture.read_bytes())
    assert answer.status_code == 200, answer.text
    return answer.json()['id'], picture


def entry(d, name='Markus'):
    return next((p for p in d['idea']['participants'] if p['name'] == name), {})


# ---------- B4: "Eigenes Bild hochladen" ----------

def test_own_picture_reaches_the_figure_end_to_end(tmp_path, monkeypatch):
    """Guard for the whole way: request, stored asset, the figure's reference, the drawn sheet from exactly this
    picture, and a new picture address (cache key) for the app."""
    f, http = figures(tmp_path, monkeypatch)
    old_ref = f.get(RID)['cast_refs']['Markus']
    aid, picture = upload(http, tmp_path, 'Cays Markus')
    answer = http.post(f'/api/factory/{RID}/cast/image', json={'name': 'Markus', 'asset_id': aid})
    assert answer.status_code == 200 and answer.json()['state'] == 'pictures' and 'Markus' not in answer.json()['cast_refs']
    assert entry(answer.json()) == {'name': 'Markus', 'traits': '', 'image': aid, 'voice': None, 'image_mode': 'neutral'}
    asyncio.run(f.pictures(f.get(RID)))
    d = f.get(RID)
    assert d['state'] == 'cast_review' and d['cast_refs']['Markus'] != old_ref and d['cast_refs']['Lena'].endswith('lena.png')
    sheet = next(body['prompt'] for _, body in f.services.prompts() if f.rows('SELECT step_key FROM factory_steps WHERE id=?',
                 (body['extra_data']['cay_factory_step'],))[0]['step_key'].startswith('castup:Markus:'))
    assert references(sheet) == [staged(picture)]                         # drawn from exactly the uploaded file
    served = http.get(f'/api/factory/{RID}/cast-image/1')
    assert served.status_code == 200 and served.content == open(d['cast_refs']['Markus'], 'rb').read()


def test_picture_chosen_while_the_studio_draws_is_kept_then_taken_at_the_next_safe_point(tmp_path, monkeypatch):
    """Before 0.19 this was refused (409) and the message lay under the figure sheet: Cay saw nothing happen."""
    f, http = figures(tmp_path, monkeypatch, 'pictures')
    aid, _ = upload(http, tmp_path, 'Cays Markus')
    f.busy = RID                                                           # the worker draws an image of this project
    answer = http.post(f'/api/factory/{RID}/cast/image', json={'name': 'Markus', 'asset_id': aid})
    assert answer.status_code == 200, answer.text
    assert [(x['name'], x['part'], x.get('own'), x['label']) for x in answer.json()['pending_cast']] == [('Markus', 'image', True, 'dein Bild')]
    assert not entry(f.get(RID)) and 'Markus' in f.get(RID)['cast_refs']   # the worker's copy of the document stays untouched
    d = f.get(RID)
    assert f.apply_pending(d) is True                                      # the worker itself, between two images
    assert entry(d)['image'] == aid and entry(d)['image_mode'] == 'neutral' and 'Markus' not in d['cast_refs']
    assert d['phase'] == 'Dein Bild für Markus übernommen' and not f.pending_cast(RID)
    f.busy = None
    asyncio.run(f.pictures(f.get(RID)))
    assert f.get(RID)['state'] == 'cast_review' and f.get(RID)['cast_refs']['Markus'] != d.get('cast_refs', {}).get('Markus')


def library_choice_kept(f, http, tmp_path):
    """Cay picked a library figure for Markus while the studio drew: kept for the next safe point."""
    from factory_models import CastProfile
    lib, _ = upload(http, tmp_path, 'Markus Knete')
    fig = f.library_save({'id': 'c' * 32, 'name': 'Markus', 'label': 'Markus Knete', 'look': 'cartoon', 'traits': 'x', 'image': lib, 'image_mode': 'exact',
                          'voice': None, 'voice_text': '', 'voice_design': None})
    f.busy = RID
    assert [x['part'] for x in f.apply_profile(RID, CastProfile(name='Markus', library_id=fig['id'], voice=False))['pending_cast']] == ['image']
    f.busy = None
    return lib


def test_a_kept_library_picture_never_comes_back_over_an_own_picture(tmp_path, monkeypatch):
    f, http = figures(tmp_path, monkeypatch, 'pictures')
    lib = library_choice_kept(f, http, tmp_path)
    aid, _ = upload(http, tmp_path, 'Cays Markus')
    assert http.post(f'/api/factory/{RID}/cast/image', json={'name': 'Markus', 'asset_id': aid}).status_code == 200
    f.sweep_pending(); f.apply_pending(f.get(RID))                         # every safe point after it
    assert entry(f.get(RID))['image'] == aid != lib and not f.pending_cast(RID)


def test_a_kept_library_picture_never_comes_back_over_a_redesign(tmp_path, monkeypatch):
    f, http = figures(tmp_path, monkeypatch, 'pictures')
    library_choice_kept(f, http, tmp_path)
    assert http.post(f'/api/factory/{RID}/cast/redo', json={'name': 'Markus'}).status_code == 200
    f.sweep_pending()
    d = f.get(RID)
    assert not entry(d).get('library_image') and d['plan']['cast'][1]['design_round'] == 1 and not f.pending_cast(RID)


def test_a_kept_own_picture_that_missed_its_window_is_dropped_with_a_note(tmp_path, monkeypatch):
    f, http = figures(tmp_path, monkeypatch, 'pictures')
    aid, _ = upload(http, tmp_path, 'Cays Markus')
    f.busy = RID; http.post(f'/api/factory/{RID}/cast/image', json={'name': 'Markus', 'asset_id': aid}); f.busy = None
    d = f.get(RID); d['state'] = 'voice_review'; f.save(d)                # moved on by hand meanwhile
    f.sweep_pending()
    d = f.get(RID)
    assert not f.pending_cast(RID) and 'Bild für Markus nicht übernommen' in d['phase'] and not entry(d)


@pytest.mark.parametrize('state', ['rendering', 'voicing'])
def test_own_picture_still_refused_once_the_pictures_are_chosen(tmp_path, monkeypatch, state):
    f, http = figures(tmp_path, monkeypatch, state)
    aid, _ = upload(http, tmp_path, 'Cays Markus')
    answer = http.post(f'/api/factory/{RID}/cast/image', json={'name': 'Markus', 'asset_id': aid})
    assert answer.status_code == 409 and not f.pending_cast(RID) and not entry(f.get(RID))


# ---------- B1: the trash ----------

def trashed(f, http, rid, title, films=0, picture=None):
    scenes = [{**scene(['Lena']), 'selected': picture, 'variants': [{'id': picture, 'key': 'image:0:0:0:0'}] if picture else []}]
    project(f, rid, 'done', {'title': title, 'episodes': [{'title': title, 'scenes': scenes}],
                             'exports': [{'file': f'Folge_{i + 1:02}.mp4', 'episode': i} for i in range(films)]}, paused=1)
    root = f.g['ROOT']
    (root / '01_Projekte/Studio' / rid / '02_Bilder').mkdir(parents=True); (root / '01_Projekte/Studio' / rid / '02_Bilder/1.png').write_bytes(b'png')
    if films:
        (root / '03_Fertige_Videos/Studio' / rid).mkdir(parents=True); (root / '03_Fertige_Videos/Studio' / rid / 'Folge_01.mp4').write_bytes(b'mp4')
    assert http.post(f'/api/factory/{rid}/delete').status_code == 200


def test_trash_lists_a_card_per_project_not_whole_documents(tmp_path, monkeypatch):
    """Cay's trash was a run-on line of blue links; the trash page shows picture, title, date and films."""
    f, http = figures(tmp_path, monkeypatch)
    trashed(f, http, 'c' * 32, 'Butterblitz', films=2, picture='s' * 32)
    trashed(f, http, 'd' * 32, 'Der Döner-Detektiv')
    cards = http.get('/api/factory/trash').json()['runs']
    assert [c['title'] for c in cards] == ['Der Döner-Detektiv', 'Butterblitz']           # newest first
    butter = cards[1]
    assert butter['films'] == 2 and butter['picture'] == f'/api/factory/{"c" * 32}/picture/{"s" * 32}' and butter['deleted_at'] and butter['state'] == 'done'
    assert cards[0]['picture'] is None and 'episodes' in cards[0] and 'idea' not in cards[0] and 'plan' not in cards[0]
    listed = [r['id'] for r in http.get('/api/factory').json()['runs']]
    assert 'c' * 32 not in listed and RID in listed                                       # hidden from the projects


def test_empty_trash_keeps_films_by_default_and_a_project_still_computing(tmp_path, monkeypatch):
    f, http = figures(tmp_path, monkeypatch)
    root = f.g['ROOT']; keep = root / '00_Eingang/Studio_Referenzen/figur.png'; keep.parent.mkdir(parents=True, exist_ok=True); keep.write_bytes(b'library')
    for rid, title in (('c' * 32, 'Butterblitz'), ('d' * 32, 'Harry Butter'), ('e' * 32, 'Säure & Glanz')):
        trashed(f, http, rid, title, films=1)
    f.busy = 'e' * 32                                                                     # its step still runs
    answer = http.post('/api/factory/trash/empty', json={})
    assert answer.json() == {'ok': True, 'purged': 2, 'kept': ['Säure & Glanz'], 'films_kept': True}
    assert [c['id'] for c in http.get('/api/factory/trash').json()['runs']] == ['e' * 32]
    assert not (root / '01_Projekte/Studio' / ('c' * 32)).exists() and (root / '03_Fertige_Videos/Studio' / ('c' * 32) / 'Folge_01.mp4').exists()
    assert f.get(RID)['state'] == 'cast_review' and keep.read_bytes() == b'library'       # outside the trash nothing changes
    f.busy = None
    assert http.post('/api/factory/trash/empty', json={'films': True}).json()['films_kept'] is False
    assert not (root / '03_Fertige_Videos/Studio' / ('e' * 32)).exists() and http.get('/api/factory/trash').json()['runs'] == []


def test_a_project_in_the_trash_is_locked_and_comes_back_paused(tmp_path, monkeypatch):
    f, http = figures(tmp_path, monkeypatch)
    assert http.post(f'/api/factory/{RID}/delete').json()['deleted'] is True
    d = http.post(f'/api/factory/{RID}/restore', json={}).json()
    assert d['deleted'] is False and d['paused'] is True and d['state'] == 'cast_review'
    assert http.post(f'/api/factory/{RID}/resume').json()['paused'] is False              # 'Rückgängig' of a project that ran


# ---------- films from the Windows drive: EIO while streaming ----------

FILM = bytes(range(256)) * 1200                     # 300 KB, five of Starlette's 64 KB chunks


def drive_app(tmp_path, monkeypatch, fail_at=(), before=False, silent_from=None):
    """A file route behind a BaseHTTPMiddleware (like the dashboard's local guard). Reads that reach one of the
    offsets in `fail_at` raise EIO once, as /mnt/d did in Cay's log; from `silent_from` on every read fails;
    `before`: the route itself fails first."""
    import errno
    import anyio
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.testclient import TestClient
    import steady_files
    film = tmp_path / 'Folge_01.mp4'; film.write_bytes(FILM)
    pending = set(fail_at); real = anyio.open_file

    class Shaky:
        def __init__(self, inner): self.inner = inner; self.at = 0
        async def __aenter__(self): await self.inner.__aenter__(); return self
        async def __aexit__(self, *a): return await self.inner.__aexit__(*a)
        async def seek(self, offset): self.at = offset; return await self.inner.seek(offset)
        async def read(self, size):
            hit = next((x for x in sorted(pending) if self.at <= x < self.at + size), None)
            if hit is not None or (silent_from is not None and self.at + size > silent_from):
                pending.discard(hit); raise OSError(errno.EIO, 'Input/output error')
            data = await self.inner.read(size); self.at += len(data); return data

    async def shaky(path, mode='r', *a, **kw): return Shaky(await real(path, mode, *a, **kw))
    monkeypatch.setattr(anyio, 'open_file', shaky)
    app = FastAPI(); lines = []
    finish = steady_files.install(app)                                       # as in server.py: first the inner layer

    @app.middleware('http')
    async def guard(request, call_next): return await call_next(request)    # the dashboard's local guard

    @app.get('/film')
    def film_route():
        if before: raise OSError(errno.EIO, 'Input/output error')
        return FileResponse(film, media_type='video/mp4')
    finish()
    for layer in app.user_middleware:
        if layer.cls in (steady_files.SteadyFiles, steady_files.QuietEnd): layer.kwargs['log'] = lines.append
    app.user_middleware[-1].kwargs['pause'] = 0
    return TestClient(app, raise_server_exceptions=True), lines


def test_a_read_error_while_a_film_streams_reads_on_from_the_next_byte(tmp_path, monkeypatch, capsys):
    """Cay's dashboard.log: 'OSError: [Errno 5] Input/output error' with a Starlette traceback per range read."""
    http, lines = drive_app(tmp_path, monkeypatch, fail_at=(70_000, 200_000))
    whole = http.get('/film')
    assert whole.status_code == 200 and whole.content == FILM                             # nothing lost, nothing twice
    part = http.get('/film', headers={'Range': 'bytes=1000-150000'})
    assert part.status_code == 206 and part.content == FILM[1000:150001]
    assert len(lines) == 1 and lines[0].startswith('Laufwerk-Lesefehler (Errno 5) bei /film: ab Byte 65536 neu gelesen')
    assert 'Traceback' not in capsys.readouterr().err


def test_a_drive_that_stays_silent_ends_only_that_answer_without_a_traceback(tmp_path, monkeypatch, capsys):
    http, lines = drive_app(tmp_path, monkeypatch, silent_from=70_000)       # every read after 64 KB fails
    answer = http.get('/film', headers={'Range': 'bytes=0-'})
    assert answer.status_code == 206 and len(answer.content) == 65536 and answer.content == FILM[:65536]
    assert lines == ['Laufwerk-Lesefehler (Errno 5) bei /film: diese Antwort endet, der Player fragt neu an']
    assert 'Traceback' not in capsys.readouterr().err


def test_a_read_error_before_the_answer_is_a_short_german_503(tmp_path, monkeypatch):
    http, lines = drive_app(tmp_path, monkeypatch, before=True)
    answer = http.get('/film')
    assert answer.status_code == 503 and answer.json() == {'detail': 'Das Laufwerk mit deinen Filmen antwortet gerade nicht. In ein paar Sekunden noch einmal versuchen.'}
    assert answer.headers['retry-after'] == '3' and len(lines) == 1


def test_other_errors_pass_through_unchanged(tmp_path, monkeypatch):
    import steady_files
    assert steady_files.read_error(FileNotFoundError(2, 'x')) is None and steady_files.read_error(ValueError('x')) is None
    assert steady_files.read_error(ExceptionGroup('g', [OSError(5, 'Input/output error')])).errno == 5


def test_the_dashboard_wraps_every_layer_with_it(tmp_path, monkeypatch):
    import json as js, sys
    runtime = tmp_path / 'studio'; (runtime / 'config').mkdir(parents=True); (tmp_path / 'ablage').mkdir()
    (runtime / 'config/ablage.json').write_text(js.dumps({'wsl_root': str(tmp_path / 'ablage'), 'windows_root': 'D:\\Cay_Studio',
                                                          'local_services': {'comfyui': 'http://127.0.0.1:9', 'ollama': 'http://127.0.0.1:9'}}))
    monkeypatch.setenv('CAY_STUDIO_RUNTIME', str(runtime)); sys.modules.pop('server', None)
    import server
    from steady_files import SteadyFiles, QuietEnd
    layers = [m.cls for m in server.app.user_middleware]                     # outermost first
    assert layers[0] is QuietEnd and layers[-1] is SteadyFiles and len(layers) >= 4  # the guards lie between them
