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


def file_sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


class Library:
    def init_library(self):
        self.sql('CREATE TABLE IF NOT EXISTS figure_library(id TEXT PRIMARY KEY,document TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL)')

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
        self.sql('INSERT INTO figure_library(id,document,created,updated) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document,updated=excluded.updated',
                 (doc['id'], json.dumps(doc, ensure_ascii=False, sort_keys=True), doc['created'], now))
        return doc

    def library_uses(self):
        """How many projects use each library figure (shown on the cards; deleting stays safe)."""
        counts = {}
        for r in self.rows('SELECT document FROM factory_runs'):
            try: d = json.loads(r['document'])
            except ValueError: continue
            for fid in {p.get('library_id') for p in d.get('idea', {}).get('participants', []) if p.get('library_id')}:
                counts[fid] = counts.get(fid, 0) + 1
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
        if ref:
            # The approved design sheet is the identity; it is used exactly as it is.
            image = self.register_file('image', ref, f'{body.label} (Bild)'); mode = 'exact'
        elif provided.get('image'):
            image = provided['image']; mode = provided.get('image_mode', 'neutral')
        profile = (d.get('voice_profiles') or {}).get(body.name)
        if profile and profile.get('file'):
            voice = self.register_file('voice', profile['file'], f'{body.label} (Stimme)'); voice_text = profile.get('voice_text', '')
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
               'source': {'project': d['id'], 'title': d.get('title', '')}}
        return self.library_save(doc)

    # ---------- library -> running project ----------
    def apply_profile(self, rid, body):
        """Give a figure of a running project the image and/or voice of a library figure.

        Image: allowed while figures or scene images are being reviewed; that figure's design
        and every scene showing it are redone. Voice: allowed until the animation starts; its
        lines are spoken again. Nothing that is already animated is touched."""
        d = self.get(rid)
        if self.busy == rid: raise HTTPException(409, 'Der laufende Schritt wird gerade abgeschlossen. Kurz warten.')
        cast = d.get('plan', {}).get('cast', [])
        person = next((p for p in cast if p['name'] == body.name), None)
        if person is None: raise HTTPException(404, 'Figur gehört nicht zu diesem Projekt.')
        fig = self.library_figure(body.library_id)
        use_image = body.image and bool(fig.get('image')); use_voice = body.voice and bool(fig.get('voice'))
        if not use_image and not use_voice: raise HTTPException(400, 'Diese Bibliotheksfigur hat dafür kein Bild oder keine Stimme.')
        state = d['state']; resume = d.get('resume_state')
        if use_image and state not in ('cast_review', 'image_review'):
            raise HTTPException(409, 'Bilder lassen sich bei der Figuren- oder Bildprüfung tauschen.')
        if use_voice and not (state in ('cast_review', 'image_review', 'voice_review', 'pictures', 'planning')
                              or (state == 'blocked' and resume not in ('rendering', 'finishing'))):
            raise HTTPException(409, 'Stimmen lassen sich nur vor der Animation tauschen.')
        if use_image: self.asset(fig['image'], 'image')
        if use_voice: self.asset(fig['voice'], 'voice')
        participants = d['idea'].setdefault('participants', [])
        entry = next((p for p in participants if p['name'] == body.name), None)
        if entry is None:
            entry = {'name': body.name, 'traits': '', 'image': None, 'voice': None, 'voice_text': ''}; participants.append(entry)
        entry['library_id'] = fig['id']
        scenes = 0
        if use_image:
            import cast_design
            entry['image'] = fig['image']; entry['image_mode'] = fig.get('image_mode', 'exact')
            if fig.get('traits'): person['appearance'] = fig['traits'][:800]
            scenes = cast_design.invalidate(d, body.name)
            d['state'] = 'pictures'
        if use_voice:
            entry['voice'] = fig['voice']; entry['voice_text'] = fig.get('voice_text', '')
            entry['voice_design'] = fig.get('voice_design')
            d.pop('voice_approval', None); d['previews'] = []
            if d['state'] == 'voice_review': d['state'] = 'voicing'
        lines = sum(1 for ep in d.get('episodes', []) for sc in ep['scenes'] for l in (sc.get('dialogues') or []) if l.get('speaker') == body.name)
        what = ' und '.join(x for x, on in (('Bild', use_image), ('Stimme', use_voice)) if on)
        d['phase'] = f'{what} von „{fig["label"]}“ für {body.name}' + (f' · {scenes} Szenen werden neu gezeichnet' if use_image else '') + (f' · {lines} Sätze neu eingesprochen' if use_voice else '')
        self.save(d)
        return self.get(rid)

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

        @app.post('/api/factory/{rid}/cast/profile')
        def cast_profile(rid: str, body: CastProfile):
            return self.apply_profile(rid, body)
