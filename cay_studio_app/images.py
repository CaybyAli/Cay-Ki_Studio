"""Owned image jobs, cast snapshots, recovery and explicit picture selection."""
import asyncio, hashlib, json, os, secrets, time, uuid
from pathlib import Path
import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from image_workflow import MAFIA_TRAITS, png_info, image_prompt, build_graph, validate_nodes


class ImageOrder(BaseModel):
    revision: int = Field(ge=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    cast_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_key: str = Field(pattern=r'^[a-f0-9]{32}$')
    scene: int | None = Field(default=None, ge=0, le=17)
    note: str = Field(default='', max_length=500)
    references_checked: bool


class Selection(BaseModel):
    job_id: str
    sha256: str


class ImageApproval(BaseModel):
    draft_sha256: str
    selection_sha256: str


class VisualProfile(BaseModel):
    style: str = Field(min_length=5, max_length=2000)


class FigureInput(BaseModel):
    role: str = Field(min_length=1, max_length=80, pattern=r"^[\w .'-]+$")
    source_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    traits: str = Field(default='', max_length=1500)


class Images:
    def __init__(self, env):
        self.g = env
        self.base = env['RUNTIME'].parent
        self.comfy_dir = self.base / 'apps/ComfyUI'
        self.setup_error = None
        self.models = None

    def rows(self, *args): return self.g['rows'](*args)
    def execute(self,*args): return self.g['execute'](*args)
    def path(self,value): return self.g['allowed'](self.g['ROOT']/value)
    def atomic(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial')
        try:
            with temp.open('xb') as f:
                f.write(value);f.flush();os.fsync(f.fileno())
            os.replace(temp,path)
        finally:temp.unlink(missing_ok=True)

    def init(self):
        with self.g['conn']() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS project_image_cast(project_id TEXT NOT NULL,role TEXT NOT NULL,asset TEXT NOT NULL,sha256 TEXT NOT NULL,selection TEXT NOT NULL,source TEXT NOT NULL,traits TEXT NOT NULL,PRIMARY KEY(project_id,role));
CREATE TABLE IF NOT EXISTS image_profiles(project_id TEXT PRIMARY KEY,style TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS image_jobs(id TEXT PRIMARY KEY,draft_id TEXT NOT NULL,draft_hash TEXT NOT NULL,scene INTEGER NOT NULL,variant INTEGER NOT NULL,status TEXT NOT NULL,phase TEXT NOT NULL,snapshot TEXT NOT NULL,graph TEXT,prompt_id TEXT,output TEXT,sha256 TEXT,error TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,submitted TEXT);
CREATE TABLE IF NOT EXISTS image_requests(request_key TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS image_selected(draft_id TEXT NOT NULL,draft_hash TEXT NOT NULL,scene INTEGER NOT NULL,job_id TEXT NOT NULL,PRIMARY KEY(draft_id,draft_hash,scene));
CREATE TABLE IF NOT EXISTS image_approvals(draft_id TEXT NOT NULL,draft_hash TEXT NOT NULL,selection_hash TEXT NOT NULL,artifact TEXT NOT NULL,PRIMARY KEY(draft_id,draft_hash));
CREATE TABLE IF NOT EXISTS image_control(id INTEGER PRIMARY KEY,paused INTEGER NOT NULL);
INSERT OR IGNORE INTO image_control VALUES(1,0);
''')

    def cast(self,pid): return self.rows('SELECT * FROM project_image_cast WHERE project_id=? ORDER BY role',(pid,))

    def profile(self,pid):
        project=self.g['project_by_id'](pid)
        saved=self.rows('SELECT style FROM image_profiles WHERE project_id=?',(pid,))
        if saved:return saved[0]['style']
        if project['format']=='Mafia':return 'Natural live-action crime film. Photographic skin, believable anatomy, restrained contrast, readable faces, no beauty retouching or oversharpening.'
        if project['format'] in ('Fruechte','Harry_Butter'):return 'Expressive stylized animated comedy, coherent character designs, clear silhouettes and cinematic lighting.'
        return 'Use the visual style described in the project briefing. Keep lighting, colors and character design consistent across scenes.'

    def cast_hash(self,pid):
        return hashlib.sha256(json.dumps({'figures':self.cast(pid),'style':self.profile(pid)},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def check_assets(self,pid):
        for row in self.cast(pid):
            if png_info(self.path(row['asset']))['sha256']!=row['sha256']:
                raise ValueError('Gesicherte Figurenreferenz verändert: '+row['role'])

    def incoming(self):
        base=self.path('00_Eingang/Bilder');result=[]
        if not base.is_dir():return result
        for path in sorted(base.rglob('*')):
            if len(result)>=200:break
            if path.suffix.lower()!='.png' or not path.is_file() or not path.resolve().is_relative_to(base.resolve()):continue
            rel=path.relative_to(base).as_posix()
            result.append({'id':hashlib.sha256(rel.encode()).hexdigest(),'name':rel})
        return result

    def register(self,pid,body):
        self.g['project_by_id'](pid)
        source=next((x for x in self.incoming() if x['id']==body.source_id),None)
        if not source:raise HTTPException(404,'PNG nicht mehr im Eingang gefunden. Bitte Liste neu öffnen.')
        path=self.path('00_Eingang/Bilder/'+source['name']);info=png_info(path)
        role=body.role.strip()
        if not role:raise HTTPException(400,'Figurenname fehlt.')
        existing=self.cast(pid)
        same=next((r for r in existing if r['role'].casefold()==role.casefold()),None)
        if same:role=same['role']
        if any(r['sha256']==info['sha256'] and r['role']!=role for r in existing):
            raise HTTPException(409,'Dieses Bild gehört in diesem Projekt bereits zu einer anderen Figur.')
        rel=f'02_Medien/Figuren/{pid}/{info["sha256"]}/referenz.png'
        self.atomic(self.path(rel),path.read_bytes())
        self.execute('INSERT INTO project_image_cast VALUES(?,?,?,?,?,?,?) ON CONFLICT(project_id,role) DO UPDATE SET asset=excluded.asset,sha256=excluded.sha256,selection=excluded.selection,source=excluded.source,traits=excluded.traits',
                     (pid,role,rel,info['sha256'],source['name'],str(path),body.traits.strip()))
        self.save_profile(pid)

    def save_profile(self,pid):
        project=self.g['project_by_id'](pid)
        dest=self.path(project['folder']+'/01_Planung/Bildvorgaben_'+uuid.uuid4().hex[:12]+'.json')
        self.atomic(dest,json.dumps({'project_id':pid,'style':self.profile(pid),'figures':self.cast(pid)},ensure_ascii=False,indent=2).encode())

    def import_cast(self,pid):
        # Explicit legacy import applies only to the original Mafia project.
        if pid!='mafia-01':return self.cast(pid)
        sources=self.g['CONFIG'].get('existing_project_sources') or [str(self.base/'projects/Cay_Mafia/Folge_01')]
        source=next((Path(x).resolve() for x in sources if (Path(x)/'Figurenfreigabe_aktuell.json').is_file()),None)
        if not source:raise ValueError('Vorhandene Figurenfreigabe_aktuell.json fehlt. Referenzen können über „Projektbilder & Stil“ zugeordnet werden.')
        approval=json.loads((source/'Figurenfreigabe_aktuell.json').read_text(encoding='utf-8'))['figuren']
        records=[];seen=set()
        for role in MAFIA_TRAITS:
            if role not in approval:continue
            row=approval[role];path=Path(row['bild']).resolve()
            if not path.is_relative_to(source) or not row.get('figurenbild_freigegeben'):raise ValueError('Ungültige Freigabe für '+role)
            info=png_info(path)
            if info['sha256']!=row['sha256']:raise ValueError('Referenz stimmt nicht mit der Freigabe überein: '+role)
            if info['sha256'] in seen:raise ValueError('Zwei Figuren verwenden dasselbe Referenzbild. Import angehalten.')
            seen.add(info['sha256'])
            if role=='Coach' and row.get('auswahl')!='Coach_Anzug_V03':raise ValueError('Coachs alte Freigabe stimmt nicht mit Coach_Anzug_V03 überein.')
            rel=f'02_Medien/Figuren/{pid}/{info["sha256"]}/referenz.png'
            self.atomic(self.path(rel),path.read_bytes())
            records.append((pid,role,rel,info['sha256'],row.get('auswahl',role),str(path),MAFIA_TRAITS[role]))
        if not records:raise ValueError('Keine freigegebenen Mafia-Figuren gefunden.')
        with self.g['conn']() as db:
            db.executemany('INSERT OR IGNORE INTO project_image_cast VALUES(?,?,?,?,?,?,?)',records)
        self.save_profile(pid)
        return self.cast(pid)

    async def preflight(self):
        async with httpx.AsyncClient(trust_env=False,timeout=15) as client:
            r=await client.get(self.g['COMFY']+'/object_info');r.raise_for_status()
            self.models=validate_nodes(r.json())
        return self.models

    def update(self,jid,**data):
        data['updated']=self.g['now']()
        self.execute('UPDATE image_jobs SET '+','.join(k+'=?' for k in data)+' WHERE id=?',(*data.values(),jid))

    def draft_valid(self,job):
        found=self.rows('SELECT status,sha256 FROM drafts WHERE id=?',(job['draft_id'],))
        return found and found[0]['status']=='text_approved' and found[0]['sha256']==job['draft_hash']

    def canonical(self,name,pid):
        aliases={'abu coach':'Coach','coachlim':'Coach','abu tim':'Tim','timgioh':'Tim','alibumaye':'Ali','ali bumaye':'Ali','caybyali':'Cay'} if pid=='mafia-01' else {}
        return aliases.get(name.strip().lower(),next((r['role'] for r in self.cast(pid) if r['role'].casefold()==name.strip().casefold()),name.strip()))

    def enqueue(self,did,body):
        draft=self.g['draft_by_id'](did);project=self.g['project_by_id'](draft['project_id'])
        pid=project['id']
        if not self.models: raise HTTPException(409,'Zuerst „Figuren & Bildworkflow prüfen“ ausführen.')
        if not body.references_checked: raise HTTPException(400,'Bitte die angezeigten Figurenreferenzen prüfen.')
        payload=json.dumps({'draft_id':did,**body.model_dump()},sort_keys=True)
        with self.g['conn']() as db:
            db.execute('BEGIN IMMEDIATE')
            # Re-read approval inside the transaction to reject stale browser state.
            fresh=db.execute('SELECT * FROM drafts WHERE id=?',(did,)).fetchone()
            if fresh['revision']!=body.revision or fresh['sha256']!=body.sha256 or fresh['status']!='text_approved':
                raise HTTPException(409,'Textfreigabe wurde geändert. Entwurf neu öffnen.')
            old=db.execute('SELECT body FROM image_requests WHERE request_key=?',(body.request_key,)).fetchone()
            if old:
                if old[0]!=payload: raise HTTPException(409,'Anforderung wurde mit anderen Eingaben verwendet.')
                return {'ok':True,'reused':True}
            if self.cast_hash(pid)!=body.cast_sha256: raise HTTPException(409,'Figurenreferenzen wurden geändert. Erneut prüfen.')
            scenes=json.loads(fresh['document'])['storyboard']['scenes']
            indices=range(len(scenes)) if body.scene is None else [body.scene]
            if body.scene is not None and body.scene>=len(scenes): raise HTTPException(400,'Szene nicht vorhanden.')
            if db.execute("SELECT 1 FROM image_jobs WHERE draft_id=? AND draft_hash=? AND status IN ('queued','submitting','submitted','uncertain')",(did,body.sha256)).fetchone():
                raise HTTPException(409,'Für diesen Entwurf sind Bildaufträge noch offen. Zuerst abschließen oder wartende Aufträge stoppen.')
            if db.execute("SELECT COUNT(*) FROM image_jobs WHERE status IN ('queued','submitting','submitted')").fetchone()[0]+2*len(indices)>40:
                raise HTTPException(409,'Bildwarteschlange voll. Bitte vorhandene Aufträge abwarten.')
            self.check_assets(pid)
            figures={r['role']:r for r in self.cast(pid)};created=[]
            for index in indices:
                scene=scenes[index];roles=list(dict.fromkeys(self.canonical(r,pid) for r in scene['cast']))
                if len(roles)>3: raise HTTPException(409,f'S{index+1:02}: Mehr als drei Gesichter. Einstellung zuerst aufteilen.')
                if any(r not in figures for r in roles): raise HTTPException(409,'Freigegebene Figur fehlt: '+', '.join(r for r in roles if r not in figures))
                offset=db.execute('SELECT COALESCE(MAX(variant),0) FROM image_jobs WHERE draft_id=? AND draft_hash=? AND scene=?',(did,body.sha256,index)).fetchone()[0]
                for variant in (offset+1,offset+2):
                    jid=uuid.uuid4().hex;seed=secrets.randbelow(2**53)
                    prompt=image_prompt(scene,roles,draft['document']['project_snapshot']['brief'],{r:figures[r]['traits'] for r in roles},self.profile(pid))
                    if body.note.strip():prompt+='\nAdditional visual direction: '+body.note.strip()
                    snapshot={'scene':scene,'roles':roles,'references':[figures[r] for r in roles], 'prompt':prompt,'seed':seed,'models':self.models,
                              'project_folder':project['folder'],'draft_revision':draft['revision'],'cast_hash':body.cast_sha256}
                    db.execute("INSERT INTO image_jobs(id,draft_id,draft_hash,scene,variant,status,phase,snapshot,created,updated) VALUES(?,?,?,?,?,'queued','Bild wartet auf freie GPU',?,?,?)",
                               (jid,did,body.sha256,index,variant,json.dumps(snapshot,ensure_ascii=False),self.g['now'](),self.g['now']()))
                    created.append(jid)
            db.execute('INSERT INTO image_requests VALUES(?,?)',(body.request_key,payload))
        return {'ok':True,'jobs':created}

    def selection_data(self,did,dhash):
        selected=self.rows('SELECT scene,job_id FROM image_selected WHERE draft_id=? AND draft_hash=? ORDER BY scene',(did,dhash))
        digest=hashlib.sha256(json.dumps(selected,sort_keys=True).encode()).hexdigest()
        return selected,digest

    def summary(self,did):
        draft=self.g['draft_by_id'](did)
        jobs=self.rows('SELECT id,draft_hash,scene,variant,status,phase,prompt_id,output,sha256,error,created,updated,submitted FROM image_jobs WHERE draft_id=? AND draft_hash=? ORDER BY scene,variant',(did,draft['sha256']))
        selected,digest=self.selection_data(did,draft['sha256'])
        approval=self.rows('SELECT selection_hash FROM image_approvals WHERE draft_id=? AND draft_hash=?',(did,draft['sha256']))
        return {'jobs':jobs,'selected':selected,'selection_sha256':digest,'approved':bool(approval and approval[0]['selection_hash']==digest),
                'paused':bool(self.rows('SELECT paused FROM image_control WHERE id=1')[0]['paused'])}

    def stage(self,job):
        snapshot=json.loads(job['snapshot']);refs=[]
        for row in snapshot['references']:
            source=self.path(row['asset'])
            if png_info(source)['sha256']!=row['sha256']: raise ValueError('Figurenreferenz nach Auftragserteilung verändert: '+row['role'])
            rel=f'CayStudio/refs/{row["sha256"]}/referenz.png'
            dest=(self.comfy_dir/'input'/rel).resolve()
            if not dest.is_relative_to((self.comfy_dir/'input').resolve()): raise ValueError('Ungültiger Referenzpfad.')
            if dest.exists():
                if png_info(dest)['sha256']!=row['sha256']: raise ValueError('Eine gestagte Referenz wurde verändert.')
            else:self.atomic(dest,source.read_bytes())
            refs.append(rel)
        graph=build_graph(snapshot['prompt'],refs,snapshot['seed'],'CayStudio/'+job['id'],snapshot['models'])
        # All and only this scene's identities are connected to the sampler.
        if [n['inputs']['image'] for n in graph.values() if n['class_type']=='LoadImage']!=refs:
            raise ValueError('Unerwartete Gesichtsreferenz im Bildworkflow.')
        folder=self.path(snapshot['project_folder']+'/02_Szenenbilder/'+job['draft_id']+'/'+job['draft_hash'][:16])
        self.atomic(folder/'Auftraege'/(job['id']+'.json'),json.dumps({'job_id':job['id'],'snapshot':snapshot,'graph':graph},ensure_ascii=False,indent=2).encode())
        return graph

    async def recover(self,client,job):
        # Submission intent is stored before POST. Never resend after an uncertain acknowledgement.
        queue=await self.g['get_json'](client,self.g['COMFY']+'/queue')
        history=await self.g['get_json'](client,self.g['COMFY']+'/history?max_items=500')
        if queue is None or history is None:return None
        candidates=[]
        for entry in queue.get('queue_running',[])+queue.get('queue_pending',[]):
            if len(entry)>3 and isinstance(entry[3],dict) and entry[3].get('cay_studio_job_id')==job['id']:candidates.append(entry[1])
        for pid,value in history.items():
            prompt=value.get('prompt',[])
            if len(prompt)>3 and isinstance(prompt[3],dict) and prompt[3].get('cay_studio_job_id')==job['id']:candidates.append(pid)
        ids=set(candidates)
        if len(ids)==1:return next(iter(ids))
        return None

    async def process(self,job):
        try:
            async with httpx.AsyncClient(trust_env=False,timeout=15) as client:
                if job['status']=='queued':
                    if not self.draft_valid(job):
                        self.update(job['id'],status='cancelled',phase='Textfreigabe geändert; Bild nicht gestartet');return
                    queue=await self.g['get_json'](client,self.g['COMFY']+'/queue')
                    loaded=await self.g['get_json'](client,self.g['OLLAMA']+'/api/ps')
                    if queue is None or loaded is None or queue.get('queue_running') or queue.get('queue_pending') or loaded.get('models'):
                        self.update(job['id'],phase='Wartet auf freie ComfyUI-Queue und entladenes Sprachmodell');return
                    await self.preflight()
                    graph=self.stage(job)
                    with self.g['conn']() as db:
                        db.execute('BEGIN IMMEDIATE')
                        current=db.execute('SELECT status FROM image_jobs WHERE id=?',(job['id'],)).fetchone()
                        draft=db.execute('SELECT status,sha256 FROM drafts WHERE id=?',(job['draft_id'],)).fetchone()
                        paused=db.execute('SELECT paused FROM image_control WHERE id=1').fetchone()[0]
                        if current['status']!='queued' or paused:return
                        if not draft or draft['status']!='text_approved' or draft['sha256']!=job['draft_hash']:
                            db.execute("UPDATE image_jobs SET status='cancelled',phase='Textfreigabe geändert',updated=? WHERE id=?",(self.g['now'](),job['id']))
                            return
                        db.execute("UPDATE image_jobs SET status='submitting',phase='Bildauftrag wird übergeben',graph=?,submitted=?,updated=? WHERE id=?",(json.dumps(graph),self.g['now'](),self.g['now'](),job['id']))
                    try:
                        result=await client.post(self.g['COMFY']+'/prompt',json={'prompt':graph,'client_id':'cay-studio','extra_data':{'cay_studio_job_id':job['id']}})
                        if result.status_code==400:
                            self.update(job['id'],status='failed',phase='ComfyUI hat den Bildworkflow abgelehnt',error=result.text[:1800]);return
                        result.raise_for_status();answer=result.json()
                        pid=answer.get('prompt_id')
                        if not isinstance(pid,str) or answer.get('node_errors'):raise ValueError('ComfyUI hat keine eindeutige Auftragsbestätigung geliefert.')
                    except (httpx.HTTPError,ValueError) as error:
                        self.update(job['id'],status='uncertain',phase='Übergabe unklar – Status prüfen, nicht erneut rendern',error=str(error)[:1000]);return
                    self.update(job['id'],status='submitted',prompt_id=pid,phase='ComfyUI rendert / Auftrag wartet')
                else:
                    pid=job['prompt_id'] or await self.recover(client,job)
                    if not pid:
                        self.update(job['id'],status='uncertain',phase='Auftrag nicht eindeutig wiedergefunden; keine doppelte Übergabe');return
                    self.update(job['id'],status='submitted',prompt_id=pid,phase='Vorhandenen Auftrag wiedergefunden')
                # Pause acts between pictures. A submitted picture is always collected.
                missing=0
                while not self.g['STOPPING']:
                    history=await self.g['get_json'](client,self.g['COMFY']+'/history/'+pid)
                    item=(history or {}).get(pid)
                    if item:
                        status=item.get('status',{})
                        if status.get('status_str')=='error':
                            from comfy_diagnostics import report,summary
                            detail=report(status,prompt_id=pid)
                            self.update(job['id'],status='failed',phase='ComfyUI-Bildauftrag fehlgeschlagen',error=summary(detail));return
                        pictures=item.get('outputs',{}).get('77',{}).get('images',[])
                        if pictures:
                            picture=pictures[0]
                            if picture.get('type')!='output':raise ValueError('Unerwarteter Bildausgabetyp.')
                            base=(self.comfy_dir/'output').resolve()
                            source=(base/picture.get('subfolder','')/picture['filename']).resolve()
                            if not source.is_relative_to(base):raise ValueError('Bild liegt außerhalb des ComfyUI-Ausgabeordners.')
                            info=png_info(source);snapshot=json.loads(job['snapshot'])
                            dest=self.path(snapshot['project_folder']+'/02_Szenenbilder/'+job['draft_id']+'/'+job['draft_hash'][:16]+f'/S{job["scene"]+1:02}_V{job["variant"]:02}_{job["id"][:8]}.png')
                            self.atomic(dest,source.read_bytes())
                            if png_info(dest)['sha256']!=info['sha256']:raise ValueError('Bildkopie konnte nicht bestätigt werden.')
                            self.update(job['id'],status='done',phase='Bild zur Auswahl bereit',output=dest.relative_to(self.g['ROOT']).as_posix(),sha256=info['sha256'],error=None);return
                        if status.get('completed'):raise ValueError('ComfyUI fertig, aber kein Bild am erwarteten Ausgang.')
                    elif history is not None:
                        queue=await self.g['get_json'](client,self.g['COMFY']+'/queue')
                        if queue is not None and not any(len(r)>1 and r[1]==pid for r in queue.get('queue_running',[])+queue.get('queue_pending',[])):
                            missing+=1
                            if missing>=3:
                                self.update(job['id'],status='uncertain',phase='ComfyUI-Auftrag nicht mehr auffindbar. Status prüfen.');return
                        else:missing=0
                    await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise  # Persisted submitting/submitted state is deliberately retained for recovery.
        except Exception as error:
            self.update(job['id'],status='failed',phase='Bildauftrag angehalten',error=str(error)[:1800])

    async def worker(self):
        while not self.g['STOPPING']:
            try:
                jobs=self.rows("SELECT * FROM image_jobs WHERE status IN ('submitting','submitted') ORDER BY created LIMIT 1")
                if not jobs and not self.rows('SELECT paused FROM image_control WHERE id=1')[0]['paused']:
                    jobs=self.rows("SELECT * FROM image_jobs WHERE status='queued' ORDER BY created LIMIT 1")
                if jobs and not self.g['MAINTENANCE']:
                    async with self.g['GPU_LOCK']:
                        # Re-read after lock acquisition: pause/cancel may have happened while waiting.
                        job=self.rows('SELECT * FROM image_jobs WHERE id=?',(jobs[0]['id'],))[0]
                        paused=self.rows('SELECT paused FROM image_control WHERE id=1')[0]['paused']
                        if job['status'] in ('submitting','submitted') or (job['status']=='queued' and not paused):await self.process(job)
            except asyncio.CancelledError:raise
            except Exception as error:self.setup_error=str(error)[:1000]
            await asyncio.sleep(2)

    def routes(self,app):
        @app.get('/api/images/setup')
        def setup(project_id:str='mafia-01'):
            self.g['project_by_id'](project_id)
            return {'figures':self.cast(project_id),'cast_sha256':self.cast_hash(project_id),'ready':bool(self.models),'error':self.setup_error,
                    'style':self.profile(project_id),'profile':'Flux 2 Klein · 864 × 1536 · 4 Schritte · zwei Varianten je Auftrag'}

        @app.get('/api/images/incoming')
        def incoming():return {'files':self.incoming()}

        @app.put('/api/projects/{pid}/image-profile')
        def profile(pid:str,body:VisualProfile):
            self.g['project_by_id'](pid)
            if len(body.style.strip())<5:raise HTTPException(400,'Bitte den Bildstil beschreiben.')
            self.execute('INSERT INTO image_profiles VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET style=excluded.style',(pid,body.style.strip()))
            self.save_profile(pid);return setup(pid)

        @app.post('/api/projects/{pid}/figures')
        def register(pid:str,body:FigureInput):
            try:self.register(pid,body);return setup(pid)
            except (ValueError,OSError) as error:raise HTTPException(400,str(error))

        @app.delete('/api/projects/{pid}/figures/{role}')
        def remove(pid:str,role:str):
            self.g['project_by_id'](pid)
            self.execute('DELETE FROM project_image_cast WHERE project_id=? AND role=?',(pid,role))
            self.save_profile(pid);return setup(pid)

        @app.post('/api/images/prepare')
        async def prepare(project_id:str='mafia-01'):
            self.g['project_by_id'](project_id)
            try:
                if project_id=='mafia-01' and not self.cast(project_id):self.import_cast(project_id)
                self.check_assets(project_id);await self.preflight();self.setup_error=None
                return setup(project_id)
            except Exception as error:
                self.models=None;self.setup_error=str(error)[:1800]
                raise HTTPException(409,self.setup_error)

        @app.get('/api/images/figures/{role}')
        def figure(role:str,project_id:str='mafia-01'):
            self.g['project_by_id'](project_id)
            found=self.rows('SELECT asset FROM project_image_cast WHERE project_id=? AND role=?',(project_id,role))
            if not found:raise HTTPException(404,'Figur in diesem Projekt nicht zugeordnet.')
            return FileResponse(self.path(found[0]['asset']),media_type='image/png')

        @app.get('/api/drafts/{did}/images')
        def listing(did:str):return self.summary(did)

        @app.post('/api/drafts/{did}/images')
        def order(did:str,body:ImageOrder):return self.enqueue(did,body)

        @app.get('/api/images/{jid}/content')
        def picture(jid:str,download:bool=False):
            found=self.rows("SELECT output FROM image_jobs WHERE id=? AND status='done'",(jid,))
            if not found:raise HTTPException(404,'Bild noch nicht verfügbar.')
            path=self.path(found[0]['output'])
            return FileResponse(path,media_type='image/png',filename=path.name if download else None)

        @app.post('/api/drafts/{did}/images/select')
        def select(did:str,body:Selection):
            with self.g['conn']() as db:
                db.execute('BEGIN IMMEDIATE')
                draft=db.execute('SELECT * FROM drafts WHERE id=?',(did,)).fetchone()
                job=db.execute('SELECT * FROM image_jobs WHERE id=?',(body.job_id,)).fetchone()
                if not draft or not job:raise HTTPException(404,'Entwurf oder Bild nicht gefunden.')
                if draft['status']!='text_approved' or job['draft_id']!=did or job['draft_hash']!=draft['sha256']:
                    raise HTTPException(409,'Dieses Bild gehört nicht zur aktuellen Textfreigabe.')
                if job['status']!='done' or body.sha256!=job['sha256'] or png_info(self.path(job['output']))['sha256']!=body.sha256:
                    raise HTTPException(409,'Bilddatei wurde verändert oder ist noch nicht fertig.')
                db.execute('INSERT INTO image_selected VALUES(?,?,?,?) ON CONFLICT(draft_id,draft_hash,scene) DO UPDATE SET job_id=excluded.job_id',
                           (did,draft['sha256'],job['scene'],job['id']))
            return self.summary(did)

        @app.post('/api/drafts/{did}/images/approve')
        def approve(did:str,body:ImageApproval):
            with self.g['conn']() as db:
                db.execute('BEGIN IMMEDIATE')
                draft=db.execute('SELECT * FROM drafts WHERE id=?',(did,)).fetchone()
                if not draft or draft['status']!='text_approved' or draft['sha256']!=body.draft_sha256:
                    raise HTTPException(409,'Textfreigabe verändert. Aktuellen Entwurf öffnen.')
                document=json.loads(draft['document']);selected,digest=self.selection_data(did,draft['sha256'])
                if digest!=body.selection_sha256:raise HTTPException(409,'Bildauswahl wurde zwischenzeitlich geändert.')
                if [r['scene'] for r in selected]!=list(range(len(document['storyboard']['scenes']))):
                    raise HTTPException(409,'Für jede Szene zuerst ein Bild auswählen.')
                result=[]
                for selection in selected:
                    job=db.execute("SELECT * FROM image_jobs WHERE id=? AND status='done'",(selection['job_id'],)).fetchone()
                    if not job or job['draft_hash']!=draft['sha256'] or png_info(self.path(job['output']))['sha256']!=job['sha256']:
                        raise HTTPException(409,'Eine ausgewählte Bilddatei wurde verändert.')
                    result.append({'scene':job['scene'],'job_id':job['id'],'image':job['output'],'sha256':job['sha256'],'source':json.loads(job['snapshot'])})
                project=self.g['project_by_id'](draft['project_id'])
                dest=self.path(project['folder']+'/02_Szenenbilder/'+did+'/'+draft['sha256'][:16]+'/Bildfreigabe_'+uuid.uuid4().hex[:12]+'.json')
                self.atomic(dest,json.dumps({'draft_id':did,'draft_sha256':draft['sha256'],'selection_sha256':digest,'created':self.g['now'](),'images':result,'animation_authorized':False},ensure_ascii=False,indent=2).encode())
                db.execute('INSERT INTO image_approvals VALUES(?,?,?,?) ON CONFLICT(draft_id,draft_hash) DO UPDATE SET selection_hash=excluded.selection_hash,artifact=excluded.artifact',
                           (did,draft['sha256'],digest,dest.relative_to(self.g['ROOT']).as_posix()))
            return {'ok':True,'animation_started':False}

        @app.post('/api/images/pause')
        def pause():self.execute('UPDATE image_control SET paused=1 WHERE id=1');return {'ok':True}

        @app.post('/api/images/resume')
        def resume():self.execute('UPDATE image_control SET paused=0 WHERE id=1');return {'ok':True}

        @app.post('/api/drafts/{did}/images/cancel-pending')
        def cancel(did:str):
            self.g['draft_by_id'](did)
            self.execute("UPDATE image_jobs SET status='cancelled',phase='Wartenden Auftrag gestoppt',updated=? WHERE draft_id=? AND status='queued'",(self.g['now'](),did))
            return {'ok':True,'running_kept':True}

        @app.post('/api/images/{jid}/recover')
        def recover(jid:str):
            found=self.rows('SELECT * FROM image_jobs WHERE id=?',(jid,))
            if not found:raise HTTPException(404,'Bildauftrag nicht gefunden.')
            if found[0]['status']=='uncertain':
                self.update(jid,status='submitting',phase='Prüfe bestehenden ComfyUI-Auftrag')
            return {'ok':True}
