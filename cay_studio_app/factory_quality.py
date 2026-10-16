"""Voice casting, complete audio previews and multi-turn editing."""
import asyncio,contextlib,copy,hashlib,json,os,signal,sys,uuid
from pathlib import Path
import httpx
from fastapi import HTTPException
from figure_library import drop_library_voice
from fastapi.responses import FileResponse
from factory_models import Idea,Review,VoiceSettings,SceneDialogueEdit,MixSettings,ProductionSettings,EditionWish
from factory_audio import turns,layout,mix,edit_spec,scene_kinds
from factory_video import file_hash
from factory_editor import regenerate
from factory_speech import ready as speech_ready
from factory_timing import POLICY,audio_layout,off_screen,allowed_speakers
from studio_quality_policy import settings
from lipsync_shots import silent_by_accident,MISSING_MARK
def sample_signature(d,options):
    # Key of the production sample Cay approves: quality options, sound version and chosen images.
    return hashlib.sha256(json.dumps([options,d.get('audio_revision'),[[sc.get('selected') for sc in ep['scenes']] for ep in d['episodes']]],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
# "Lautstärke und Ton ändern" on a finished film can be undone while nothing was re-voiced or re-mixed:
# these keys are what reopen_output changes, sound_material what the finished sound was made from.
SOUND_UNDO=('exports','export_generation','export_history','voice_approval','render_segments','render_tracking_version','phase')
def sound_material(d):return hashlib.sha256(json.dumps([d['idea'],d.get('mix'),d.get('lines'),d.get('plan',{}).get('cast')],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
class Quality:
    def init_quality(self):self.setup_task=None;self.setup_process=None;self.setup_status={'state':'missing','message':'Stimmenstudio noch nicht eingerichtet.'}
    def voice_ready(self):return all(p.is_file() for p in [self.base/'envs/studio-voices/bereit.json',self.base/'envs/studio-voices/bin/python',self.base/'models/studio-voices/VoiceDesign/config.json'])
    async def setup_voices(self,upgrade=False):
        self.setup_status={'state':'running','message':'Stimmenmodell wird einmalig eingerichtet. Internet wird benötigt.'};log=self.g['RUNTIME']/'logs/stimmen_einrichtung.log';log.parent.mkdir(parents=True,exist_ok=True)
        try:
            with log.open('ab') as stream:
                self.setup_process=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('factory_voice.py')),'--base',str(self.base),'--setup',stdout=stream,stderr=stream,start_new_session=True);code=await self.setup_process.wait()
                if not code and upgrade:
                    self.setup_status={'state':'running','message':'Zusätzliches Qwen-Dialogmodell wird eingerichtet. Vorhandene Stimmen bleiben erhalten.'}
                    self.setup_process=await asyncio.create_subprocess_exec(str(self.base/'envs/studio-voices/bin/python'),str(Path(__file__).with_name('factory_speech.py')),'--base',str(self.base),'--setup',stdout=stream,stderr=stream,start_new_session=True);code=await self.setup_process.wait()
            if code or not self.voice_ready() or (upgrade and not speech_ready(self.base)):raise RuntimeError(log.read_text(errors='replace')[-1400:])
            self.setup_status={'state':'ready','message':'Stimmenstudio bereit. Angehaltenes Projekt jetzt fortsetzen.'}
        except asyncio.CancelledError:
            if self.setup_process and self.setup_process.returncode is None:
                os.killpg(self.setup_process.pid,signal.SIGTERM)
                try:await asyncio.wait_for(self.setup_process.wait(),15)
                except asyncio.TimeoutError:os.killpg(self.setup_process.pid,signal.SIGKILL);await self.setup_process.wait()
            raise
        except Exception as e:self.setup_status={'state':'failed','message':str(e)}
        finally:self.setup_process=None
    async def quality_voices(self,d):
        def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        lines=[];cast=[];provided={p['name']:p for p in d['idea']['participants']};options=settings(d['idea'])
        for person in d['plan']['cast']:
            row=dict(person);asset=provided.get(person['name'],{}).get('voice')
            if asset:
                ref=self.asset(asset,'voice');row.update(voice_file=ref['path'],voice_hash=ref['sha256'],voice_text=provided[person['name']].get('voice_text',''))
                # A library voice brings its design recipe: emotion takes in the same voice.
                if provided[person['name']].get('voice_design'):row['voice_design']=provided[person['name']]['voice_design']
            cast.append(row)
        takes=d.get('speech_takes',{})
        for ei,ep in enumerate(d['episodes']):
            for si,scene in enumerate(ep['scenes']):
                for ti,line in enumerate(turns(scene)):
                    key=f'E{ei+1:02}_S{si+1:02}_T{ti+1:02}_{digest(line)[:10]}';take=int(takes.get(key,0))
                    entry={'key':key,'episode':ei,'scene':si,'turn':ti,'speaker':line['speaker'],'text':line['text'],'text_de':line['text'],'emotion':line['emotion'],'pause_after':line.get('pause_after',.18),'seed':int(digest(d['id']+str(ei)+':'+str(si)+':'+str(ti))[:8],16)+104729*take}
                    # Only lines that failed the speech check get a take number;
                    # all other lines keep their cache signature and audio.
                    if take:entry['take']=take
                    lines.append(entry)
        if not lines and silent_by_accident(d['idea'],d['plan']['cast'],d['episodes']):
            # Older plans could reach this point without any line; never mix a silent film by accident.
            raise RuntimeError(MISSING_MARK+': Dieses Drehbuch enthält kein einziges gesprochenes Wort, obwohl Figuren sprechen sollen. '
                'Der Film wäre stumm. „Neue Fassung planen“ übernimmt Idee und Einstellungen; dieses Projekt bleibt erhalten.')
        if self.apply_pending(d):return            # kept library voices: plan the lines again with them
        audio_only=d.pop('audio_only',False) and bool(d.get('lines') or not lines)
        if self.paused(d['id']):return
        # Pinned once: a project voiced before 0.17 keeps its approved voices and cached
        # lines (0.16 references, sampling and signatures); new projects get 0.17 voices.
        # 18 = 17 plus the transcript of own and library recordings: a project voiced with 0.17
        # keeps cloning its recordings without transcript, so its approved lines stay cached.
        policy=d.setdefault('voice_policy',16 if d.get('voice_profiles') or d.get('lines') else 18)
        if lines and not audio_only:
            async with httpx.AsyncClient(trust_env=False,timeout=15) as c:await self.idle(c,True)
            speaking={l['speaker'] for l in lines};cast=[p for p in cast if p['name'] in speaking]
            if any(not p.get('voice_file') or p.get('voice_design') for p in cast):
                if not self.voice_ready():raise RuntimeError('Für verschiedene erfundene Stimmen einmalig „Stimmenstudio einrichten“ wählen. Danach dieses Projekt fortsetzen. Die alte Einheitsstimme wird nicht mehr verwendet.')
                job=self.folder(d)/'Stimmgestaltung.json';out=self.folder(d)/'03_Stimmen/Profile';self.atomic(job,json.dumps({'run_id':d['id'],'cast':cast,'lines':lines,'performances':options['speech_engine']=='qwen' or options['speech_engine']=='auto' and speech_ready(self.base),'look':d['plan'].get('visual',''),'voice_policy':policy,'output':str(out)}).encode());d['phase']='Eigene Stimmen für die Figuren gestalten';self.save(d)
                async with self.measured(d,'Stimmgestaltung'):await self.command([self.base/'envs/studio-voices/bin/python',Path(__file__).with_name('factory_voice.py'),'--base',self.base,'--job',job],7200)
                profiles=json.loads((out/'Profile.json').read_text());d['voice_profiles']=profiles
                for p in cast:
                    profile=profiles[p['name']];p.update(voice_file=profile['file'],voice_hash=profile['sha256'],voice_text=profile.get('voice_text',''),emotion_profiles=profile.get('emotion_profiles',{}))
            else:d['voice_profiles']={p['name']:{'file':p['voice_file'],'sha256':p['voice_hash'],'source':'upload'} for p in cast}
            engine=options['speech_engine']
            if engine=='auto':engine='qwen' if speech_ready(self.base) else 'chatterbox'
            if engine=='qwen' and not speech_ready(self.base):raise RuntimeError('Für Qwen-Dialoge unter „Stimmenqualität“ einmal das Dialogmodell einrichten. Danach dieses Projekt fortsetzen.')
            python=self.base/('envs/studio-voices/bin/python' if engine=='qwen' else 'envs/chatterbox/bin/python')
            if not python.is_file():raise RuntimeError('Die ausgewählte lokale Sprachumgebung fehlt.')
            d['audio_engine']=engine
            folder=self.folder(d)/'03_Stimmen/Dialoge';job=self.folder(d)/'Sprachauftrag.json';self.atomic(job,json.dumps({'cast':cast,'lines':lines,'voice_policy':policy,'output':str(folder)}).encode());d['phase']=f'{len(lines)} Dialogbeiträge werden eingesprochen';self.save(d)
            async with self.measured(d,'Sprache · '+engine):await self.command([python,Path(__file__).with_name('factory_speech.py' if engine=='qwen' else 'factory_tts.py'),'--base',self.base,'--job',job],14400)
            d['lines']=json.loads((folder/'Ergebnis.json').read_text())['lines']
            if len(d['lines'])!=len(lines):raise RuntimeError('Sprachvorschau unvollständig.')
            if self.apply_pending(d):return        # a voice chosen meanwhile: speak its lines again, then mix
        elif not lines:d['lines']=[];d['voice_profiles']={}
        if self.paused(d['id']):return
        # Pinned once: a 0.16 sound version keeps the 0.16 layout (same shot lengths, cached windows),
        # a 0.17 one keeps 17. Only a project without any sound version gets the 0.18 cut (layout 18:
        # reaction and establishing shots, longer silent action); factory_audio.layout knows 16/17 only.
        version=d.setdefault('timing_layout',18 if not d.get('timing') else 16 if not any(t.get('layout') or 'silent_shots' in t for t in d['timing']) else 17)
        # Only the volume or the music changed (same lines): an approved production sample still holds
        # if the timing is the same, so a remix of a finished film does not stop at the sample again.
        carry=audio_only and d.get('sample_approval') and d['sample_approval']==sample_signature(d,options);before=d.get('timing')
        d['timing']=(audio_layout(d['episodes'],d['lines'],d['idea']['duration'],options['fps'],version=version) if version>=18 else layout(d['episodes'],d['lines'],d['idea']['duration'],options['fps'],version));d['timing_policy']=POLICY;d['timing_fps']=options['fps'];d['audio_revision']=d.get('audio_revision',0)+1;d['previews']=[];music=self.asset(d['idea']['music'],'music') if d['idea'].get('music') else None
        if carry and d['timing']==before:d['sample_approval']=sample_signature(d,options)
        for ei,ep in enumerate(d['episodes']):
            if self.paused(d['id']):return
            d['phase']=f'Folge {ei+1}: Dialog, Musik und Geräusche mischen';self.save(d);scenes=[{'seconds':s['render_seconds'],'lines':[l for l in d['lines'] if l['episode']==ei and l['scene']==si],'ambience':s.get('ambience','room'),'sound_cues':s.get('sound_cues',[]),**kind} for si,(s,kind) in enumerate(zip(ep['scenes'],scene_kinds(d,ep['scenes'])))];folder=self.folder(d)/'03_Stimmen'/f'Mischung_{d["audio_revision"]:03}'/f'Folge_{ei+1:02}'
            self.queue_post(d,'mix',ei,{'folder':str(folder),'scenes':scenes,'mood':d['plan']['mood'],
                'music':{'file':music['path'],'sha256':music['sha256']} if music else None,
                'mix':d.get('mix'),'seconds':d['timing'][ei]['seconds'],**edit_spec(d)})
        d['state']='audio_mixing';d['phase']='CPU: Dialog, Musik und Geräusche mischen · GPU wieder frei';self.save(d)
    def image_open(self,d):
        """Own image or redesign: the same window as a library image, but never kept for later."""
        window=self.cast_window(d,'image')
        if window=='later':raise HTTPException(409,'Das Studio zeichnet gerade. Pausiere kurz, dann kannst du neu gestalten oder ein eigenes Bild wählen.')
        if window!='now':raise HTTPException(409,window)
    def voice_open(self,d):
        """Voices change until the animation starts; refuse with the reason otherwise."""
        window=self.cast_window(d,'voice')
        if window=='later':
            raise HTTPException(409,'Der Ton wird gerade gemischt. Danach kannst du die Stimme ändern.' if d['state']=='audio_mixing'
                                else 'Das Studio rechnet gerade an diesem Projekt. In ein paar Sekunden noch einmal versuchen.')
        if window!='now':raise HTTPException(409,window)
    def voice_changed(self,d):
        """A figure got another voice: its lines are spoken again (cache by voice), the approval goes."""
        d.pop('voice_approval',None);d.pop('audio_only',None);d['previews']=[]
        if d['state']=='voice_review':d['state']='voicing'
        # A failed mix would otherwise resume with the old lines.
        elif d['state']=='blocked' and d.get('resume_state')=='audio_mixing':d['resume_state']='voicing'
    def measured(self,d,stage):
        """Voice generation runs outside ComfyUI; record its time like every other stage."""
        resources=self.g.get('resources')
        return resources.measure(d['id'],stage,'GPU') if resources else contextlib.nullcontext()
    def speech_retake(self,d):
        """After a failed speech check, speak only the inaudible lines again."""
        from speech_check import MARK
        keys=set()
        if d.get('resume_state')=='voicing':
            failed=self.path(self.folder(d)/'03_Stimmen/Dialoge/Fehlgeschlagen.json')
            try:keys.add(json.loads(failed.read_text())['key']);failed.unlink()
            except (OSError,ValueError,KeyError,TypeError):return False
        elif d.get('resume_state')!='audio_mixing':return False
        for row in self.post_rows(d,'mix'):
            if row['status']!='failed' or MARK not in (row['error'] or ''):continue
            try:
                report=json.loads(self.path(Path(json.loads(row['spec'])['folder'])/'Sprachpruefung.json').read_text(encoding='utf-8'))
                keys|={x['key'] for x in report['lines'] if x['blocking'] and x.get('key')}
            except (OSError,ValueError,KeyError,TypeError):continue
        if not keys:return False
        takes=d.setdefault('speech_takes',{})
        for key in keys:takes[key]=int(takes.get(key,0))+1
        for key in ('resume_state','error','uncertain','voice_approval','audio_only'):d.pop(key,None)
        d.update(state='voicing',previews=[],phase=f'{len(keys)} stumme oder unhörbare Dialogbeiträge werden neu eingesprochen.')
        return True
    def quality_routes(self,app):
        @app.get('/api/factory/voice-studio/status')
        async def status():
            r=dict(self.setup_status)
            if self.voice_ready() and r['state'] not in ('running','failed'):r={'state':'ready','message':'Stimmenstudio bereit.'}
            r['dialogue_ready']=speech_ready(self.base)
            log=self.g['RUNTIME']/'logs/stimmen_einrichtung.log'
            if r['state'] in ('running','failed') and log.is_file():
                with log.open('rb') as f:f.seek(max(0,log.stat().st_size-1400));r['log']=f.read().decode(errors='replace')
            return r
        @app.post('/api/factory/voice-studio/setup')
        async def setup():
            if not self.setup_task or self.setup_task.done():self.setup_task=asyncio.create_task(self.setup_voices())
            return {'ok':True}
        @app.post('/api/factory/voice-studio/upgrade')
        async def upgrade():
            if speech_ready(self.base) and self.voice_ready():
                self.setup_status={'state':'ready','message':'Qwen-Dialogstudio bereit.'};return {'state':'ready'}
            if not self.setup_task or self.setup_task.done():self.setup_task=asyncio.create_task(self.setup_voices(upgrade=True))
            return {'state':'running'}
        @app.post('/api/factory/{rid}/reopen-output')
        async def reopen_output(rid:str,body:Review):
            d=self.get(rid);self.revision(d,body,{'done'})
            d['sound_edit_undo']={'keep':{k:copy.deepcopy(d[k]) for k in SOUND_UNDO if k in d},'audio_revision':d.get('audio_revision'),'material':sound_material(d)}
            d.setdefault('export_history',[]).append({'generation':d.get('export_generation',0),'exports':d.get('exports',[])})
            d['export_generation']=d.get('export_generation',0)+1;d['exports']=[];d.pop('voice_approval',None)
            d['render_segments']={};d['render_tracking_version']=10;d['sound_edit']=True
            d['state']='voice_review';d['phase']='Ton und Export bearbeiten. Fertige Animationen werden bei passenden Vorgaben weiterverwendet.'
            self.save(d);return self.get(rid)
        @app.post('/api/factory/{rid}/cancel-sound-edit')
        async def cancel_sound_edit(rid:str,body:Review):
            """Back to the finished film, exactly as it was (same export generation: no second 'fertig' message)."""
            d=self.get(rid);self.revision(d,body,{'voice_review'});undo=d.get('sound_edit_undo')
            if not undo:raise HTTPException(409,'Hier gibt es keinen fertigen Film zum Zurückholen.')
            if undo['audio_revision']!=d.get('audio_revision') or undo['material']!=sound_material(d):
                raise HTTPException(409,'Der Ton wurde schon geändert. Gib ihn frei, dann entsteht der neue Film.')
            for k in SOUND_UNDO:
                if k in undo['keep']:d[k]=undo['keep'][k]
                else:d.pop(k,None)
            d.pop('sound_edit',None);d.pop('sound_edit_undo',None);d['state']='done'
            self.save(d);return self.get(rid)
        @app.post('/api/factory/{rid}/reopen-voices')
        async def reopen_voices(rid:str,body:Review):
            d=self.get(rid);self.revision(d,body,{'blocked'})
            if d.get('resume_state') not in ('rendering','finishing') or not d.get('previews'):
                raise HTTPException(409,'Noch keine fertige Tonvorschau zum Bearbeiten vorhanden.')
            if d.get('uncertain'):
                raise HTTPException(409,'Der ComfyUI-Auftragsstatus ist unklar. Zuerst Produktion fortsetzen, um den gespeicherten Auftrag zu prüfen.')
            if self.busy==rid or self.rows("SELECT id FROM factory_post WHERE run_id=? AND status='running'",(rid,)):
                raise HTTPException(409,'Der laufende Arbeitsschritt wird noch abgeschlossen. Kurz warten.')
            d.setdefault('export_history',[]).append({'generation':d.get('export_generation',0),'exports':d.get('exports',[])})
            d['export_generation']=d.get('export_generation',0)+1;d['exports']=[]
            for key in ('voice_approval','sample_approval','error','resume_state','uncertain','sound_edit_undo'):d.pop(key,None)
            d['render_segments']={};d['render_tracking_version']=10;d['sound_edit']=True
            d.update(state='voice_review',phase='Dialoge und Ton prüfen. Danach die Produktion erneut freigeben.')
            self.save(d);return self.get(rid)
        @app.post('/api/factory/{rid}/production-settings')
        async def production(rid:str,body:ProductionSettings):
            d=self.get(rid);self.revision(d,body,{'image_review','voice_review'})
            before=settings(d['idea']);values=body.model_dump(exclude={'revision'});d['idea'].update(values)
            if d['state']=='voice_review' and (values['fps']!=before['fps'] or values['speech_engine']!=before['speech_engine']):
                d['audio_only']=values['speech_engine']==before['speech_engine'];d['state']='voicing';d['previews']=[];d.pop('voice_approval',None)
            d['phase']='Produktionsqualität gespeichert. Vorschauen vor der Produktion prüfen.';self.save(d);return self.get(rid)
        @app.get('/api/factory/{rid}/mix/{ei}')
        def preview(rid:str,ei:int):
            p=next((p for p in self.get(rid).get('previews',[]) if p['episode']==ei),None)
            if not p:raise HTTPException(404,'Gesamtvorschau noch nicht bereit.')
            return FileResponse(self.path(p['file']),media_type='audio/wav')
        @app.get('/api/factory/{rid}/voice-profile/{name}')
        def profile(rid:str,name:str):
            p=self.get(rid).get('voice_profiles',{}).get(name)
            if not p:raise HTTPException(404,'Stimmprofil noch nicht erzeugt.')
            return FileResponse(self.path(p['file']),media_type='audio/wav')
        @app.post('/api/factory/{rid}/voice-settings')
        async def voices(rid:str,body:VoiceSettings):
            d=self.get(rid);self.voice_open(d)
            p=next((p for p in d.get('plan',{}).get('cast',[]) if p['name']==body.name),None)
            if not p:raise HTTPException(400,'Figur gehört nicht zum Projekt.')
            p.update(voice_preset=body.voice_preset,voice_description=body.voice_description)
            if body.new_variant:p['voice_variant']=p.get('voice_variant',0)+1
            for participant in d['idea']['participants']:
                # A designed voice from the studio: the library voice and its recipe no longer apply.
                if participant['name']==body.name:drop_library_voice(participant)
            self.voice_changed(d)
            self.save(d);return self.get(rid)
        @app.put('/api/factory/{rid}/dialogues')
        async def edit(rid:str,body:SceneDialogueEdit):
            d=self.get(rid)
            if d['state'] not in ('image_review','voice_review'):raise HTTPException(409,'Dialoge während der Vorschau bearbeiten.')
            try:s=d['episodes'][body.episode]['scenes'][body.scene]
            except IndexError:raise HTTPException(404,'Szene nicht gefunden.')
            # 0.18: in a reaction the figure in the frame listens and only the voice from off-screen speaks;
            # a wide establishing shot shows the place and stays silent.
            allowed=allowed_speakers(s)
            if any(l.speaker not in allowed for l in body.dialogues):
                if off_screen(s):raise HTTPException(400,f'In dieser Reaktion hört {", ".join(s["cast"])} nur zu. Sprechen kann hier nur {s.get("voice_of") or "die Stimme aus dem Off"}.')
                if s.get('kind')=='establish':raise HTTPException(400,'Diese Totale zeigt nur den neuen Ort. Hier spricht niemand.')
                raise HTTPException(400,'Sprecher muss zur Besetzung der Szene gehören.')
            if body.action!=s['action']:
                if d['state']=='voice_review':raise HTTPException(409,'Bildhandlung in der Bildauswahl ändern.')
                regenerate(s,[0,1]);s['action']=body.action;s['animation_prompt']='';s['motion']=[body.action];s['still']='';d['state']='pictures'
            s['dialogues']=[x.model_dump() for x in body.dialogues];s['dialogue']='';s['speaker']='';d.pop('voice_approval',None);d['previews']=[]
            if d['state']=='voice_review':d['state']='voicing'
            self.save(d);return self.get(rid)
        @app.post('/api/factory/{rid}/mix-settings')
        async def mix_settings(rid:str,body:MixSettings):
            d=self.get(rid)
            if d['state']!='voice_review':raise HTTPException(409,'Tonmischung in der Hörvorschau einstellen.')
            if body.music_mode=='uploaded' and not d['idea'].get('music'):raise HTTPException(400,'Keine eigene Musik hochgeladen.')
            d['mix']={**d.get('mix',{}),**body.model_dump()};d['audio_only']=True;d['state']='voicing';d['previews']=[];d.pop('voice_approval',None);self.save(d);return self.get(rid)
        @app.post('/api/factory/{rid}/rebuild-audio')
        async def rebuild(rid:str):
            d=self.get(rid)
            if d['state']!='voice_review':raise HTTPException(409,'Ton in der Hörvorschau neu erzeugen.')
            d['state']='voicing';d['previews']=[];d.pop('voice_approval',None);self.save(d);return self.get(rid)
        @app.post('/api/factory/{rid}/new-edition')
        async def edition(rid:str,body:EditionWish|None=None):
            old=self.get(rid);idea=copy.deepcopy(old['idea']);idea['request_key']=uuid.uuid4().hex
            # One suffix, however often a film is planned anew; Cay's own wish steers it, else the general note.
            title,suffix=old['title'],' · neue Fassung'
            while title.endswith(suffix):title=title[:-len(suffix)]
            idea['title']=(title+suffix)[:100];note=body.note if body else ''
            idea['idea']=idea['idea']+'\nÜberarbeitung: '+(note or 'Nur EIN Ereignis mit Ziel, Hindernis und Pointe. Keine gesamte Filmhandlung in einer Minute. Mehrere kurze Dialogwechsel und passende Altersstimmen. Alte Vorgaben mit einem Satz je Szene sind aufgehoben. Bei Lebensmittel-Parodien keine Verwandlung in Menschen.')
            if len(idea['idea'])>100000:idea['idea']=old['idea']['idea']
            # A new edition is a new film: an original from before 0.18 (no field) gets the title card too.
            idea.setdefault('cover','start')
            create=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/factory' and 'POST' in (getattr(r,'methods',None) or set()));return create(Idea.model_validate(idea))
