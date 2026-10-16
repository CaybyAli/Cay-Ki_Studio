"""Cay's reports from his 0.17 series 'Gangster SpongeBob in Bikini Bottom' (6 episodes, 90 s):
1. "Im Original und in deiner Liste stehen mehr als acht Figuren: Spongebob, Patrick, Larry, … SpongeBob Schwammkopf,
   Patrick Star, Mr Krabs, … Larry der Hummer, Krabs" – one figure under several names counted several times.
2. "1 validation error for SourceNote summary String should have at most 2200 characters" – a model text that is
   too long stopped the whole planning after two attempts ("keine Textlängen-Sperre").
3. "6 Folgen ausgewählt, aber nur 5 erstellt" – the planning now stops before any picture if the count differs."""
import asyncio
import json

import httpx
import pytest

from studio_fakes import Services, factory  # noqa: F401  (adds cay_studio_app to the path)
from factory_cast import merge_figure, same_figure
from factory import fit_lengths
from factory_models import SeriesPlan
from story_source import SourceNote, compact_notes

CAY = ('Spongebob, Patrick, Larry, Perla, Sandy, Thaddäus, Plankton, Mr. Krabs, SpongeBob Schwammkopf, Patrick Star, '
       'Mr Krabs, Sandy Cheeks, Thaddäus Tentakel, Perla Krabs, Larry der Hummer, Krabs, Larry dem Hummer').split(', ')


def collect(names):
    known = []
    for name in names:
        if not merge_figure(name, known): known.append(name)
    return known


def test_one_figure_under_several_names_is_one_figure():
    assert collect(CAY) == ['Spongebob', 'Patrick', 'Larry', 'Perla', 'Sandy', 'Thaddäus', 'Plankton', 'Mr. Krabs']
    # The full name first: the short forms join it.
    assert collect(['SpongeBob Schwammkopf', 'Spongebob', 'Mr Krabs', 'Krabs', 'Perla Krabs']) == ['SpongeBob Schwammkopf', 'Mr Krabs', 'Perla Krabs']


def test_different_figures_stay_apart():
    assert not same_figure('Tim', 'Tims Oma')
    assert not same_figure('Perla Krabs', 'Mr. Krabs')
    assert not same_figure('Ann-Marie', 'Ann')
    assert merge_figure('Max', ['Max Müller', 'Max Schmidt']) is None          # two would fit: no guess
    assert collect(['Oma', 'Opa', 'Herr Müller', 'Frau Müller', 'Mr. Smith', 'Mrs. Smith', 'Müller']) == ['Oma', 'Opa', 'Herr Müller', 'Frau Müller', 'Mr. Smith', 'Mrs. Smith', 'Müller']   # which Müller: no guess


def test_a_too_long_model_text_is_cut_at_a_sentence_end():
    summary = ' '.join(f'Satz {i} über die Gangster von Bikini Bottom.' for i in range(120))
    fitted = fit_lengths(SourceNote, {'summary': summary})['summary']
    assert len(fitted) <= 2200 and fitted.endswith('.') and summary.startswith(fitted)
    # Nested texts too; a list that is too long (figures) is never shortened here.
    cast = [{'name': f'Figur {i}', 'appearance': 'A' * 1500, 'personality': 'freundlich'} for i in range(13)]
    header = {'title': 'Gangster', 'synopsis': 'x' * 10, 'style': 'clay', 'visual': 'clay', 'mood': 'playful', 'cast': cast, 'episodes': []}
    fitted = fit_lengths(SeriesPlan, json.loads(json.dumps(header)))
    assert len(fitted['cast']) == 13 and all(len(p['appearance']) <= 1000 for p in fitted['cast'])


def test_planning_survives_a_too_long_summary(tmp_path, monkeypatch):
    services = Services()
    long = ' '.join(f'Satz {i} der Zusammenfassung.' for i in range(200))       # ~5000 characters, schema allows 2200
    services.chat = lambda request, body: httpx.Response(200, json={'done': True, 'done_reason': 'stop',
                                                                    'message': {'content': json.dumps({'summary': long})}})
    f = factory(tmp_path, monkeypatch, services)
    f.idle = lambda *a, **kw: asyncio.sleep(0)
    result = asyncio.run(f.llm(SourceNote, 'Fasse zusammen.', {'source': 'Text'}))
    assert 0 < len(result['summary']) <= 2200
    assert sum(1 for path, _ in services.calls if path == '/api/chat') == 1          # no correction rounds needed


def test_compacting_never_stops_for_length():
    async def llm(schema, instruction, data): return {'summary': data['source_notes']}   # a model that does not shorten
    notes = [f'Folge {i}: ' + 'Wichtiges Ereignis. ' * 200 for i in range(6)]
    text = asyncio.run(compact_notes(llm, notes, {}, lambda: None, limit=11000))
    assert len(text) <= 11000 and all(f'Folge {i}:' in text for i in range(6))


def test_delete_for_good_from_the_trash(tmp_path, monkeypatch):
    """Cay: "ich kann pausierte und fertige Videos nicht löschen … Ich will es löschen können." """
    from studio_fakes import project, client
    f = factory(tmp_path, monkeypatch)
    api = client(f)
    root = f.g['ROOT']
    for rid in ('a' * 32, 'b' * 32):
        project(f, rid, 'done', {'exports': [{'file': 'x.mp4'}]}, paused=1)
        (root / '01_Projekte/Studio' / rid / '02_Bilder').mkdir(parents=True); (root / '01_Projekte/Studio' / rid / '02_Bilder/1.png').write_bytes(b'png')
        (root / '03_Fertige_Videos/Studio' / rid).mkdir(parents=True); (root / '03_Fertige_Videos/Studio' / rid / 'Folge_01.mp4').write_bytes(b'mp4')
    keep = root / '00_Eingang/Studio_Referenzen/figur.png'; keep.parent.mkdir(parents=True); keep.write_bytes(b'library')
    assert api.post(f'/api/factory/{"a" * 32}/purge', json={}).status_code == 409          # only from the trash
    assert api.post(f'/api/factory/{"a" * 32}/delete').status_code == 200
    assert api.post(f'/api/factory/{"a" * 32}/purge', json={}).json() == {'ok': True, 'films_kept': True}
    assert not (root / '01_Projekte/Studio' / ('a' * 32)).exists() and (root / '03_Fertige_Videos/Studio' / ('a' * 32) / 'Folge_01.mp4').exists()
    assert not f.rows('SELECT id FROM factory_runs WHERE id=?', ('a' * 32,)) and not f.rows('SELECT id FROM studio_trash')
    api.post(f'/api/factory/{"b" * 32}/delete')
    assert api.post(f'/api/factory/{"b" * 32}/purge', json={'films': True}).json()['films_kept'] is False
    assert not (root / '03_Fertige_Videos/Studio' / ('b' * 32)).exists() and keep.read_bytes() == b'library'
