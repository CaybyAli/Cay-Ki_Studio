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
