"""Library figure -> figure of a running project: applied now, kept for the next safe point,
or refused with the reason; a voice change is never silently lost."""
import copy
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

from figure_library import Library, IMAGE_LATE, VOICE_LATE, BLOCKED_FIRST  # noqa: E402
from factory_quality import Quality  # noqa: E402
from factory_models import CastProfile  # noqa: E402

PATRICK = 'a' * 32


class Studio(Library):
    voice_changed = Quality.voice_changed

    def __init__(self):
        self.db = sqlite3.connect(':memory:'); self.db.row_factory = sqlite3.Row
        self.busy = None; self.docs = {}
        self.g = {'now': lambda: '2026-10-15T12:00:00+00:00'}
        self.sql('CREATE TABLE factory_runs(id TEXT PRIMARY KEY,document TEXT)')
        self.init_library()
        self.library_save({'id': PATRICK, 'name': 'Patrick', 'label': 'Patrick Knete', 'look': 'clay', 'traits': 'Seestern',
                           'image': 'b' * 32, 'image_mode': 'exact', 'voice': 'c' * 32, 'voice_text': 'Na endlich',
                           'voice_design': {'instruction': 'An adult man, resonant voice.', 'seed': 7}, 'appearance': 'pink starfish'})

    def sql(self, q, a=()): self.db.execute(q, a); self.db.commit()
    def rows(self, q, a=()): return self.db.execute(q, a).fetchall()
    def path(self, p): return Path(p)
    def asset(self, aid, kind=None): return {'id': aid, 'path': f'/assets/{aid}', 'sha256': 'x'}
    def save(self, d): self.docs[d['id']] = copy.deepcopy(d)

    def get(self, rid):
        if rid not in self.docs: raise HTTPException(404, 'Projekt nicht gefunden.')
        return copy.deepcopy(self.docs[rid])


def project(studio, state, **extra):
    scene = lambda who: {'cast': [who], 'dialogues': [{'speaker': who, 'text': 'Hallo', 'emotion': 'fröhlich'}], 'variants': [{'id': 'v', 'key': 'k'}], 'selected': 'v'}
    d = {'id': 'd' * 32, 'state': state, 'idea': {'look': 'cartoon', 'participants': []}, 'voice_approval': 'x', 'previews': [{'episode': 0}],
         'plan': {'cast': [{'name': 'Patrick', 'appearance': 'a pink starfish in shorts'}, {'name': 'SpongeBob', 'appearance': 'yellow sponge'}]},
         'cast_refs': {'Patrick': '/p.png', 'SpongeBob': '/s.png'},
         'episodes': [{'scenes': [scene('Patrick'), scene('SpongeBob'), scene('Patrick')]}], **extra}
    studio.save(d)
    return d['id']


def entry(d, name='Patrick'):
    return next((p for p in d['idea']['participants'] if p['name'] == name), {})


def test_choice_while_the_studio_draws_is_kept_then_applied_at_the_next_safe_point():
    studio = Studio(); rid = project(studio, 'pictures'); studio.busy = rid
    view = studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK))
    assert {(x['part'], x['label']) for x in view['pending_cast']} == {('image', 'Patrick Knete'), ('voice', 'Patrick Knete')}
    assert view['cast_windows'] == {'image': 'later', 'voice': 'later'}
    assert not entry(studio.get(rid))                                  # the worker's copy of the document stays untouched
    d = studio.get(rid)
    assert studio.apply_pending(d) is True                             # the worker itself, between two images
    e = entry(d)
    assert e['image'] == 'b' * 32 and e['library_image'] == PATRICK and e['image_look'] == 'clay'
    assert e['voice'] == 'c' * 32 and e['library_voice'] == PATRICK and e['voice_design']['seed'] == 7
    assert 'Patrick' not in d['cast_refs'] and 'SpongeBob' in d['cast_refs']
    assert d['plan']['cast'][0]['appearance'] == 'pink starfish'       # English description from the library, not Cay's notes
    assert d['state'] == 'pictures' and not studio.pending_cast(rid)


def test_voice_chosen_during_the_mix_waits_for_the_mix_and_is_never_lost():
    studio = Studio(); rid = project(studio, 'audio_mixing')
    with pytest.raises(HTTPException) as refused:
        studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK))      # image too: pictures are chosen
    assert refused.value.status_code == 409 and refused.value.detail == IMAGE_LATE
    view = studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, image=False))
    assert [x['part'] for x in view['pending_cast']] == ['voice']
    studio.sweep_pending()
    assert studio.pending_cast(rid)                                     # still mixing: kept
    d = studio.get(rid); d['state'] = 'voice_review'; studio.save(d)    # the mix is done
    studio.sweep_pending()
    d = studio.get(rid)
    assert d['state'] == 'voicing' and 'voice_approval' not in d and d['previews'] == []
    assert entry(d)['library_voice'] == PATRICK and not studio.pending_cast(rid)


def test_a_failed_mix_resumes_with_the_new_voice():
    studio = Studio(); rid = project(studio, 'blocked', resume_state='audio_mixing', error='Nachbearbeitung: SPRACHPRÜFUNG')
    d = studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, image=False))
    assert d['state'] == 'blocked' and d['resume_state'] == 'voicing' and entry(d)['voice'] == 'c' * 32


def test_refused_once_the_animation_runs_and_while_planning():
    studio = Studio()
    for state, reason in (('rendering', VOICE_LATE), ('finishing', VOICE_LATE)):
        rid = project(studio, state)
        with pytest.raises(HTTPException) as refused:
            studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, image=False))
        assert refused.value.status_code == 409 and refused.value.detail == reason
    rid = project(studio, 'blocked', resume_state='rendering')
    assert studio.cast_windows(studio.get(rid)) == {'image': VOICE_LATE, 'voice': VOICE_LATE}
    rid = project(studio, 'blocked', resume_state='audio_mixing')
    assert studio.cast_windows(studio.get(rid)) == {'image': IMAGE_LATE, 'voice': 'now'}
    rid = project(studio, 'blocked', resume_state='correcting')                # a failed change request: honest reason
    assert set(studio.cast_windows(studio.get(rid)).values()) == {BLOCKED_FIRST}
    rid = project(studio, 'planning')
    assert 'entstehen gerade' in studio.cast_window(studio.get(rid), 'voice')


def test_a_kept_choice_that_missed_its_window_is_dropped_with_a_note():
    studio = Studio(); rid = project(studio, 'pictures'); studio.busy = rid
    studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, voice=False))
    studio.busy = None
    d = studio.get(rid); d['state'] = 'voice_review'; studio.save(d)   # e.g. moved on by hand meanwhile
    studio.sweep_pending()
    d = studio.get(rid)
    assert not studio.pending_cast(rid) and 'nicht übernommen' in d['phase'] and not entry(d)


def test_cancel_and_supersede():
    studio = Studio(); rid = project(studio, 'pictures'); studio.busy = rid
    studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK))
    assert studio.cancel_pending(rid, 'Patrick')['pending_cast'] == []
    studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, image=False))
    studio.busy = None; d = studio.get(rid); d['state'] = 'image_review'; studio.save(d)
    view = studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, image=False))   # now applied at once
    assert view['pending_cast'] == [] and entry(view)['library_voice'] == PATRICK


def test_uses_count_image_and_voice_sources_and_skip_the_trash():
    studio = Studio()
    studio.sql('CREATE TABLE studio_trash(id TEXT PRIMARY KEY,deleted TEXT)')
    for rid, trashed in (('1' * 32, False), ('2' * 32, True)):
        studio.sql('INSERT INTO factory_runs VALUES(?,?)', (rid, '{"idea":{"participants":[{"name":"P","library_voice":"%s"}]}}' % PATRICK))
        if trashed: studio.sql('INSERT INTO studio_trash VALUES(?,?)', (rid, 'x'))
    assert studio.library_uses() == {PATRICK: 1}


def test_an_own_picture_enters_the_library_with_its_mode_never_as_a_frozen_face():
    from factory_models import LibraryFromProject
    studio = Studio(); upload = 'e' * 32
    for mode, expected in (('exact', 'exact'), (None, 'neutral')):          # None: project from before 0.18
        rid = project(studio, 'voice_review', cast_refs={'Patrick': f'/assets/{upload}'})
        d = studio.get(rid); person = {'name': 'Patrick', 'image': upload, 'voice': 'f' * 32, 'voice_text': 'Hallo'}
        if mode: person['image_mode'] = mode
        d['idea']['participants'] = [person]; studio.save(d)
        fig = studio.figure_from_project(LibraryFromProject(project=rid, name='Patrick', label='Patrick Foto'))
        assert fig['image'] == upload and fig['image_mode'] == expected      # the upload itself, not a copy marked 'exact'
        assert fig['voice'] == 'f' * 32 and fig['voice_text'] == 'Hallo' and fig['appearance'] == 'a pink starfish in shorts'


def test_while_the_worker_only_cleans_up_a_review_state_applies_at_once():
    """The worker stays 'busy' for a moment after saving a review state (cache release); a choice
    in that moment must not be kept for later, or 'Bilder übernehmen' could skip it."""
    studio = Studio(); rid = project(studio, 'image_review'); studio.busy = rid
    view = studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK))
    assert view['pending_cast'] == [] and entry(view)['library_image'] == PATRICK and view['state'] == 'pictures'
    rid = project(studio, 'pictures'); studio.busy = rid
    assert studio.cast_windows(studio.get(rid)) == {'image': 'later', 'voice': 'later'}


def test_voice_line_count_reads_both_dialogue_formats():
    studio = Studio(); rid = project(studio, 'voice_review')
    d = studio.get(rid); old = d['episodes'][0]['scenes'][2]
    old.update(dialogues=[], dialogue='Wo ist mein Stein?', speaker='Patrick'); studio.save(d)
    view = studio.apply_profile(rid, CastProfile(name='Patrick', library_id=PATRICK, image=False))
    assert '2 Sätze' in view['phase']
