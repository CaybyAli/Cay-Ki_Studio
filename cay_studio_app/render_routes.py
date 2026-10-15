"""Animation checks and explicit local setup; tracked and stopped with the dashboard."""
import asyncio,json,os,signal
from pathlib import Path
import httpx
from fastapi import HTTPException
from render_studio import audio_graph,fast_models

def add_routes(factory,app):
    f=factory;f.animation_setup=None;f.animation_setup_process=None
    record=f.g['RUNTIME']/'logs/animation_status.json'
    try:f.animation_setup_status=json.loads(record.read_text())
    except (OSError,ValueError):f.animation_setup_status={'state':'idle'}
    if f.animation_setup_status.get('state')=='running':f.animation_setup_status={'state':'interrupted','error':'Einrichtung unterbrochen. Erneut starten; vorhandene Downloads werden weiterverwendet.'}
    def save_status():f.atomic(record,json.dumps(f.animation_setup_status,ensure_ascii=False).encode())
    @app.get('/api/factory/render-studio/status')
    async def status():
        checks=[]
        try:info=await f.object_info()
        except Exception as e:info={};checks.append({'name':'ComfyUI','ready':False,'detail':str(e)})
        for name,fn in [('Schnelle Bildbewegung',lambda:fast_models(info)),('Mundbewegung mit Ton',lambda:audio_graph(info,'probe.png','probe.wav','check',1,1)),('Schnelle Mundbewegung',lambda:audio_graph(info,'probe.png','probe.wav','check',1,1,'fast'))]:
            try:fn();checks.append({'name':name,'ready':True,'detail':'Modelle und Anschlüsse verfügbar; GPU-Probe noch erforderlich.'})
            except Exception as e:checks.append({'name':name,'ready':False,'detail':str(e)})
        path=f.g['RUNTIME']/'logs/animation_einrichtung.log';log=''
        if path.exists():
            with path.open('rb') as stream:stream.seek(max(0,path.stat().st_size-4000));log=stream.read().decode(errors='replace')
        result=dict(f.animation_setup_status)
        stale='CayWanVideoSampler' in info and 'cay_audio_cfg_steps' not in info['CayWanVideoSampler'].get('input',{}).get('optional',{})
        if 'WanVideoSampler' in info and ('CayWanVideoSampler' not in info or stale) and (f.comfy/'custom_nodes/cay_studio_sampler/__init__.py').is_file():
            result.update(state='restart_required',message='Sampler-Reparatur ist installiert. PC nach Ende des laufenden Schritts neu starten und Cay Studio öffnen. Keine erneute Einrichtung nötig.')
        return {**result,'checks':checks,'running':bool(f.animation_setup and not f.animation_setup.done()),'log':log}
    async def install():
        path=f.g['RUNTIME']/'logs/animation_einrichtung.log';path.parent.mkdir(parents=True,exist_ok=True)
        f.animation_setup_status={'state':'running'};save_status()
        try:
            # Dependencies must not change while studio inference is active.
            async with f.g['GPU_LOCK']:
                async with httpx.AsyncClient(trust_env=False,timeout=10) as client:
                    queue=await f.g['get_json'](client,f.g['COMFY']+'/queue')
                    if queue is None or queue.get('queue_running') or queue.get('queue_pending'):raise RuntimeError('ComfyUI zuerst starten und laufende Aufträge fertig werden lassen.')
                python=f.base/'envs/comfyui/bin/python'
                with path.open('ab') as log:
                    f.animation_setup_process=await asyncio.create_subprocess_exec(str(python),str(Path(__file__).with_name('render_studio.py')),'--base',str(f.base),stdout=log,stderr=log,start_new_session=True)
                    code=await f.animation_setup_process.wait()
                    if code:raise RuntimeError('Einrichtung angehalten. Ursache steht unten im Protokoll.')
                f.animation_setup_status={'state':'restart_required','message':'Einrichtung beendet. ComfyUI neu starten, dann Prüfung aktualisieren.'}
        except asyncio.CancelledError:
            proc=f.animation_setup_process
            if proc and proc.returncode is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:await asyncio.wait_for(proc.wait(),15)
                except asyncio.TimeoutError:os.killpg(proc.pid,signal.SIGKILL);await proc.wait()
            f.animation_setup_status={'state':'interrupted','error':'Einrichtung unterbrochen. Erneut starten, um fortzusetzen.'}
            raise
        except Exception as error:f.animation_setup_status={'state':'failed','error':str(error)}
        finally:f.animation_setup_process=None;save_status()
    @app.post('/api/factory/render-studio/setup')
    async def setup():
        if f.animation_setup and not f.animation_setup.done():return {'state':'running'}
        if f.g['GPU_LOCK'].locked():raise HTTPException(409,'Zuerst die laufende Produktion nach dem aktuellen Schritt pausieren. Die Einrichtung ändert Modellabhängigkeiten.')
        f.animation_setup=asyncio.create_task(install());return {'state':'running'}
