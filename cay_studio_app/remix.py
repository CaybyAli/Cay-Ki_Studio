"""Persistent, separately reviewed character replacement jobs sharing the local GPU queue."""
from pathlib import Path
import asyncio,json,math,os,signal,sys,uuid
import httpx
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from pydantic import Field,model_validator
from typing import Literal
from factory import Factory,Wait,Uncertain,packed,digest,uid
from factory_models import Strict,Review
from factory_video import ff,probe,file_hash
from image_workflow import validate_nodes,build_graph
from remix_engine import MODEL,edit_models,graph,segment_inputs,finish_edit,SEGMENT_FRAMES,PIPELINE_POLICY,anchor_indices
from remix_identity import model_ready
from wan_text_encoder import local_ready as text_ready,validate_selected

class Replacement(Strict):
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)
    reference:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    prompt:str=Field(default='',max_length=1800)
    kind:Literal['reference','person','dog','cat','animal','object']='reference'
    @model_validator(mode='after')
    def content(self):
        if not self.reference and len(self.prompt.strip())<5:raise ValueError('Jeder Punkt braucht ein Ersatzbild oder eine Beschreibung.')
        return self

class EditRequest(Strict):
    request_key:str=Field(pattern=r'^[a-f0-9]{32}$')
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    reference:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    prompt:str=Field(default='',max_length=1800)
    title:str=Field(default='',max_length=100)
    start:float=Field(default=0,ge=0,le=600)
    seconds:float=Field(default=5,ge=2,le=30)
    x:float=Field(default=.5,ge=0,le=1)
    y:float=Field(default=.5,ge=0,le=1)
    kind:Literal['reference','person','dog','cat','animal','object']='reference'
    targets:list[Replacement]=Field(default_factory=list,max_length=4)
    acknowledged:bool=False
    fps:Literal[25,30]=30
    quality:Literal['balanced','high']='high'
    smooth:bool=True
    @model_validator(mode='after')
    def content(self):
        if not self.targets and not self.reference and len(self.prompt.strip())<5:raise ValueError('Ein Ersatzbild oder eine Beschreibung ist erforderlich.')
        if not self.acknowledged:raise ValueError('Nutzungsrechte und Kennzeichnung bestätigen.')
        return self

class EditPrompt(Strict):
    prompt:str=Field(min_length=10,max_length=1800)
    appearance:str=Field(min_length=10,max_length=1500)

class Remix(Factory):
    def init(self):
        with self.g['conn']() as db:db.executescript('''
CREATE TABLE IF NOT EXISTS remix_runs(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,state TEXT NOT NULL,document TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS remix_assets(id TEXT PRIMARY KEY,document TEXT NOT NULL);
''')
        self.init_editor()
        status=self.g['RUNTIME']/'logs/figurentausch_status.json'
        if status.is_file():
            try:
                self.setup_status=json.loads(status.read_text())
                if self.setup_status.get('state')=='running':self.setup_status={'state':'failed','message':'Die Einrichtung wurde unterbrochen. Einrichtung erneut starten; vorhandene Downloads werden weiterverwendet.'}
            except (ValueError,OSError):pass
        for row in self.rows("SELECT id FROM remix_runs WHERE state='blocked'"):
            d=self.get(row['id'])
            if 'Zuerst „Figurentausch einrichten“' in d.get('error',''):
                d.update(state='awaiting_setup',phase='Wartet auf die Einrichtung des Figurenstudios.');d.pop('error',None);self.save(d)
        # Existing reviews must show the actual replacement before any long video pass.
        for row in self.rows("SELECT id FROM remix_runs WHERE state IN ('mask_review','rendering','finishing','blocked')"):
            d=self.get(row['id'])
            if d['state']=='blocked' and d.get('resume_state') not in ('rendering','finishing'):continue
            work=d.get('target_work') or [d]
            if any(w.get('identity_policy')!=PIPELINE_POLICY for w in work):
                if d['state']=='blocked':d['resume_state']='tracking'
                else:d.update(state='tracking',phase='Figurenbilder für den gesamten Verlauf ergänzen.')
                d.pop('approval',None);self.save(d)
    def get(self,rid):
        rows=self.rows('SELECT document FROM remix_runs WHERE id=?',(rid,))
        if not rows:raise HTTPException(404,'Figurentausch nicht gefunden.')
        d=self.controlled(json.loads(rows[0]['document']));d['revision']=digest(d);return d
    def save(self,d):
        if d.get('_parent_id'):
            from remix_targets import save_child
            return save_child(self,d)
        d=dict(d);d.pop('revision',None);d['updated']=self.g['now']()
        self.sql('UPDATE remix_runs SET state=?,document=?,updated=? WHERE id=?',(d['state'],packed(d),d['updated'],d['id']))
        self.atomic(self.folder(d)/'Figurentausch.json',packed(d).encode())
    def folder(self,d):
        root=self.path(self.g['ROOT']/'01_Projekte/Figurentausch'/d['id'])
        return root/f'Punkt_{d["_target_index"]+1:02}' if '_target_index' in d else root
    async def render(self,d,key,graph,video=False):
        if '_target_index' in d:key=f'target{d["_target_index"]}:'+key
        return await super().render(d,key,graph,video)
    def source(self,aid):
        rows=self.rows('SELECT document FROM remix_assets WHERE id=?',(aid,))
        if not rows:raise HTTPException(404,'Originalvideo fehlt.')
        d=json.loads(rows[0]['document']);p=self.path(d['file'])
        if not p.is_file():raise HTTPException(404,'Originalvideo ist nicht mehr vorhanden.')
        return d
    def ready(self):return all(p.is_file() for p in [self.base/'envs/studio-remix/bereit.json',self.base/'envs/studio-remix/bin/python',self.base/'models/studio-remix/SAM2/config.json',self.comfy/'models/diffusion_models'/MODEL]) and text_ready(self.comfy) and model_ready(self.base)
    def setup_checks(self):
        return [{'name':name,'ready':path.is_file()} for name,path in [
            ('Abgeschlossene Einrichtung',self.base/'envs/studio-remix/bereit.json'),
            ('Separate Python-Umgebung',self.base/'envs/studio-remix/bin/python'),
            ('SAM2-Maskenmodell',self.base/'models/studio-remix/SAM2/config.json'),
            ('VACE-Videomodell',self.comfy/'models/diffusion_models'/MODEL)]]+[{'name':'Passendes Wan-Textmodell für ComfyUI','ready':text_ready(self.comfy)},{'name':'Lokale Prüfung auf Figurenwechsel','ready':model_ready(self.base)}]
    async def cpu(self,fn,*args):
        return await self.g['resources'].cpu(self.busy or 'remix',fn.__name__,fn,*args)
    async def setup_edit(self):
        self.setup_status={'state':'running','message':'Fehlende Komponenten werden ergänzt. Vorhandene Modelle werden weiterverwendet.'}
        self.atomic(self.g['RUNTIME']/'logs/figurentausch_status.json',packed(self.setup_status).encode())
        log=self.g['RUNTIME']/'logs/figurentausch_einrichtung.log';log.parent.mkdir(parents=True,exist_ok=True)
        try:
            async with self.g['GPU_LOCK']:
                with log.open('ab') as stream:
                    self.setup_process=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('remix_prepare.py')),'--base',str(self.base),'--setup',stdout=stream,stderr=stream,start_new_session=True)
                    code=await self.setup_process.wait()
            if code or not self.ready():raise RuntimeError(log.read_text(errors='replace')[-1400:])
            self.setup_status={'state':'ready','message':'Figurentausch eingerichtet. Zuerst einen kurzen Ausschnitt testen.'}
        except asyncio.CancelledError:
            if self.setup_process and self.setup_process.returncode is None:
                os.killpg(self.setup_process.pid,signal.SIGTERM)
                try:await asyncio.wait_for(self.setup_process.wait(),15)
                except asyncio.TimeoutError:os.killpg(self.setup_process.pid,signal.SIGKILL);await self.setup_process.wait()
            raise
        except Exception as e:self.setup_status={'state':'failed','message':str(e)}
        finally:
            self.setup_process=None
            self.atomic(self.g['RUNTIME']/'logs/figurentausch_status.json',packed(self.setup_status).encode())
    async def _prepare_one(self,d):
        if not self.ready():
            d.update(state='awaiting_setup',phase='Wartet auf die Einrichtung des Figurenstudios.');self.save(d);return
        req=d['request'];source=self.source(req['asset_id'])
        if await self.cpu(file_hash,source['file'])!=source['sha256']:raise RuntimeError('Originalvideo wurde verändert.')
        edit_models(await self.object_info(),self.comfy)
        if not d.get('english'):
            d['phase']='Ersatzfigur vorbereiten';self.save(d)
            d['english']=await self.llm(EditPrompt,'Translate the supplied replacement request into concise English instructions for a video editing model. Only replace the selected character. Preserve the camera, scene, background, actions and timing. The original audio is kept separately. No new dialogue. If a reference image is supplied, describe it as the replacement reference; do not invent unseen details. appearance describes one full-body replacement character on a plain background, for image generation.',{'description':req['prompt'],'replacement_type':req.get('kind','reference'),'has_reference_image':bool(req['reference'])});self.save(d)
            await self.release_planner()
        if not d.get('reference_file'):
            if req['reference']:d['reference_file']=self.asset(req['reference'],'image')['path']
            else:
                models=validate_nodes(await self.object_info());result=await self.render(d,'replacement-reference',build_graph(d['english']['appearance']+'. One single character, full body, clean neutral background. No text.',[],int(digest(d['id'])[:12],16),'',models))
                d['reference_file']=result['output']
            self.save(d)
        folder=self.folder(d)/'Verfolgung';meta=folder/'Tracking.json'
        if not meta.is_file():
            async with httpx.AsyncClient(trust_env=False,timeout=20) as c:await self.idle(c,True)
            job={'source':source['file'],'source_hash':source['sha256'],'start':req['start'],'seconds':req['seconds'],
                 'width':source['width'],'height':source['height'],'point':[req['x'],req['y']],
                 'exclude_points':[[t['x'],t['y']] for i,t in enumerate(self.get(d['id'])['request'].get('targets',[])) if i!=d.get('_target_index')],
                 'folder':str(folder)}
            path=self.folder(d)/'Maskenauftrag.json';self.atomic(path,packed(job).encode());d['phase']='Gewählte Figur verfolgen und Maskenvorschau erstellen';self.save(d)
            await self.command([self.base/'envs/studio-remix/bin/python',Path(__file__).with_name('remix_prepare.py'),'--base',self.base,'--job',path],7200)
        d['tracking']=json.loads(meta.read_text());d['mask_hash']=file_hash(folder/'mask.mp4');d['reference_hash']=file_hash(d['reference_file'])
        from remix_targets import prepare_anchor
        await prepare_anchor(self,d)
        if self.paused(d['id']):return
        if sorted(a['frame'] for a in d.get('identity_anchors',[]))!=anchor_indices(d['tracking']['frames']):raise RuntimeError('Die Figurenbilder sind noch nicht vollständig. Vorbereitung fortsetzen.')
        d['state']='mask_review';d['phase']='Maske und Ersatzfigur prüfen. Erst deine Freigabe startet die Videobearbeitung.';self.save(d)
    async def check_identity(self,d,video,sha256,start,frames):
        folder=self.folder(d)/'Verfolgung';report=folder/f'Figurenpruefung_{sha256[:16]}_{start}_{frames}.json'
        if report.is_file():
            cached=json.loads(report.read_text())
            if cached.get('video_sha256')==sha256:return cached
        job={'folder':str(folder),'video':str(video),'sha256':sha256,'start_frame':start,'frames':frames,
             'total_frames':d['tracking']['frames'],'reference':d['reference_file'],'kind':d['request'].get('kind','reference'),'anchors':d.get('identity_anchors',[]),'report':str(report)}
        path=folder/'Pruefauftrag.json';self.atomic(path,packed(job).encode())
        await self.command([self.base/'envs/studio-remix/bin/python',Path(__file__).with_name('remix_identity.py'),'--base',self.base,'--job',path],900)
        return json.loads(report.read_text())
    async def _produce_one(self,d):
        folder=self.folder(d)/'Verfolgung';source=self.source(d['request']['asset_id']);req=d['request']
        if not d.get('approval'):raise RuntimeError('Zuerst Maske und Ersatzfigur freigeben.')
        if file_hash(folder/'mask.mp4')!=d['mask_hash'] or file_hash(d['reference_file'])!=d['reference_hash'] or file_hash(source['file'])!=source['sha256']:raise RuntimeError('Eine freigegebene Eingabedatei wurde verändert.')
        if not d.get('anchor_file'):raise RuntimeError('Ersetzte Startbildvorschau fehlt. Auswahl neu vorbereiten; kein langer Blind-Render gestartet.')
        if file_hash(d['anchor_file'])!=d['anchor_hash']:raise RuntimeError('Freigegebenes Startbild wurde verändert.')
        if d.get('identity_policy')!=PIPELINE_POLICY or sorted(a['frame'] for a in d.get('identity_anchors',[]))!=anchor_indices(d['tracking']['frames']):
            d.update(state='tracking',phase='Figuren über den gesamten Verlauf vorbereiten.');d.pop('approval',None);self.save(d);return
        from remix_targets import KINDS
        models=edit_models(await self.object_info(),self.comfy);reference=self.stage(d['reference_file']);clips=d.setdefault('clips',[])
        validate_selected(self.comfy,models['clip'])
        total=d['tracking']['frames'];count=math.ceil(total/SEGMENT_FRAMES)
        for i in range(count):
            if self.paused(d['id']):return
            if len(clips)>i:continue
            d['phase']=f'Figurentausch · Abschnitt {i+1} von {count}';self.save(d)
            previous=clips[-1]['file'] if clips else None
            control,masks,length,take=await self.cpu(segment_inputs,folder,i,total,previous,d.get('anchor_file'),d['identity_anchors'])
            # Core LoadVideo lists root-level files. Stage them there without user names.
            def stage_video(path):
                name='cay_remix_'+file_hash(path)[:32]+'.mp4';target=self.comfy/'input'/name
                if not target.exists():shutil_copy(path,target)
                return name
            for attempt in range(d.setdefault('clip_attempts',{}).get(str(i),0),2):
                kind=req.get('kind','reference')
                text=d['english']['prompt']+' The selected subject is replaced completely by '+KINDS.get(kind,KINDS['reference'])+'. The same replacement subject is visible at EVERY moment. Preserve its face, species, markings and clothing throughout. Use all the supplied control keyframes. Never restore the original person, even during fast gestures or occlusion.'
                g=graph(stage_video(control),stage_video(masks),reference,text,models,d['tracking']['width'],d['tracking']['height'],length,int(digest([d['id'],d.get('_target_index',0),i,attempt,d.get('quality_round',0)])[:12],16),'high' if attempt else req.get('quality','balanced'),kind)
                d['phase']=f'Figurentausch · Abschnitt {i+1}/{count}'+(' · gezielte Wiederholung' if attempt else '');self.save(d)
                result=await self.render(d,'remix12:'+str(i)+':'+digest(g)[:16],g,True)
                d['phase']=f'Figur im Verlauf prüfen · Abschnitt {i+1}/{count}';self.save(d)
                report=await self.check_identity(d,result['output'],result['sha256'],i*SEGMENT_FRAMES,take)
                if report['status']=='pass':
                    clips.append({'file':result['output'],'sha256':result['sha256'],'frames':take,'identity_check':report});d.pop('quality_issue',None);self.save(d);break
                d['clip_attempts'][str(i)]=attempt+1
                d['quality_issue']={'segment':i,'file':result['output'],'sha256':result['sha256'],'report':report};self.save(d)
                if self.paused(d['id']):return
            if len(clips)<=i:
                d.update(state='quality_review',phase='Die Figur verändert sich möglicherweise. Der weitere Renderlauf wartet; den auffälligen Abschnitt prüfen.');self.save(d);return
        if self.paused(d['id']):return
        d['state']='finishing';d['phase']='CPU: Originalton und Hintergrund zusammensetzen';self.save(d)
    async def _finish_one(self,d):
        folder=self.folder(d)/'Verfolgung';source=self.source(d['request']['asset_id']);req=d['request'];clips=d['clips']
        d['phase']='Originalton übernehmen, Hintergrund erhalten und Export prüfen';self.save(d)
        out=self.folder(d)/'Figurentausch_Vorschau.mp4'
        d['export']=await self.cpu(finish_edit,folder,source['file'],req['start'],req['seconds'],clips,source['width'],source['height'],out,req.get('fps',25),req.get('smooth',False))
        report=await self.check_identity(d,d['export']['file'],d['export']['sha256'],0,d['tracking']['frames'])
        d['final_identity_check']=report
        d['state']='done' if '_target_index' in d else 'result_review';d['phase']='Ergebnis über die gesamte Länge prüfen und freigeben.';self.save(d)
    async def prepare(self,d):
        if d['request'].get('targets'):
            from remix_targets import prepare_multi
            return await prepare_multi(self,d)
        return await self._prepare_one(d)
    async def produce(self,d):
        if d['request'].get('targets'):
            from remix_targets import produce_multi
            return await produce_multi(self,d)
        return await self._produce_one(d)
    async def finish_output(self,d):
        if d['request'].get('targets'):
            from remix_targets import composite_targets,target_document
            d['export']=await self.cpu(composite_targets,self,d);self.save(d)
            for index in range(len(d['request']['targets'])):
                child=target_document(self.get(d['id']),index)
                child['phase']='Zusammengesetztes Ergebnis auf Figurenwechsel prüfen';self.save(child)
                child['final_composite_check']=await self.check_identity(child,d['export']['file'],d['export']['sha256'],0,child['tracking']['frames']);self.save(child)
            d=self.get(d['id']);d.update(state='result_review',phase='Zusammengesetztes Video vollständig prüfen und freigeben.');self.save(d);return
        return await self._finish_one(d)
    async def worker(self):
        while not self.g['STOPPING']:
            try:
                for row in self.rows("SELECT id FROM remix_runs WHERE state IN ('tracking','rendering','awaiting_setup','finishing') ORDER BY created"):
                    d=self.get(row['id'])
                    if d.get('paused') or self.g['MAINTENANCE']:continue
                    if d['state']=='awaiting_setup':
                        if not self.ready():continue
                        d.update(state='tracking',phase='Einrichtung erkannt. Vorbereitung wartet.');self.save(d)
                    if d['state']=='finishing':
                        self.busy=d['id']
                        try:await self.finish_output(d)
                        except Exception as error:
                            d.update(state='blocked',resume_state='finishing',error=str(error)[:1700]);self.save(d)
                        finally:self.busy=None
                        break
                    async with self.g['GPU_LOCK']:
                        d=self.get(row['id'])
                        if d.get('paused') or self.g['MAINTENANCE'] or d['state'] not in ('tracking','rendering'):continue
                        self.busy=d['id'];stage=d['state']
                        try:await (self.prepare(d) if stage=='tracking' else self.produce(d))
                        except Wait as e:
                            latest=self.get(d['id']);latest['phase']=str(e);self.save(latest)
                        except Exception as e:
                            latest=self.get(d['id']);latest.update(state='blocked',resume_state=stage,error=str(e)[:2000],uncertain=isinstance(e,Uncertain));self.save(latest)
                        finally:
                            await self.release_planner()
                            self.busy=None
                    break
            except asyncio.CancelledError:raise
            except Exception as e:
                try:self.g['record']('remix_worker_error',str(e)[:1200])
                except Exception:pass      # full disk: keep the worker alive
            await asyncio.sleep(2)
    def routes(self,app):
        self.editor_routes(app,'remix')
        @app.get('/api/remix/{rid}/diagnostics')
        async def diagnosis(rid:str):return await self.diagnostics(rid)
        @app.get('/api/remix/status')
        async def status():
            result=dict(self.setup_status)
            if self.ready():
                try:edit_models(await self.object_info(),self.comfy);result={'state':'ready','message':'Figurentausch eingerichtet. Zuerst fünf Sekunden testen.'}
                except Exception as e:result={'state':'missing_nodes','message':str(e)}
            result['checks']=self.setup_checks()
            if not self.ready() and result['state'] in ('ready','missing'):
                result.update(state='missing',message='Figurenstudio noch nicht vollständig eingerichtet. Fehlend: '+', '.join(x['name'] for x in result['checks'] if not x['ready'])+'. Einrichtung starten; bestehende Downloads bleiben erhalten.')
            if result['state'] in ('running','failed','missing'):
                log=self.g['RUNTIME']/'logs/figurentausch_einrichtung.log'
                if log.is_file():
                    with log.open('rb') as f:f.seek(max(0,log.stat().st_size-1400));result['log']=f.read().decode(errors='replace')
            return result
        @app.post('/api/remix/setup')
        async def setup():
            if self.ready():return {'state':'ready'}
            if self.g['GPU_LOCK'].locked():raise HTTPException(409,'Bitte die laufende Produktion nach dem aktuellen Schritt pausieren. Danach Figurenstudio ergänzen.')
            if not self.setup_task or self.setup_task.done():self.setup_task=asyncio.create_task(self.setup_edit())
            return {'state':'running'}
        @app.get('/api/remix')
        def listing():return {'runs':[d for x in self.rows('SELECT id FROM remix_runs ORDER BY created DESC') if not (d:=self.get(x['id'])).get('deleted')]}
        @app.post('/api/remix/import')
        async def upload(request:Request,name:str='Video.mp4'):
            if Path(name).suffix.lower() not in ('.mp4','.mov','.mkv','.webm'):raise HTTPException(400,'Video als MP4, MOV, MKV oder WebM hochladen.')
            folder=self.g['ROOT']/'00_Eingang/Figurentausch';folder.mkdir(parents=True,exist_ok=True);aid=uid();temp=folder/(aid+'.upload');dest=folder/(aid+Path(name).suffix.lower());size=0
            try:
                with temp.open('xb') as stream:
                    async for chunk in request.stream():
                        size+=len(chunk)
                        if size>500*1024**2:raise HTTPException(413,'Originalvideo höchstens 500 MB. Vorher einen Ausschnitt speichern.')
                        stream.write(chunk)
                info=await self.cpu(probe,temp);video=next((s for s in info['streams'] if s['codec_type']=='video'),None)
                seconds=float(info['format'].get('duration',0))
                if not video or not 2<=seconds<=600:raise HTTPException(400,'Ein Video zwischen 2 Sekunden und 10 Minuten wählen. Bearbeitet werden bis zu 30 Sekunden.')
                if not 32<=video['width']<=7680 or not 32<=video['height']<=7680:raise HTTPException(400,'Ungültige Videogröße.')
                width,height=video['width'],video['height']
                rotation=next((float(s.get('rotation',0)) for s in video.get('side_data_list',[]) if 'rotation' in s),float(video.get('tags',{}).get('rotate',0)))
                if abs(rotation)%180==90:width,height=height,width
                os.replace(temp,dest);doc={'id':aid,'name':name[:200],'file':str(dest),'sha256':await self.cpu(file_hash,dest),'seconds':seconds,'width':width,'height':height,'has_audio':any(s['codec_type']=='audio' for s in info['streams'])}
                self.sql('INSERT INTO remix_assets VALUES(?,?)',(aid,packed(doc)));return doc
            except HTTPException:raise
            except Exception as e:raise HTTPException(400,'Video konnte nicht gelesen werden: '+str(e)[-300:])
            finally:temp.unlink(missing_ok=True)
        @app.get('/api/remix/assets/{aid}/frame')
        async def frame(aid:str,time:float=0):
            source=self.source(aid)
            if not math.isfinite(time) or not 0<=time<source['seconds']:raise HTTPException(400,'Vorschaustelle liegt außerhalb des Videos.')
            dest=self.path(Path(source['file']).with_name(aid+'_frame_'+str(round(time*1000))+'.png'))
            if not dest.exists():await self.cpu(ff,['-protocol_whitelist','file,pipe','-ss',time,'-i',source['file'],'-frames:v','1','-vf','scale=960:960:force_original_aspect_ratio=decrease',dest])
            return FileResponse(dest,media_type='image/png')
        @app.get('/api/remix/assets/{aid}')
        def asset_metadata(aid:str):return self.source(aid)
        @app.get('/api/remix/assets/{aid}/content')
        def original(aid:str):
            source=self.source(aid);return FileResponse(source['file'])
        @app.post('/api/remix')
        def create(body:EditRequest):
            old=self.rows('SELECT id FROM remix_runs WHERE request_key=?',(body.request_key,))
            if old:
                d=self.get(old[0]['id'])
                if d['request']!=body.model_dump():raise HTTPException(409,'Diese Anfrage wurde bereits mit anderen Angaben gespeichert.')
                return d
            source=self.source(body.asset_id)
            if body.start+body.seconds>source['seconds']+1e-6:raise HTTPException(400,'Der gewählte Ausschnitt reicht über das Ende des Originalvideos.')
            if body.reference:self.asset(body.reference,'image')
            for t in body.targets:
                if t.reference:self.asset(t.reference,'image')
            if len({(round(t.x,4),round(t.y,4)) for t in body.targets})!=len(body.targets):raise HTTPException(400,'Jede Figur braucht einen eigenen Punkt.')
            rid=uid();now=self.g['now']();d={'id':rid,'request':body.model_dump(),'state':'tracking','phase':'Wartet auf die lokale GPU','title':body.title or 'Figurentausch · '+source['name'][:70],'created':now,'updated':now,'paused':False}
            if not self.ready():d.update(state='awaiting_setup',phase='Wartet auf die Einrichtung des Figurenstudios.')
            with self.g['conn']() as db:
                db.execute('INSERT OR IGNORE INTO remix_runs VALUES(?,?,?,?,?,?)',(rid,body.request_key,d['state'],packed(d),now,now));found=db.execute('SELECT id FROM remix_runs WHERE request_key=?',(body.request_key,)).fetchone()[0]
            if found==rid:self.save(d)
            result=self.get(found)
            if result['request']!=body.model_dump():raise HTTPException(409,'Diese Anfrage wurde bereits mit anderen Angaben gespeichert.')
            return result
        @app.get('/api/remix/{rid}')
        def get(rid:str):return self.get(rid)
        @app.post('/api/remix/{rid}/approve')
        def approve(rid:str,body:Review):
            d=self.get(rid);self.revision(d,body,{'mask_review'});d['approval']=body.revision;d['state']='rendering';d['phase']='Videobearbeitung wartet';self.save(d);return self.get(rid)
        @app.post('/api/remix/{rid}/approve-result')
        async def approve_result(rid:str,body:Review):
            d=self.get(rid);self.revision(d,body,{'result_review'})
            export=d['export'];source=self.path(export['file'])
            if await self.cpu(file_hash,source)!=export['sha256']:raise HTTPException(409,'Die Ergebnisdatei wurde verändert. Bitte erneut prüfen.')
            dest=self.g['ROOT']/'03_Fertige_Videos/Figurentausch'/rid/'Figurentausch_KI.mp4'
            await self.cpu(shutil_copy,source,dest)
            d['export']['file']=str(dest);d.update(state='done',phase='Von dir geprüft und freigegeben.');d['result_approval']=body.revision;self.save(d)
            await self.cpu(self.g['scan_media']);return self.get(rid)
        @app.post('/api/remix/{rid}/retry-quality')
        def retry_quality(rid:str,body:Review):
            d=self.get(rid);self.revision(d,body,{'quality_review'})
            if d['request'].get('targets'):
                index=d['quality_target'];work=d['target_work'][index]
            else:work=d
            issue=work.get('quality_issue') or {};segment=str(issue.get('segment',0))
            work.setdefault('clip_attempts',{})[segment]=0;work['quality_round']=work.get('quality_round',0)+1;work['state']='rendering'
            work.pop('quality_issue',None);d.update(state='rendering',phase='Auffälligen Abschnitt gezielt neu erzeugen.');self.save(d);return self.get(rid)
        @app.post('/api/remix/{rid}/pause')
        def pause(rid:str):
            self.get(rid);self.sql('INSERT INTO factory_control VALUES(?,1) ON CONFLICT(id) DO UPDATE SET paused=1',(rid,));return self.get(rid)
        @app.post('/api/remix/{rid}/resume')
        async def resume(rid:str):
            d=self.get(rid)
            if d['state']=='blocked':
                if not self.ready():
                    raise HTTPException(409,'Das lokale Figurenstudio ist noch nicht vollständig eingerichtet. „Figurenstudio ergänzen“ starten; danach diesen Auftrag fortsetzen.')
                await self.diagnostics(rid)
                self.sql("DELETE FROM factory_steps WHERE run_id=? AND status='failed'",(rid,));d['state']=d.pop('resume_state');d.pop('error',None)
            self.sql('INSERT INTO factory_control VALUES(?,0) ON CONFLICT(id) DO UPDATE SET paused=0',(rid,));d['paused']=False
            self.save(d);return self.get(rid)
        @app.get('/api/remix/{rid}/preview/{kind}')
        def preview(rid:str,kind:str,download:bool=False,target:int|None=None,frame:int|None=None):
            d=self.get(rid)
            if target is not None:
                if not 0<=target<len(d.get('target_work',[])):raise HTTPException(404,'Zuordnung fehlt.')
                from remix_targets import target_document
                d=target_document(d,target)
            if kind=='mask' and d.get('tracking'):p=self.folder(d)/'Verfolgung/Maske_Vorschau.mp4';mime='video/mp4'
            elif kind=='anchor' and d.get('anchor_file'):p=self.path(d['anchor_file']);mime='image/png'
            elif kind=='keyframe':
                item=next((a for a in d.get('identity_anchors',[]) if a['frame']==frame),None)
                if not item:raise HTTPException(404,'Figurenbild noch nicht verfügbar.')
                p=self.path(item['file']);mime='image/png'
            elif kind=='quality' and d.get('quality_issue'):p=self.path(d['quality_issue']['file']);mime='video/mp4'
            elif kind=='reference' and d.get('reference_file'):p=self.path(d['reference_file']);mime='image/png'
            elif kind=='export' and d.get('export'):p=self.path(d['export']['file']);mime='video/mp4'
            else:raise HTTPException(404,'Vorschau noch nicht verfügbar.')
            return FileResponse(p,media_type=mime,filename=p.name if download else None)

def shutil_copy(source,dest):
    import shutil
    dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_suffix('.partial');shutil.copyfile(source,temp);os.replace(temp,dest)
