"""Scoped, persistent corrections and recoverable project lifecycle controls."""
import copy
from typing import Literal
from pydantic import Field
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from factory_models import Strict, VoiceSettings, SoundCue


def image_rounds(scene):
    return scene.get('image_rounds', [scene.get('round', 0)] * 2)


def active_variants(scene):
    rounds = image_rounds(scene)
    return [v for slot in range(2) for v in scene.get('variants', [])
            if v.get('key', '').endswith(f':{rounds[slot]}:{slot}')][-2:]


def regenerate(scene, slots):
    rounds = list(image_rounds(scene))
    replaced = {v['id'] for v in active_variants(scene)
                if int(v['key'].split(':')[-1]) in slots}
    for slot in slots: rounds[slot] += 1
    scene['image_rounds'] = rounds
    if scene.get('selected') in replaced: scene['selected'] = None


class Correction(Strict):
    request_key: str = Field(pattern=r'^[a-f0-9]{32}$')
    revision: str
    kind: Literal['image', 'voice', 'music', 'effects', 'dialogue']
    message: str = Field(default='', max_length=1800)
    episode: int = Field(default=0, ge=0, le=11)
    scene: int = Field(default=0, ge=0, le=44)
    variant: Literal['0', '1', 'both'] = 'both'
    name: str = Field(default='', max_length=60)


class Appearance(Strict):
    name: str = Field(max_length=60)
    appearance: str = Field(min_length=10, max_length=1200)


class PictureCorrection(Strict):
    reply: str = Field(min_length=3, max_length=900)
    image_note: str = Field(min_length=5, max_length=1800)
    characters: list[Appearance] = Field(default_factory=list, max_length=4)


class VoiceCorrection(VoiceSettings):
    reply: str = Field(min_length=3, max_length=900)


class MusicCorrection(Strict):
    reply: str = Field(min_length=3, max_length=900)
    mood: Literal['suspense', 'playful', 'gentle', 'energetic']
    music_mode: Literal['auto', 'off', 'uploaded']
    music_level: float = Field(ge=0, le=2)
    tempo: float = Field(ge=.65, le=1.5)


class EffectsCorrection(Strict):
    reply: str = Field(min_length=3, max_length=900)
    ambience: Literal['room', 'wind', 'forest', 'rain', 'train', 'none']
    sound_cues: list[SoundCue] = Field(max_length=8)


class Editor:
    def init_editor(self):
        self.sql('CREATE TABLE IF NOT EXISTS studio_trash(id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)')

    def controlled(self, d):
        control = self.rows('SELECT paused FROM factory_control WHERE id=?', (d['id'],))
        d['deleted'] = bool(self.rows('SELECT id FROM studio_trash WHERE id=?', (d['id'],)))
        d['paused'] = d['deleted'] or bool(control and control[0]['paused'])
        return d

    def editor_routes(self, app, kind='factory'):
        prefix = '/api/' + kind
        table = 'factory_runs' if kind == 'factory' else 'remix_runs'
        if kind == 'factory':
            @app.middleware('http')
            async def protect_trash(request, call_next):
                parts = request.url.path.strip('/').split('/')
                if (request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and len(parts) >= 4
                        and parts[:2] in (['api', 'factory'], ['api', 'remix'])
                        and parts[3] != 'restore'
                        and self.rows('SELECT id FROM studio_trash WHERE id=?', (parts[2],))):
                    return JSONResponse({'detail': 'Projekt liegt im Papierkorb. Zuerst wiederherstellen.'}, status_code=409)
                return await call_next(request)

        @app.get(prefix + '/trash')
        def trash():
            return {'runs': [self.get(row['id']) for row in self.rows(
                f'SELECT r.id FROM {table} r JOIN studio_trash t ON r.id=t.id ORDER BY t.deleted_at DESC')]}

        @app.post(prefix + '/{rid}/delete')
        def delete(rid: str):
            self.get(rid)
            with self.g['conn']() as db:
                db.execute('INSERT OR IGNORE INTO studio_trash VALUES(?,?)', (rid, self.g['now']()))
                db.execute('INSERT INTO factory_control VALUES(?,1) ON CONFLICT(id) DO UPDATE SET paused=1', (rid,))
            return self.get(rid)

        @app.post(prefix + '/{rid}/restore')
        def restore(rid: str):
            self.get(rid)
            # An in-flight renderer may finish its owned step. Never auto-resume.
            with self.g['conn']() as db:
                db.execute('INSERT INTO factory_control VALUES(?,1) ON CONFLICT(id) DO UPDATE SET paused=1', (rid,))
                db.execute('DELETE FROM studio_trash WHERE id=?', (rid,))
            return self.get(rid)

        if kind != 'factory': return

        @app.post(prefix + '/{rid}/correction')
        async def correction(rid: str, body: Correction):
            d = self.get(rid)
            previous = next((x for x in d.get('corrections', []) if x['request_key'] == body.request_key), None)
            if previous:
                if previous['request'] != body.model_dump(exclude={'revision'}):
                    raise HTTPException(409, 'Diese Anfrage wurde bereits mit anderen Angaben gespeichert.')
                return d
            self.revision(d, body, {'image_review', 'voice_review'})
            if self.busy == rid: raise HTTPException(409, 'Der laufende Schritt wird gerade abgeschlossen. Kurz warten.')
            if body.kind == 'image' and d['state'] != 'image_review':
                raise HTTPException(409, 'Bilder vor der Bildfreigabe korrigieren; sonst neue Fassung anlegen.')
            if body.kind in ('music', 'effects') and d['state'] != 'voice_review':
                raise HTTPException(409, 'Musik und Geräusche in der Tonvorschau korrigieren.')
            if body.kind in ('image', 'effects', 'dialogue'):
                try: d['episodes'][body.episode]['scenes'][body.scene]
                except IndexError: raise HTTPException(404, 'Szene fehlt.')
            if body.kind == 'voice' and not any(p['name'] == body.name for p in d['plan']['cast']):
                raise HTTPException(400, 'Figur gehört nicht zu diesem Projekt.')
            entry = {'request_key': body.request_key, 'request': body.model_dump(exclude={'revision'}),
                     'status': 'queued', 'return_state': d['state'], 'created': self.g['now']()}
            d.setdefault('corrections', []).append(entry)
            d.update(state='correcting', phase='Dein Änderungswunsch wartet auf die KI.')
            self.save(d)
            return self.get(rid)

    async def correct(self, original):
        # Validate the entire reply before changing the project; retries cannot
        # increment variants twice or leave half-applied character definitions.
        d = copy.deepcopy(original)
        entry = next(x for x in d['corrections'] if x['status'] == 'queued')
        req = entry['request']; kind = req['kind']
        if kind == 'dialogue':
            from dialogue_density import enrich, word_count
            from factory_timing import plan_seconds
            from studio_quality_policy import settings
            index=req['episode'];timing=d.get('timing',[])
            d['phase']=f'Folge {index+1}: Dialoge ergänzen, Bilder erhalten';self.save(d)
            episode=await enrich(self,d,d['episodes'][index],index,timing[index] if len(timing)>index else None,force=True,request=req['message'])
            if self.paused(d['id']):return
            changed=word_count(episode)>word_count(d['episodes'][index])
            d['episodes'][index]=episode
            if not changed:
                entry.update(status='done',reply='Keine zusätzlichen gültigen Dialoge übernommen. '+(' '.join(episode.get('warnings',[]))),finished=self.g['now']())
                d.update(state=entry['return_state'],phase='Dialogergänzung prüfen. Vorhandene Tonvorschau bleibt erhalten.')
                self.save(d);return
            plan_seconds(episode,d['idea']['duration'],settings(d['idea'])['fps'])
            entry.update(status='done',reply='Dialogergänzung abgeschlossen. Texte und neue Tonvorschau prüfen.',finished=self.g['now']())
            d.pop('voice_approval',None);d.pop('sample_approval',None)
            if entry['return_state']=='voice_review':
                d['state']='voicing';d['previews']=[]
            else:d['state']='image_review'
            d['phase']='Dialoge prüfen; vorhandene Szenenbilder bleiben erhalten.';self.save(d);return
        context = {'request': req, 'cast': d['plan']['cast'], 'style': d['plan']['style'],
                   'history': [x for x in d['corrections'][-12:] if x['request']['kind'] == kind and x['status'] == 'done']}
        scene = None
        if kind in ('image', 'effects'):
            scene = d['episodes'][req['episode']]['scenes'][req['scene']]
            context['scene'] = scene
        context['music'] = {'mood': d['plan']['mood'], 'settings': d.get('mix', {}), 'has_upload': bool(d['idea'].get('music'))}
        instruction = ('Du bist der Korrektur-Assistent eines Filmstudios. Antworte auf Deutsch. '
                       'Ändere ausschließlich den angeforderten Bereich; Namen, Geschichte und Dialoge erhalten. '
                       'reply beschreibt konkret die angeforderte neue Variante, ohne zu behaupten, du hättest sie bereits gesehen oder gehört. ')
        schema = {'image': PictureCorrection, 'voice': VoiceCorrection, 'music': MusicCorrection, 'effects': EffectsCorrection}[kind]
        instruction += {
            'image': 'image_note: englische Bildanweisung. characters nur für Figuren dieser Szene, deren Aussehen ausdrücklich bemängelt wurde. Vorhandene Details erhalten und Material/Form konkret beschreiben.',
            'voice': 'Nur die gewählte Figur ändern. voice_description beschreibt ihre Stimme. new_variant immer true. Altersgruppe passend zum Wunsch.',
            'music': 'Die lokale Musik ist eine einfache synthetische Instrumentalbegleitung, kein freies Musikmodell. Steuerbar: Stimmung, Tempo, Lautstärke, neue Melodievariante oder aus. Keine Sänger oder Instrumentenaufnahmen versprechen. uploaded nur bei vorhandener Datei und ausdrücklichem Wunsch.',
            'effects': 'Nur Geräusche der gewählten Szene ändern. Nur verfügbare kind-Werte verwenden; position ist der Szenenanteil 0 bis 1. Maximal acht passende Effekte. Nicht verfügbare Geräusche im reply ehrlich benennen.',
        }[kind]
        if kind == 'image' and not req['message']:
            answer = {'reply': 'Neue Bildvariante wird mit den bisherigen Vorgaben erzeugt.', 'image_note': scene.get('image_note', ''), 'characters': []}
        else:
            answer = await self.llm(schema, instruction, context)
            answer = schema.model_validate(answer).model_dump()
        if self.paused(d['id']): return
        if kind == 'image':
            changes = {p['name']: p['appearance'] for p in answer['characters']}
            if not set(changes).issubset(scene['cast']): raise RuntimeError('Die KI hat eine fremde Figur verändert. Bitte erneut versuchen.')
            from cast_design import invalidate
            for person in d['plan']['cast']:
                if person['name'] in changes:
                    person['appearance'] = changes[person['name']]
                    # Every scene with this figure, not only this one: no face drift.
                    invalidate(d, person['name'])
            scene['image_note'] = answer['image_note']; scene['note_policy'] = 18   # the wish leads the image prompt
            if not changes: regenerate(scene, [0, 1] if req['variant'] == 'both' else [int(req['variant'])])
            d['state'] = 'pictures'
        elif kind == 'voice':
            if answer['name'] != req['name']: raise RuntimeError('Die KI hat die falsche Stimme gewählt. Bitte erneut versuchen.')
            person = next(p for p in d['plan']['cast'] if p['name'] == req['name'])
            person.update(voice_preset=answer['voice_preset'], voice_description=answer['voice_description'], voice_variant=person.get('voice_variant', 0) + 1)
            from figure_library import drop_library_voice
            for p in d['idea']['participants']:
                if p['name'] == req['name']: drop_library_voice(p)
            d['state'] = 'voicing' if entry['return_state'] == 'voice_review' else 'image_review'
        elif kind == 'music':
            if answer['music_mode'] == 'uploaded' and not d['idea'].get('music'): raise RuntimeError('Keine eigene Musikdatei vorhanden.')
            d['plan']['mood'] = answer['mood']
            settings = d.setdefault('mix', {})
            settings.update(music_mode=answer['music_mode'], music_level=answer['music_level'], tempo=answer['tempo'], music_variant=settings.get('music_variant', 0) + 1)
            d['audio_only'] = True; d['state'] = 'voicing'
        else:
            scene.update(ambience=answer['ambience'], sound_cues=answer['sound_cues'])
            d['audio_only'] = True; d['state'] = 'voicing'
        if kind != 'image':
            d.pop('voice_approval', None); d['previews'] = []
        entry.update(status='done', reply=answer['reply'])
        d['phase'] = 'Änderung übernommen. Neue Vorschau wird vorbereitet.' if d['state'] != 'image_review' else 'Stimmwunsch gespeichert; hörbar im nächsten Schritt.'
        self.save(d)
