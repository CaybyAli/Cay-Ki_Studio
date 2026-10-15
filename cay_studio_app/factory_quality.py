"""Voice casting, complete audio previews and multi-turn editing."""
import asyncio,contextlib,copy,hashlib,json,os,signal,sys,uuid
from pathlib import Path
import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse
from factory_models import Idea,Review,VoiceSettings,SceneDialogueEdit,MixSettings,ProductionSettings
from factory_audio import turns,layout,mix
from factory_video import file_hash
from factory_editor import regenerate
from factory_speech import ready as speech_ready
from factory_timing import POLICY
from studio_quality_policy import settings
from lipsync_shots import silent_by_accident,MISSING_MARK
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
        audio_only=d.pop('audio_only',False) and bool(d.get('lines') or not lines)
        if self.paused(d['id']):return
        # Pinned once: a project voiced before 0.17 keeps its approved voices and cached
        # lines (0.16 references, sampling and signatures); new projects get 0.17 voices.
        policy=d.setdefault('voice_policy',16 if d.get('voice_profiles') or d.get('lines') else 17)
        if lines and not audio_only:
            async with httpx.AsyncClient(trust_env=False,timeout=15) as c:await self.idle(c,True)
            speaking={l['speaker'] for l in lines};cast=[p for p in cast if p['name'] in speaking]
            if any(not p.get('voice_file') for p in cast):
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
        elif not lines:d['lines']=[];d['voice_profiles']={}
        if self.paused(d['id']):return
        # Pinned once: a 0.16 sound version keeps the 0.16 layout (same shot lengths, cached windows).
        d.setdefault('timing_layout',16 if d.get('timing') and not any(t.get('layout') or 'silent_shots' in t for t in d['timing']) else 17)
        d['timing']=layout(d['episodes'],d['lines'],d['idea']['duration'],options['fps'],d['timing_layout']);d['timing_policy']=POLICY;d['timing_fps']=options['fps'];d['audio_revision']=d.get('audio_revision',0)+1;d['previews']=[];music=self.asset(d['idea']['music'],'music') if d['idea'].get('music') else None
        for ei,ep in enumerate(d['episodes']):
            if self.paused(d['id']):return
            d['phase']=f'Folge {ei+1}: Dialog, Musik und Geräusche mischen';self.save(d);scenes=[{'seconds':s['render_seconds'],'lines':[l for l in d['lines'] if l['episode']==ei and l['scene']==si],'ambience':s.get('ambience','room'),'sound_cues':s.get('sound_cues',[])} for si,s in enumerate(ep['scenes'])];folder=self.folder(d)/'03_Stimmen'/f'Mischung_{d["audio_revision"]:03}'/f'Folge_{ei+1:02}'
            self.queue_post(d,'mix',ei,{'folder':str(folder),'scenes':scenes,'mood':d['plan']['mood'],
                'music':{'file':music['path'],'sha256':music['sha256']} if music else None,
                'mix':d.get('mix'),'seconds':d['timing'][ei]['seconds']})
        d['state']='audio_mixing';d['phase']='CPU: Dialog, Musik und Geräusche mischen · GPU wieder frei';self.save(d)
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
            d.setdefault('export_history',[]).append({'generation':d.get('export_generation',0),'exports':d.get('exports',[])})
            d['export_generation']=d.get('export_generation',0)+1;d['exports']=[];d.pop('voice_approval',None)
            d['render_segments']={};d['render_tracking_version']=10
            d['state']='voice_review';d['phase']='Ton und Export bearbeiten. Fertige Animationen werden bei passenden Vorgaben weiterverwendet.'
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
            for key in ('voice_approval','sample_approval','error','resume_state','uncertain'):d.pop(key,None)
            d['render_segments']={};d['render_tracking_version']=10
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
            d=self.get(rid)
            if d['state'] not in ('image_review','voice_review','blocked') or (d['state']=='blocked' and d.get('resume_state')=='rendering'):raise HTTPException(409,'Stimmen während der Vorschau ändern.')
            p=next((p for p in d.get('plan',{}).get('cast',[]) if p['name']==body.name),None)
            if not p:raise HTTPException(400,'Figur gehört nicht zum Projekt.')
            p.update(voice_preset=body.voice_preset,voice_description=body.voice_description)
            if body.new_variant:p['voice_variant']=p.get('voice_variant',0)+1
            for participant in d['idea']['participants']:
                if participant['name']==body.name:participant['voice']=None
            d.pop('voice_approval',None);d['previews']=[]
            if d['state']=='voice_review':d['state']='voicing'
            self.save(d);return self.get(rid)
        @app.put('/api/factory/{rid}/dialogues')
        async def edit(rid:str,body:SceneDialogueEdit):
            d=self.get(rid)
            if d['state'] not in ('image_review','voice_review'):raise HTTPException(409,'Dialoge während der Vorschau bearbeiten.')
            try:s=d['episodes'][body.episode]['scenes'][body.scene]
            except IndexError:raise HTTPException(404,'Szene nicht gefunden.')
            if any(l.speaker not in s['cast'] for l in body.dialogues):raise HTTPException(400,'Sprecher muss zur Besetzung der Szene gehören.')
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
        async def edition(rid:str):
            old=self.get(rid);idea=copy.deepcopy(old['idea']);idea['request_key']=uuid.uuid4().hex;idea['title']=(old['title']+' · neue Fassung')[:100];idea['idea']=idea['idea']+'\nÜberarbeitung: Nur EIN Ereignis mit Ziel, Hindernis und Pointe. Keine gesamte Filmhandlung in einer Minute. Mehrere kurze Dialogwechsel und passende Altersstimmen. Alte Vorgaben mit einem Satz je Szene sind aufgehoben. Bei Lebensmittel-Parodien keine Verwandlung in Menschen.'
            if len(idea['idea'])>100000:idea['idea']=old['idea']['idea']
            create=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/factory' and 'POST' in (getattr(r,'methods',None) or set()));return create(Idea.model_validate(idea))
