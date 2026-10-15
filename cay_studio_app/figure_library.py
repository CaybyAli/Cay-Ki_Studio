"""Cay's figure library: figures with image and voice that every project can reuse.

A library figure is a profile such as "Patrick Knete": the name used in stories, an image
(an approved design sheet or Cay's own picture), optionally a voice (a designed voice with
its design recipe, or Cay's own recording) and a short description. Projects copy the
references they need; deleting a library figure never touches a project.

Stored as JSON documents in figure_library (same pattern as factory_runs); files live in the
asset store (factory_assets), so projects and the library share one integrity check.
"""
import json
import shutil
from pathlib import Path

from fastapi import HTTPException

from factory_models import LibraryFigure, LibraryFromProject, CastProfile

LOOKS = {'auto': 'Jeder Look', 'clay': 'Knete', 'cartoon': 'Cartoon', 'film': 'Film', 'paper': 'Papier'}
IMAGE_STATES = ('cast_review', 'pictures', 'image_review')
VOICE_STATES = ('cast_review', 'pictures', 'image_review', 'voicing', 'audio_mixing', 'voice_review')
IMAGE_LATE = 'Die Szenenbilder sind schon gewählt. Bilder lassen sich bis zur Bildauswahl tauschen.'
VOICE_LATE = 'Die Animation hat begonnen. Bild und Stimme lassen sich jetzt nur in einer neuen Fassung tauschen.'
BLOCKED_FIRST = 'Die Produktion ist angehalten. Erst „Fortsetzen“ wählen, danach kannst du Bild und Stimme tauschen.'
WORKER_STATES = ('planning', 'pictures', 'voicing', 'rendering', 'correcting')


def drop_library_voice(participant):
    """The figure gets a studio-designed voice: no recording, no library voice, no recipe."""
    participant['voice'] = None; participant['voice_text'] = ''
    participant.pop('voice_design', None); participant.pop('library_voice', None)
    if not participant.get('library_image'): participant.pop('library_id', None)


def file_sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def voice_peaks(path, bars=36):
    """Loudness outline of a voice (0..1 per bar) for the card's waveform; plain stdlib."""
    import array, wave
    try:
        with wave.open(str(path)) as w:
            if w.getsampwidth() != 2: return []
            frames = array.array('h', w.readframes(w.getnframes()))
            channels = w.getnchannels()
    except (OSError, EOFError, wave.Error):
        return []
    if channels > 1: frames = frames[::channels]
    if not frames: return []
    step = max(1, len(frames) // bars)
    peaks = [max((abs(x) for x in frames[i:i + step]), default=0) for i in range(0, step * bars, step)][:bars]
    top = max(peaks) or 1
    return [round(x / top, 2) for x in peaks]


class Library:
    def init_library(self):
        self.sql('CREATE TABLE IF NOT EXISTS figure_library(id TEXT PRIMARY KEY,document TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL)')
        # Library choices made while the project computes; applied by the worker at a safe point.
        self.sql('CREATE TABLE IF NOT EXISTS factory_cast_pending(run_id TEXT NOT NULL,name TEXT NOT NULL,part TEXT NOT NULL,library_id TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(run_id,name,part))')

    # ---------- storage ----------
    def library_figure(self, fid, deleted=False):
        rows = self.rows('SELECT document FROM figure_library WHERE id=?', (fid,))
        if not rows: raise HTTPException(404, 'Figur nicht in deiner Bibliothek.')
        doc = json.loads(rows[0]['document'])
        if doc.get('deleted') and not deleted: raise HTTPException(404, 'Figur wurde aus der Bibliothek entfernt.')
        return doc

    def library_figures(self):
        docs = [json.loads(r['document']) for r in self.rows('SELECT document FROM figure_library ORDER BY updated DESC')]
        used = self.library_uses()
        return [dict(doc, uses=used.get(doc['id'], 0)) for doc in docs if not doc.get('deleted')]

    def library_save(self, doc):
        now = self.g['now'](); doc['updated'] = now; doc.setdefault('created', now)
        if doc.get('voice') and doc.get('peaks_of') != doc['voice']:
            try: doc['voice_peaks'] = voice_peaks(self.path(Path(self.asset(doc['voice'], 'voice')['path'])))
            except HTTPException: doc['voice_peaks'] = []
            doc['peaks_of'] = doc['voice']
        if not doc.get('voice'): doc['voice_peaks'] = []; doc.pop('peaks_of', None)
        self.sql('INSERT INTO figure_library(id,document,created,updated) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document,updated=excluded.updated',
                 (doc['id'], json.dumps(doc, ensure_ascii=False, sort_keys=True), doc['created'], now))
        return doc

    def library_uses(self):
        """How many projects use each library figure (shown on the cards; deleting stays safe)."""
        counts = {}
        try: trash = {r['id'] for r in self.rows('SELECT id FROM studio_trash')}
        except Exception: trash = set()
        for r in self.rows('SELECT id,document FROM factory_runs'):
            if r['id'] in trash: continue
            try: d = json.loads(r['document'])
            except ValueError: continue
            used = set()
            for p in d.get('idea', {}).get('participants', []):
                used |= {p.get(k) for k in ('library_id', 'library_image', 'library_voice') if p.get(k)}
            for fid in used: counts[fid] = counts.get(fid, 0) + 1
        return counts

    def register_file(self, kind, source, name):
        """Copy a project file into the asset store (projects may later delete or replace theirs)."""
        from factory import uid
        source = self.path(Path(source))
        if not source.is_file(): raise HTTPException(409, 'Die Datei dieser Figur fehlt im Projekt.')
        aid = uid(); suffix = '.png' if kind == 'image' else '.wav'
        dest = self.path(self.g['ROOT'] / '00_Eingang/Studio_Referenzen' / (aid + suffix))
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + '.partial')
        shutil.copyfile(source, partial); partial.replace(dest)
        self.sql('INSERT INTO factory_assets(id,kind,path,sha256,name) VALUES(?,?,?,?,?)', (aid, kind, str(dest), file_sha(dest), name[:120]))
        return aid

    def check_figure(self, body):
        if body.image: self.asset(body.image, 'image')
        if body.voice: self.asset(body.voice, 'voice')
        if not body.image and not body.voice: raise HTTPException(400, 'Eine Figur braucht mindestens ein Bild oder eine Stimme.')

    # ---------- project -> library ----------
    def figure_from_project(self, body):
        d = self.get(body.project)
        person = next((p for p in d.get('plan', {}).get('cast', []) if p['name'] == body.name), None)
        if person is None: raise HTTPException(404, 'Figur gehört nicht zu diesem Projekt.')
        provided = next((p for p in d['idea'].get('participants', []) if p['name'] == body.name), {}) or {}
        image = mode = voice = None; voice_text = ''; recipe = None
        ref = (d.get('cast_refs') or {}).get(body.name)
        upload = self.asset(provided['image'], 'image')['path'] if provided.get('image') else None
        if ref and not (upload and Path(ref) == Path(upload)):
            # The approved design sheet (studio design or neutral redraw) is the identity; used as it is.
            image = self.register_file('image', ref, f'{body.label} (Bild)'); mode = 'exact'
        elif provided.get('image'):
            # Cay's own picture keeps its mode; projects before 0.18 had no choice, so their
            # uploads enter the library as 'neutral' (a laughing photo must not freeze the face).
            image = provided['image']; mode = provided.get('image_mode') or 'neutral'
        profile = (d.get('voice_profiles') or {}).get(body.name)
        if profile and profile.get('file'):
            voice = self.register_file('voice', profile['file'], f'{body.label} (Stimme)')
            voice_text = profile.get('voice_text') or provided.get('voice_text', '')
            meta = Path(profile['file']).with_suffix('.json')
            if profile.get('source') == 'designed':
                try:
                    info = json.loads(self.path(meta).read_text())
                    recipe = {'instruction': str(info['description'])[:2000], 'seed': int(info['seed'])}
                except (OSError, ValueError, KeyError, TypeError): recipe = None
            elif provided.get('voice_design'): recipe = provided['voice_design']
        elif provided.get('voice'):
            voice = provided['voice']; voice_text = provided.get('voice_text', ''); recipe = provided.get('voice_design')
        if not image and not voice: raise HTTPException(409, 'Diese Figur hat noch kein Bild und keine Stimme. Erst nach der Figurengestaltung speichern.')
        traits = ' '.join(x for x in (person.get('appearance', ''), person.get('personality', '')) if x).strip()
        from factory import uid
        doc = {'id': uid(), 'name': body.name, 'label': body.label, 'look': d['idea'].get('look', 'auto'),
               'traits': (provided.get('traits') or traits)[:1500], 'image': image, 'image_mode': mode or 'exact',
               'voice': voice, 'voice_text': voice_text[:2500], 'voice_design': recipe,
               'voice_preset': person.get('voice_preset', ''), 'original': person.get('original', ''),
               # English look description from the planner: replaces the planner's text when this
               # figure is cast into another film (Cay's own German notes never enter image prompts).
               'appearance': person.get('appearance', '')[:1000],
               'source': {'project': d['id'], 'title': d.get('title', '')}}
        return self.library_save(doc)

    # ---------- library -> running project ----------
    def cast_window(self, d, part, owner=False):
        """When a figure of this project may get a new image or voice.

        'now': applied at once. 'later': the project is computing (or mixing its sound); the
        choice is kept and applied at the next safe point, before any review stop moves on.
        Any other value is the reason why not (shown as it is). owner: the caller is the worker
        that computes this project, so it may apply at once."""
        state = d['state']
        if state == 'blocked':
            resume = d.get('resume_state')
            if resume in ('rendering', 'finishing'): return VOICE_LATE
            if part == 'image': return 'now' if resume == 'pictures' else IMAGE_LATE if resume in ('voicing', 'audio_mixing') else BLOCKED_FIRST
            return 'now' if resume in ('pictures', 'voicing', 'audio_mixing') else BLOCKED_FIRST
        if state == 'planning': return 'Die Figuren entstehen gerade. Sobald sie zu sehen sind, kannst du sie tauschen.'
        if part == 'image':
            if state not in IMAGE_STATES: return IMAGE_LATE if state in VOICE_STATES else VOICE_LATE
        elif state not in VOICE_STATES: return VOICE_LATE
        # 'later' only while the worker really computes this state (it owns its copy of the document);
        # in a review state the worker is at most in its cleanup, which never saves the document.
        if (self.busy == d['id'] and not owner and state in WORKER_STATES) or (part == 'voice' and state == 'audio_mixing'): return 'later'
        return 'now'

    def cast_windows(self, d):
        return {part: self.cast_window(d, part) for part in ('image', 'voice')}

    def assign_profile(self, d, name, fig, use_image, use_voice):
        """Give one figure the image and/or voice of a library figure (in place, no save).
        Returns (scenes drawn again, lines spoken again)."""
        person = next(p for p in d['plan']['cast'] if p['name'] == name)
        participants = d['idea'].setdefault('participants', [])
        entry = next((p for p in participants if p['name'] == name), None)
        if entry is None:
            entry = {'name': name, 'traits': '', 'image': None, 'voice': None, 'voice_text': ''}; participants.append(entry)
        entry['library_id'] = fig['id']; scenes = lines = 0
        if use_image:
            import cast_design
            entry.update(image=fig['image'], image_mode=fig.get('image_mode', 'exact'), library_image=fig['id'], image_look=fig.get('look', 'auto'))
            if fig.get('appearance'): person['appearance'] = fig['appearance'][:1000]
            scenes = cast_design.invalidate(d, name)
            if d['state'] != 'blocked': d['state'] = 'pictures'
        if use_voice:
            from factory_audio import turns
            entry.update(voice=fig['voice'], voice_text=fig.get('voice_text', ''), voice_design=fig.get('voice_design'), library_voice=fig['id'])
            self.voice_changed(d)
            lines = sum(1 for ep in d.get('episodes', []) for sc in ep['scenes'] for l in turns(sc) if l.get('speaker') == name)
        return scenes, lines

    def pending_cast(self, rid):
        rows = self.rows('SELECT name,part,library_id,created FROM factory_cast_pending WHERE run_id=? ORDER BY created', (rid,))
        out = []
        for r in rows:
            try: label = self.library_figure(r['library_id'], deleted=True)['label']
            except HTTPException: label = ''
            out.append({'name': r['name'], 'part': r['part'], 'library_id': r['library_id'], 'label': label})
        return out

    def apply_pending(self, d):
        """Apply kept library choices at a safe point (called by the worker, which owns d).
        Returns True if d changed (and was saved)."""
        rows = self.rows('SELECT name,part,library_id FROM factory_cast_pending WHERE run_id=?', (d['id'],))
        if not rows: return False
        changed = False; notes = []
        for r in rows:
            window = self.cast_window(d, r['part'], owner=True)
            if window == 'later': continue
            self.sql('DELETE FROM factory_cast_pending WHERE run_id=? AND name=? AND part=?', (d['id'], r['name'], r['part']))
            try: fig = self.library_figure(r['library_id'])
            except HTTPException: fig = None
            person = next((p for p in d.get('plan', {}).get('cast', []) if p['name'] == r['name']), None)
            what = 'Bild' if r['part'] == 'image' else 'Stimme'
            if window != 'now' or not fig or not fig.get(r['part']) or person is None:
                notes.append(f'{what} für {r["name"]} nicht übernommen: ' + (window if window != 'now' else 'Bibliotheksfigur fehlt.'))
                continue
            self.assign_profile(d, r['name'], fig, r['part'] == 'image', r['part'] == 'voice'); changed = True
            notes.append(f'{what} von „{fig["label"]}“ für {r["name"]} übernommen')
        if notes: d['phase'] = ' · '.join(notes)[:600]
        if changed or notes: self.save(d)
        return changed

    def sweep_pending(self):
        """Worker: projects that are not computing get their kept choices now."""
        for row in self.rows('SELECT DISTINCT run_id FROM factory_cast_pending'):
            if self.busy == row['run_id']: continue
            try: d = self.get(row['run_id'])
            except HTTPException:
                self.sql('DELETE FROM factory_cast_pending WHERE run_id=?', (row['run_id'],)); continue
            self.apply_pending(d)

    def apply_profile(self, rid, body):
        """Library figure -> figure of a running project: now, or kept until the next safe point.
        Image: until the scene images are chosen; that figure's design and its scenes are drawn
        again. Voice: until the animation starts; its lines are spoken again."""
        d = self.get(rid)
        if not any(p['name'] == body.name for p in d.get('plan', {}).get('cast', [])):
            raise HTTPException(404, 'Figur gehört nicht zu diesem Projekt.')
        fig = self.library_figure(body.library_id)
        parts = [part for part, wanted in (('image', body.image), ('voice', body.voice)) if wanted and fig.get(part)]
        if not parts: raise HTTPException(400, 'Diese Bibliotheksfigur hat dafür kein Bild und keine Stimme.')
        windows = {part: self.cast_window(d, part) for part in parts}
        refused = [w for w in windows.values() if w not in ('now', 'later')]
        if refused: raise HTTPException(409, refused[0])
        for part in parts: self.asset(fig[part], part)
        now = [p for p in parts if windows[p] == 'now']; later = [p for p in parts if windows[p] == 'later']
        for part in parts:
            self.sql('DELETE FROM factory_cast_pending WHERE run_id=? AND name=? AND part=?', (rid, body.name, part))
        for part in later:
            self.sql('INSERT INTO factory_cast_pending(run_id,name,part,library_id,created) VALUES(?,?,?,?,?)',
                     (rid, body.name, part, fig['id'], self.g['now']()))
        if now:
            scenes, lines = self.assign_profile(d, body.name, fig, 'image' in now, 'voice' in now)
            what = ' und '.join(x for x, on in (('Bild', 'image' in now), ('Stimme', 'voice' in now)) if on)
            d['phase'] = (f'{what} von „{fig["label"]}“ für {body.name}' + (f' · {scenes} Szenen werden neu gezeichnet' if 'image' in now else '')
                          + (f' · {lines} Sätze werden neu eingesprochen' if 'voice' in now else ''))
            self.save(d)
        return self.view(rid)

    def cancel_pending(self, rid, name):
        self.get(rid)
        self.sql('DELETE FROM factory_cast_pending WHERE run_id=? AND name=?', (rid, name))
        return self.view(rid)

    def view(self, rid):
        """A project as the app shows it: the document plus what may change right now."""
        d = self.get(rid)
        if d.get('plan', {}).get('cast'):
            d['cast_windows'] = self.cast_windows(d); d['pending_cast'] = self.pending_cast(rid)
        return d

    def library_routes(self, app):
        @app.get('/api/library')
        def listing():
            return {'figures': self.library_figures(), 'looks': LOOKS}

        @app.post('/api/library')
        def create(body: LibraryFigure):
            from factory import uid
            self.check_figure(body)
            return self.library_save({'id': uid(), **body.model_dump(), 'source': {'manual': True}})

        @app.put('/api/library/{fid}')
        def update(fid: str, body: LibraryFigure):
            doc = self.library_figure(fid); self.check_figure(body)
            if body.voice != doc.get('voice'): doc['voice_design'] = None      # a new recording has no design recipe
            if body.image != doc.get('image'): doc.pop('appearance', None)    # the planner's description was of the old image
            doc.update({k: v for k, v in body.model_dump().items() if k != 'voice_design' or v})
            return self.library_save(doc)

        @app.delete('/api/library/{fid}')
        def remove(fid: str):
            doc = self.library_figure(fid); doc['deleted'] = True; self.library_save(doc)
            return {'ok': True, 'id': fid}

        @app.post('/api/library/{fid}/restore')
        def restore(fid: str):
            doc = self.library_figure(fid, deleted=True); doc.pop('deleted', None)
            return self.library_save(doc)

        @app.post('/api/library/from-project')
        def from_project(body: LibraryFromProject):
            return self.figure_from_project(body)

        # async: runs on the event loop like the worker, so no save can interleave with it.
        @app.post('/api/factory/{rid}/cast/profile')
        async def cast_profile(rid: str, body: CastProfile):
            return self.apply_profile(rid, body)

        @app.delete('/api/factory/{rid}/cast/pending/{name}')
        async def cast_pending_cancel(rid: str, name: str):
            return self.cancel_pending(rid, name)
