"""Durable, project-scoped measurements. Percentages are never simulated."""
import asyncio
import json
import math
import time
from collections import defaultdict
from comfy_socket import messages
from studio_quality_policy import segments, scene_segments, settings
from factory_timing import off_screen

LABELS = {'LoadImage':'Referenzbild laden','UNETLoader':'Animationsmodell bereitstellen',
          'CLIPLoader':'Textmodell bereitstellen','CLIPTextEncode':'Text verarbeiten',
          'VAELoader':'Bilddecoder bereitstellen','WanImageToVideo':'Startbild vorbereiten',
          'ModelSamplingSD3':'Animation vorbereiten','VAEDecode':'Bilder decodieren',
          'VAEDecodeTiled':'Bilder abschnittsweise decodieren','CreateVideo':'Clip zusammensetzen',
          'SaveVideo':'Clip speichern','CayWanVideoSampler':'Mundbewegung animieren','WanVideoSampler':'Mundbewegung animieren','MultiTalkWav2VecEmbeds':'Sprache zeitlich analysieren','WanVideoTextEncodeCached':'Animationsbeschreibung vorbereiten','WanVideoPassImagesFromSamples':'Sprechbilder bereitstellen'}


def graph_info(graph):
    by_kind={n.get('class_type'):n.get('inputs',{}) for n in graph.values()}
    talk='WanVideoSampler' in by_kind or 'CayWanVideoSampler' in by_kind
    source=by_kind.get('WanVideoImageToVideoMultiTalk',{}) if talk else by_kind.get('WanImageToVideo',{})
    sampler=by_kind.get('CayWanVideoSampler',by_kind.get('WanVideoSampler',{})) if talk else by_kind.get('KSamplerAdvanced',{})
    return {'width':source.get('width'),'height':source.get('height'),
            'frames':by_kind.get('MultiTalkWav2VecEmbeds',{}).get('num_frames') if talk else source.get('length'),
            'steps':sampler.get('steps'),'native_fps':25 if talk else 16,'audio_conditioned':talk,
            'vae_decode':'InfiniteTalk' if talk else ('VAEDecodeTiled' if 'VAEDecodeTiled' in by_kind else 'VAEDecode'),
            'clip':by_kind.get('WanVideoTextEncodeCached',{}).get('model_name') if talk else by_kind.get('CLIPLoader',{}).get('clip_name'),
            'models':{n:x['inputs'].get('unet_name',x['inputs'].get('model')) for n,x in graph.items() if x.get('class_type') in ('UNETLoader','WanVideoModelLoader','MultiTalkModelLoader')},
            'acceleration':any(x.get('class_type') in ('LoraLoaderModelOnly','WanVideoLoraSelect') for x in graph.values())}


def profile_key(info):
    return json.dumps({k:info.get(k) for k in ('width','height','steps','models','vae_decode','clip','native_fps','audio_conditioned','acceleration')},sort_keys=True)


class RenderProgress:
    def __init__(self,factory):
        self.f=factory;self.connected=asyncio.Event();self.live={};self.last_flush={}
        self.client_id='cay-studio-factory'

    def init(self):
        self.f.sql('''CREATE TABLE IF NOT EXISTS factory_metrics(
            step_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,submitted REAL,started REAL,
            ended REAL,updated REAL,detail TEXT NOT NULL)''')
        self.f.sql('CREATE INDEX IF NOT EXISTS factory_metrics_run ON factory_metrics(run_id)')

    def load(self,step):
        if step['id'] in self.live:return self.live[step['id']]
        rows=self.f.rows('SELECT * FROM factory_metrics WHERE step_id=?',(step['id'],))
        if rows:
            item=dict(rows[0]);item['detail']=json.loads(item['detail'])
            if item['detail'].get('node_started') is not None:
                item['detail']['node_started']=None;item['detail']['coverage']='partial'
        else:
            item={'step_id':step['id'],'run_id':step['run_id'],'submitted':None,'started':None,
                  'ended':None,'updated':None,'detail':{'profile':graph_info(json.loads(step['graph'])),
                  'nodes':{},'cached':[],'coverage':'partial','status':'unknown'}}
        self.live[step['id']]=item
        # Retain only a bounded set; complete history remains in SQLite.
        if len(self.live)>128:
            for key in list(self.live):
                if key!=step['id'] and self.live[key].get('ended'):
                    self.live.pop(key);self.last_flush.pop(key,None)
                    if len(self.live)<=64:break
        return item

    def flush(self,item,force=False):
        now=time.time()
        if not force and now-self.last_flush.get(item['step_id'],0)<2:return
        self.f.sql('INSERT OR REPLACE INTO factory_metrics VALUES(?,?,?,?,?,?,?)',
                   tuple(item.get(k) for k in ('step_id','run_id','submitted','started','ended','updated'))+(json.dumps(item['detail']),))
        self.last_flush[item['step_id']]=now

    def submitted(self,step):
        item=self.load(step)
        if item['submitted'] is None:item['submitted']=time.time()
        item['detail']['status']='queued';self.flush(item,True)

    def queue(self,step,state):
        item=self.load(step)
        if item['detail'].get('status')!=state:
            item['detail']['status']=state;item['updated']=time.time();self.flush(item,True)

    def close_node(self,item,now):
        detail=item['detail'];node=detail.get('node');start=detail.pop('node_started',None)
        if node and start is not None:
            duration=max(0,now-start)
            detail['nodes'].setdefault(node,{'seconds':0,'first_progress_seconds':None})['seconds']+=duration

    def event(self,message):
        data=message.get('data') or {};kind=message.get('type')
        if not isinstance(data,dict):return
        pid=data.get('prompt_id')
        if not pid:return
        steps=self.f.rows('SELECT * FROM factory_steps WHERE prompt_id=?',(pid,))
        if not steps:return
        step=steps[0]
        if step['status'] not in ('submitting','submitted'):return
        item=self.load(step);detail=item['detail'];now=time.time()
        if kind=='execution_start':
            item['started']=now;detail['coverage']='events';detail['status']='running'
        elif kind=='execution_cached':detail['cached']=list(data.get('nodes',[]))
        elif kind=='executing':
            node=str(data['node']) if data.get('node') is not None else None
            if node==detail.get('node') and detail.get('node_started') is not None:return
            self.close_node(item,now);detail.update(node=node,node_started=now if node else None)
            detail.pop('progress',None)
            if node:
                graph=json.loads(step['graph']);typ=graph.get(node,{}).get('class_type','')
                detail['label']=('Animation · erste Hälfte' if node=='11' else 'Animation · zweite Hälfte') if typ=='KSamplerAdvanced' else LABELS.get(typ,typ or 'Arbeitsschritt')
                detail['status']='running'
        elif kind=='progress':
            node=str(data.get('node') or detail.get('node') or '')
            if not node or node!=detail.get('node'):return
            value=data.get('value');maximum=data.get('max')
            if not isinstance(value,(int,float)) or not isinstance(maximum,(int,float)) or maximum<=0:return
            progress={'value':value,'max':maximum}
            if detail.get('progress')==progress:return
            detail['progress']=progress
            stats=detail['nodes'].setdefault(node,{'seconds':0,'first_progress_seconds':None})
            if stats['first_progress_seconds'] is None and detail.get('node_started'):
                stats['first_progress_seconds']=max(0,now-detail['node_started'])
        elif kind in ('execution_success','execution_error','execution_interrupted'):
            self.close_node(item,now);detail['node']=None
            detail['status']='complete' if kind=='execution_success' else 'failed'
            if kind=='execution_success':item['ended']=now
        else:return
        item['updated']=now;self.flush(item,kind!='progress')

    def complete(self,step,history,copy_seconds):
        item=self.load(step);now=time.time();self.close_node(item,now)
        # History timestamps survive reconnects and process restarts.
        for kind,data in history.get('status',{}).get('messages',[]):
            stamp=data.get('timestamp')
            if isinstance(stamp,(int,float)):
                if kind=='execution_start':item['started']=stamp/1000
                if kind=='execution_success':item['ended']=stamp/1000
        item['ended']=item['ended'] or now;item['updated']=now
        item['detail'].update(status='done',node=None,copy_seconds=copy_seconds)
        self.flush(item,True)

    async def listen(self):
        while not self.f.g['STOPPING']:
            try:
                async for message in messages(self.f.g['COMFY'],self.client_id,self.connected):
                    self.event(message)
            except asyncio.CancelledError:raise
            except Exception:
                # Socket failure never cancels or repeats a render. HTTP history
                # remains the authoritative completion channel.
                pass
            finally:
                for item in list(self.live.values()):
                    if item['detail'].get('node_started'):
                        # A disconnected interval must not be attributed to a node.
                        self.close_node(item,time.time());item['detail']['coverage']='partial';self.flush(item,True)
            await asyncio.sleep(3)

    def history(self,limit=400):
        """Seconds per frame of recently finished animation sections of all projects, by profile key."""
        out=defaultdict(list)
        for r in self.f.rows('SELECT started,ended,detail FROM factory_metrics WHERE started IS NOT NULL AND ended IS NOT NULL ORDER BY ended DESC LIMIT ?',(limit,)):
            try:detail=json.loads(r['detail'])
            except ValueError:continue
            profile=detail.get('profile') or {};frames=profile.get('frames');seconds=r['ended']-r['started']
            if detail.get('status')=='done' and frames and seconds>0:out[profile_key(profile)].append(seconds/frames)
        return out

    def estimate(self,d,remaining,samples,rows,metrics,active,selected_profile):
        """Remaining animation time, per kind of section (lip-sync and silent motion are timed apart,
        a film mixes both). Measurements of this project first; with fewer than three of a kind, the
        same kind of section in earlier films on this PC. Returns (eta, note): eta None with a note
        that says what is still missing."""
        if not remaining or d.get('paused') or d['state']!='rendering':return None,None
        # The profile each kind renders with: the running section, else the latest finished one.
        latest={}
        for row in rows:
            m=metrics.get(row['id'])
            if not m:continue
            profile=m['detail'].get('profile') or {}
            if row['status']=='done' or (active and row['id']==active['step_id']):latest[bool(profile.get('audio_conditioned'))]=profile
        if active and active['detail'].get('profile'):latest[bool(active['detail']['profile'].get('audio_conditioned'))]=active['detail']['profile']
        history=None;low=high=0.;sources=set();missing=[]
        for talk in (True,False):
            frames=sum(f for _,f,t in remaining if t==talk)
            if not frames:continue
            profile=latest.get(talk);values=list(samples.get(profile_key(profile),[])) if profile else []
            if len(values)<3:
                history=history if history is not None else self.history()
                if profile:values=values+history.get(profile_key(profile),[])
                else:
                    # Nothing of this kind rendered yet here: same kind and size from earlier films.
                    fits=[k for k in history if json.loads(k).get('audio_conditioned')==talk and json.loads(k).get('width')==selected_profile.get('width')]
                    values=[v for k in fits for v in history[k]]
                if len(values)>=3:sources.add('history')
            else:sources.add('project')
            if len(values)<3:missing.append('Sprechabschnitten' if talk else 'Bewegungsabschnitten');continue
            values=sorted(values)
            q=lambda x:values[min(len(values)-1,max(0,round(x*(len(values)-1))))]
            low+=q(.2)*frames*.9;high+=q(.8)*frames*1.15
        if missing:
            return None,'Restzeit folgt nach drei fertigen '+' und drei '.join(missing)
        elapsed=max(0,time.time()-active['started']) if active and active.get('started') else 0
        eta={'low':max(0,low-elapsed),'high':max(0,high-elapsed),'source':'project' if sources=={'project'} else 'history'}
        return (eta if eta['high']>0 else None),None

    def snapshot(self,d):
        rows=self.f.rows('SELECT * FROM factory_steps WHERE run_id=? AND step_key LIKE \'video%\'',(d['id'],))
        metrics={r['step_id']:{**r,'detail':json.loads(r['detail'])} for r in self.f.rows('SELECT * FROM factory_metrics WHERE run_id=?',(d['id'],))}
        metrics.update({k:v for k,v in self.live.items() if v['run_id']==d['id']})
        # New runs record the exact chosen step; legacy projects retain validated
        # video09 keys. Never count duplicate attempts as additional segments.
        chosen=d.get('render_segments',{});by_slot={}
        for r in rows:
            parts=r['step_key'].split(':')
            if len(parts)<5:continue
            slot=':'.join(parts[1:4]);wanted=chosen.get(slot)
            if wanted and wanted!=r['id']:continue
            if not wanted and (parts[0]!='video09' or d.get('render_tracking_version')==10):continue
            old=by_slot.get(slot)
            if not old or r['status']=='done':by_slot[slot]=r
        episodes=[];done=total=0;active=None;last=None;latest=None;samples=defaultdict(list)
        for row in rows:
            m=metrics.get(row['id'])
            if not m:continue
            if m.get('updated'):last=max(last or 0,m['updated'])
            if row['status']=='done' and m.get('started') and m.get('ended'):
                seconds=m['ended']-m['started'];profile=m['detail']['profile'];frames=profile.get('frames')
                if seconds>0 and frames:samples[profile_key(profile)].append(seconds/frames)
            if row['status'] in ('submitted','submitting'):
                active={'step_id':row['id'],'prompt_id':row['prompt_id'],**m}
        remaining=[];options=settings(d['idea'])
        from factory_video import VIDEO_MODELS
        from studio_quality_policy import PROFILES
        selected_profile=PROFILES[options['quality']]
        # Compare actual graphs, not a historical global mean or all projects.
        for ei,episode in enumerate(d.get('episodes',[])):
            completed=count=0;current=None
            export_index=next((i for i,e in enumerate(d.get('exports',[])) if e['episode']==ei),None)
            job=next((j for j in d.get('cpu_jobs',[]) if j['kind']=='export' and j['episode']==ei),None)
            for si,scene in enumerate(episode['scenes']):
                # A 0.18 reaction carries a voice from off-screen but renders as silent motion.
                talking=options['lip_sync']=='audio' and not off_screen(scene) and any(l['episode']==ei and l['scene']==si for l in d.get('lines',[]))
                durations=scene_segments(scene.get('render_seconds',scene.get('seconds',0)),options['fps'],talking)
                for seg,duration in enumerate(durations):
                    count+=1;row=by_slot.get(f'{ei}:{si}:{seg}')
                    if row and row['status']=='done':
                        completed+=1;latest={'step_id':row['id'],'episode':ei,'scene':si,'segment':seg}
                    else:
                        is_talk=talking
                        remaining.append((row,4*math.ceil(duration*(25 if is_talk else 16)/4)+1,is_talk))
                        if row and active and row['id']==active['step_id']:
                            current={'scene':si,'segment':seg,'segments':len(durations)};active.update(episode=ei,**current)
            status=('done' if export_index is not None else 'exporting' if job and job['status']=='running' else
                    'export_queued' if job and job['status']=='queued' else 'blocked' if job and job['status']=='failed' else
                    'rendering' if current else 'clips_ready' if completed==count and count else 'waiting')
            episodes.append({'episode':ei,'title':episode['title'],'done':completed,'total':count,'status':status,'export_index':export_index})
            done+=completed;total+=count
        eta,eta_note=self.estimate(d,remaining,samples,rows,metrics,active,selected_profile)
        if active:
            timestamp=active.get('started') or active.get('submitted')
            active['elapsed']=max(0,time.time()-timestamp) if timestamp else None
            active['queue_seconds']=max(0,active['started']-active['submitted']) if active.get('started') and active.get('submitted') else None
        first=min((m['submitted'] for m in metrics.values() if m.get('submitted')),default=None)
        return {'project':d['id'],'state':d['state'],'paused':bool(d.get('paused')),'done':done,'total':total,
                'episodes':episodes,'active':active,'last_progress':last,'latest_clip':latest,
                'elapsed':time.time()-first if first else None,'eta':eta,'eta_note':eta_note,'socket_connected':self.connected.is_set(),
                'note':'Restzeit betrifft Animation, ohne CPU-Export. Grundlage: vergleichbare abgeschlossene Abschnitte dieses Projekts.'}
