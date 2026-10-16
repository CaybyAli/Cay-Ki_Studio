"""Durable CPU post-production queue, separate from the GPU lease."""
import asyncio
import hashlib
import json
from pathlib import Path
from factory_video import finish, prepare, file_hash
from factory_audio import mix


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)


class PostProduction:
    def init_post(self):
        self.post_tasks={};self.export_locks={}
        self.sql('''CREATE TABLE IF NOT EXISTS factory_post(
            id TEXT PRIMARY KEY,run_id TEXT NOT NULL,kind TEXT NOT NULL,episode INTEGER NOT NULL,
            generation INTEGER NOT NULL,spec TEXT NOT NULL,status TEXT NOT NULL,
            result TEXT,error TEXT,UNIQUE(run_id,kind,generation,episode))''')
        self.sql("UPDATE factory_post SET status='queued' WHERE status='running'")

    def post_rows(self,d,kind):
        generation=d.get('audio_revision',0) if kind=='mix' else d.get('export_generation',0)
        return self.rows('SELECT * FROM factory_post WHERE run_id=? AND kind=? AND generation=? ORDER BY episode',
                         (d['id'],kind,generation))

    def merge_posts(self,d):
        # Only this table is written by the CPU worker. GPU saves cannot overwrite it.
        rows_=self.post_rows(d,'export')
        if rows_:
            exports={p['episode']:p for p in d.get('exports',[])}
            for row in rows_:
                if row['status']=='done':exports[row['episode']]=json.loads(row['result'])
            d['exports']=[exports[i] for i in sorted(exports)]
        d['cpu_jobs']=[{'episode':r['episode'],'kind':r['kind'],'status':r['status'],'error':r['error']}
                       for r in [*rows_,*self.post_rows(d,'mix'),*self.rows("SELECT * FROM factory_post WHERE run_id=? AND generation=? AND kind LIKE 'prepare:%'",(d['id'],d.get('export_generation',0)))] if r['status']!='done']
        return d

    def queue_post(self,d,kind,episode,spec):
        generation=d.get('audio_revision',0) if kind=='mix' else d.get('export_generation',0)
        raw=canonical(spec);key=hashlib.sha256((d['id']+kind+str(generation)+str(episode)+raw).encode()).hexdigest()
        self.sql('INSERT OR IGNORE INTO factory_post(id,run_id,kind,episode,generation,spec,status) VALUES(?,?,?,?,?,?,?)',
                 (key,d['id'],kind,episode,generation,raw,'queued'))
        existing=self.rows('SELECT id,status FROM factory_post WHERE run_id=? AND kind=? AND episode=? AND generation=?',
                           (d['id'],kind,episode,generation))[0]
        if existing['id']!=key and kind.startswith('prepare:'):
            # The export encodes every part again from its own spec; an outdated
            # pre-encoding (e.g. after an update changed the segments) is harmless.
            if existing['status']!='running':
                self.sql('DELETE FROM factory_post WHERE id=?',(existing['id'],))
                self.sql('INSERT OR IGNORE INTO factory_post(id,run_id,kind,episode,generation,spec,status) VALUES(?,?,?,?,?,?,?)',
                         (key,d['id'],kind,episode,generation,raw,'queued'))
            return
        if existing['id']!=key:raise RuntimeError('Die Nachbearbeitung gehört zu einer anderen Freigabe. Bitte die aktuelle Fassung erneut prüfen.')

    async def post_execute(self,row):
        spec=json.loads(row['spec']);resources=self.g['resources']
        try:
            if row['kind']=='export' or row['kind'].startswith('prepare:'):
                work=resources.workspace(row['run_id'],row['episode'])
                spec['folder']=str(work)
                lock=self.export_locks.setdefault((row['run_id'],row['episode']),asyncio.Lock())
                async with lock:
                    result=await resources.cpu(row['run_id'],'Abschnitt vorbereiten' if row['kind'].startswith('prepare:') else 'Schnitt / Export',prepare if row['kind'].startswith('prepare:') else finish,spec)
                result.update(episode=row['episode'],title=spec['title'])
                if row['kind']=='export':(work/'.completed').touch()
            else:
                def mixing():
                    path=mix(Path(spec['folder']),spec['scenes'],spec['mood'],spec.get('music'),spec.get('mix'),spec.get('edit_policy',17))
                    return {'episode':row['episode'],'file':str(path),'sha256':file_hash(path),'seconds':spec['seconds']}
                result=await resources.cpu(row['run_id'],'Tonmischung',mixing)
            self.sql("UPDATE factory_post SET status='done',result=?,error=NULL WHERE id=?",(canonical(result),row['id']))
            if row['kind']=='export':await asyncio.to_thread(self.g['scan_media'])
        except asyncio.CancelledError:
            self.sql("UPDATE factory_post SET status='queued' WHERE id=? AND status='running'",(row['id'],))
            raise
        except Exception as error:
            self.sql("UPDATE factory_post SET status='failed',error=? WHERE id=?",(str(error)[:1700],row['id']))

    async def post_worker(self):
        try:
            while not self.g['STOPPING']:
                try:
                    for key,task in list(self.post_tasks.items()):
                        if task.done():
                            try:await task
                            except Exception:
                                # Its own status write failed (disk full for a moment): queue it again, as after a restart.
                                self.sql("UPDATE factory_post SET status='queued' WHERE id=? AND status='running'",(key,))
                            self.post_tasks.pop(key,None)
                    if not self.g['MAINTENANCE']:
                        limit=self.g['resources'].options['workers']-len(self.post_tasks)
                        if limit>0:
                            candidates=self.rows("SELECT p.* FROM factory_post p JOIN factory_runs r ON r.id=p.run_id LEFT JOIN factory_control c ON c.id=r.id LEFT JOIN studio_trash t ON t.id=r.id WHERE p.status='queued' AND COALESCE(c.paused,0)=0 AND t.id IS NULL AND r.state IN ('rendering','finishing','audio_mixing') ORDER BY p.rowid")
                            for row in candidates:
                                if limit<=0:break
                                d=self.get(row['run_id'])
                                generation=d.get('audio_revision',0) if row['kind']=='mix' else d.get('export_generation',0)
                                if row['generation']!=generation:continue
                                self.sql("UPDATE factory_post SET status='running' WHERE id=? AND status='queued'",(row['id'],))
                                self.post_tasks[row['id']]=asyncio.create_task(self.post_execute(row));limit-=1
                except Exception as error:
                    # A failed database write must not end mixing and export for good; the next round tries again.
                    try:self.g['record']('post_worker_error',str(error)[:1200])
                    except Exception:pass
                await asyncio.sleep(.4)
        finally:
            tasks=list(self.post_tasks.values())
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            self.post_tasks.clear()

    def collect_posts(self,d):
        kind='mix' if d['state']=='audio_mixing' else 'export'
        jobs=self.post_rows(d,kind)
        failed=next((j for j in jobs if j['status']=='failed'),None)
        if failed:
            d.update(resume_state=d['state'],state='blocked',error='Nachbearbeitung: '+failed['error'])
            self.save(d);return
        if len(jobs)!=len(d['episodes']) or any(j['status']!='done' for j in jobs):return
        if kind=='mix':
            d['previews']=[json.loads(j['result']) for j in jobs]
            d['state']='voice_review';d['phase']='Die ganze Folge mit Dialog, Musik und Geräuschen anhören.'
        else:
            d['exports']=[json.loads(j['result']) for j in jobs]
            d['state']='done';d['phase']='Alle Folgen sind fertig. Du kannst sie ansehen und selbst hochladen.'
        self.save(d)
