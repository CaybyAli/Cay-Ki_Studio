"""Local, schema-checked animation adapters. No paid service or implicit fallback."""
from pathlib import Path
import math,json,hashlib,subprocess,os,shutil
FAST_REPO='lightx2v/Wan2.2-Lightning'
FAST_REVISION='18bccf8884ec0a078eed79785eb4ef13ea16ce1e'
TALK_MODEL='Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors'
WRAPPER_REVISION='088128b224242e110d3906c6750e9a3a348a659b'
FAST_DIR='Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1'
FAST_NAMES={k:FAST_DIR+'/'+k+'_noise_model.safetensors' for k in ('high','low')}

def fields(info,kind):
    node=info.get(kind)
    if not node:raise ValueError('Animationserweiterung fehlt: '+kind+'. Animation einrichten und ComfyUI nach laufenden Aufträgen neu starten.')
    inp=node.get('input',{});return inp.get('required',{}),inp.get('optional',{})

def node(info,kind,**values):
    required,optional=fields(info,kind);out={}
    for key,schema in {**required,**optional}.items():
        if key in values:out[key]=values[key];continue
        opt=schema[1] if len(schema)>1 and isinstance(schema[1],dict) else {}
        # API workflows do not receive optional widget values from a browser.
        # Explicit schema defaults avoid None entering version-dependent code.
        if key not in required and not ('default' in opt and opt['default'] is not None and (schema[0] in ('INT','FLOAT','BOOLEAN','STRING') or isinstance(schema[0],list))):continue
        if 'default' in opt:out[key]=opt['default']
        elif isinstance(schema[0],list) and schema[0]:out[key]=schema[0][0]
        else:raise ValueError(f'Nicht unterstützter Pflichtanschluss: {kind}.{key}. Keine Animation gestartet.')
    for key,value in out.items():
        spec={**required,**optional}[key]
        if kind not in ('LoadImage','LoadAudio') and isinstance(spec[0],list) and not isinstance(value,list) and value not in spec[0]:raise ValueError(f'Nicht verfügbare Auswahl: {kind}.{key} = {value}')
    return {'class_type':kind,'inputs':out}

def option(info,kind,field,predicate):
    required,optional=fields(info,kind);choices={**required,**optional}.get(field,[[]])[0]
    if not isinstance(choices,list):raise ValueError(f'Modellliste fehlt: {kind}.{field}')
    match=next((x for x in choices if isinstance(x,str) and predicate(x.replace('\\','/').lower())),None)
    if not match:raise ValueError('Passendes lokales Modell fehlt: '+kind+'.'+field+'. Unter Animation einrichten ergänzen.')
    return match

def fast_models(info):
    return {k:option(info,'LoraLoaderModelOnly','lora_name',lambda x,k=k:x.endswith(FAST_NAMES[k].lower())) for k in FAST_NAMES}

def talk_models(info,fast=False):
    names={
      'model':option(info,'WanVideoModelLoader','model',lambda x:x.endswith('/'+TALK_MODEL.lower()) or x==TALK_MODEL.lower()),
      'talk':option(info,'MultiTalkModelLoader','model',lambda x:'infinitetalk' in x and 'single' in x),
      'wav':option(info,'Wav2VecModelLoader','model',lambda x:'wav2vec' in x and ('chinese' in x or 'tencent' in x)),
      'vae':option(info,'WanVideoVAELoader','model_name',lambda x:'vae' in x and ('2_1' in x or '2.1' in x)),
      'text':option(info,'WanVideoTextEncodeCached','model_name',lambda x:x.rsplit('/',1)[-1]=='umt5-xxl-enc-bf16.safetensors'),
      'vision':option(info,'CLIPVisionLoader','clip_name',lambda x:x.endswith('clip_vision_h.safetensors')),
    }
    if fast:names['lora']=option(info,'WanVideoLoraSelect','lora',lambda x:'lightx2v' in x and 'i2v' in x and '480p' in x and 'cfg_step' in x)
    return names

def audio_graph(info,image,audio,prompt,seed,seconds,quality='high',prefix=''):
    """25 native FPS, isolated dialogue only, exact onset/pauses; no background music."""
    if 'CayWanVideoSampler' not in info:
        raise ValueError('Die Sampler-Reparatur ist noch nicht in ComfyUI geladen. Nach dem Update laufende Arbeit pausieren, den PC neu starten und Cay Studio öffnen. Keine neuen Modelle nötig.')
    m=talk_models(info,quality=='fast');n=lambda kind,**kw:node(info,kind,**kw)
    size=(720,1280) if quality=='high' else (576,1024)
    frames=4*math.ceil(seconds*25/4)+1
    g={'1':n('LoadImage',image=image),'2':n('LoadAudio',audio=audio),
       '3':n('WanVideoVAELoader',model_name=m['vae'],precision='bf16'),
       '4':n('MultiTalkModelLoader',model=m['talk']),
       '5':n('Wav2VecModelLoader',model=m['wav'],base_precision='fp16',load_device='offload_device'),
       '6':n('MultiTalkWav2VecEmbeds',wav2vec_model=['5',0],audio_1=['2',0],normalize_loudness=False,num_frames=frames,fps=25.,audio_scale=1.,audio_cfg_scale=2. if quality=='fast' else 4.,multi_audio_type='para',add_noise_floor=False,smooth_transients=False),
       '7':n('CLIPVisionLoader',clip_name=m['vision']),
       '8':n('WanVideoClipVisionEncode',clip_vision=['7',0],image_1=['1',0],strength_1=1.,crop='center',force_offload=True),
       '9':n('WanVideoTextEncodeCached',model_name=m['text'],precision='bf16',positive_prompt=prompt+' Only the single visible character speaks to the supplied voice. Mouth relaxed and closed during silence. Stable identity.',negative_prompt='talking during silence, extra speaker, extra person, identity change, subtitles, text, watermark, lip flapping',quantization='disabled',use_disk_cache=True,device='gpu'),
       '10':n('WanVideoModelLoader',model=m['model'],base_precision='bf16',quantization='fp8_e4m3fn',load_device='offload_device',attention_mode='sdpa',multitalk_model=['4',0],block_swap_args=['17',0]),
       '11':n('WanVideoImageToVideoMultiTalk',vae=['3',0],width=size[0],height=size[1],frame_window_size=81,motion_frame=9,force_offload=True,colormatch='disabled',start_image=['1',0],tiled_vae=True,clip_embeds=['8',0],mode='infinitetalk',output_path=''),
       '12':n('CayWanVideoSampler',model=['10',0],image_embeds=['11',0],text_embeds=['9',0],multitalk_embeds=['6',0],steps=4 if quality=='fast' else 40 if quality=='high' else 24,cfg=1.,shift=2. if quality=='fast' else 5.,seed=seed,force_offload=True,scheduler='euler',riflex_freq_index=0,start_step=0,end_step=-1),
       '13':n('WanVideoPassImagesFromSamples',samples=['12',0]),
       '14':n('CreateVideo',images=['13',0],fps=25.),
       '15':n('SaveVideo',video=['14',0],filename_prefix=prefix,format='mp4',codec='h264'),
       '17':n('WanVideoBlockSwap',blocks_to_swap=20,vace_blocks_to_swap=0,offload_img_emb=True,offload_txt_emb=True,use_non_blocking=True,prefetch_blocks=1)}
    if quality=='fast':
        g['16']=n('WanVideoLoraSelect',lora=m['lora'],strength=1.,low_mem_load=False,merge_loras=True)
        g['10']['inputs']['lora']=['16',0]
    # Do not silently omit the essential audio path on an incompatible wrapper.
    for key,field in [('10','multitalk_model'),('10','block_swap_args'),('12','multitalk_embeds'),('11','mode')]:
        if field not in g[key]['inputs']:raise ValueError('ComfyUI-WanVideoWrapper unterstützt '+field+' noch nicht. Erweiterung aktualisieren.')
    validate_graph(info,g)
    return g

def validate_graph(info,graph):
    for key,item in graph.items():
        required,optional=fields(info,item['class_type'])
        for field,value in item['inputs'].items():
            if not (isinstance(value,list) and len(value)==2 and str(value[0]) in graph and isinstance(value[1],int)):continue
            origin=graph[str(value[0])]['class_type'];outputs=info[origin].get('output')
            if outputs is None:continue
            expected={**required,**optional}[field][0]
            if value[1]>=len(outputs) or (isinstance(expected,str) and expected!='*' and outputs[value[1]] not in (expected,'*')):
                raise ValueError(f'Unpassender Anschluss: {origin} → {item["class_type"]}.{field}')

def dialogue_window(lines,start,seconds,target):
    """No per-window loudness change and no music; sample-accurate offsets at 24 kHz."""
    from factory_video import ff,file_hash
    rate=24000;count=round(seconds*rate);args=[];filters=[];labels=[]
    for l in lines:
        end=l.get('offset',0)+l['duration'];a=max(start,l.get('offset',0));b=min(start+seconds,end)
        if b<=a:continue
        if file_hash(l['file'])!=l['sha256']:raise RuntimeError('Freigegebene Sprache wurde verändert.')
        idx=len(labels);args+=['-i',l['file']]
        seek=round((a-l.get('offset',0))*rate);length=round((b-a)*rate);delay=round((a-start)*rate)
        filters.append(f'[{idx}:a]aresample={rate},atrim=start_sample={seek}:end_sample={seek+length},asetpts=PTS-STARTPTS,adelay={delay}S:all=1,apad=whole_len={count}[a{idx}]');labels.append(f'[a{idx}]')
    if not labels:args=['-f','lavfi','-i',f'anullsrc=r={rate}:cl=mono:d={seconds}'];filters=['[0:a]anull[out]']
    else:filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=end_sample={count}[out]')
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    ff([*args,'-filter_complex',';'.join(filters),'-map','[out]','-t',seconds,'-ar',rate,'-ac','1','-c:a','pcm_s16le',target])
    return target

def install_wrapper(base):
    """Add the official extension if missing; never reset an existing checkout."""
    import sys,uuid,importlib.metadata as md
    base=Path(base);custom=base/'apps/ComfyUI/custom_nodes';target=custom/'ComfyUI-WanVideoWrapper'
    if target.is_dir():
        print('Vorhandene WanVideo-Erweiterung bleibt erhalten. Fehlende Anschlüsse gegebenenfalls im ComfyUI-Manager aktualisieren.',flush=True)
        return
    custom.mkdir(parents=True,exist_ok=True)
    work=base/'studio/cache'/('WanVideo-Installation-'+uuid.uuid4().hex[:8]);work.parent.mkdir(parents=True,exist_ok=True)
    print('Installiere offizielle WanVideo-Erweiterung: '+WRAPPER_REVISION,flush=True)
    subprocess.run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/kijai/ComfyUI-WanVideoWrapper.git',str(work)],check=True,timeout=600)
    subprocess.run(['git','-C',str(work),'checkout','--detach',WRAPPER_REVISION],check=True,timeout=600)
    constraints=work.parent/'Cay_Comfy_Basisversionen.txt';keep=[]
    for package in ('torch','torchvision','torchaudio','transformers','numpy'):
        try:keep.append(package+'=='+md.version(package))
        except md.PackageNotFoundError:pass
    constraints.write_text('\n'.join(keep)+'\n')
    subprocess.run([sys.executable,'-m','pip','install','--constraint',str(constraints),'-r',str(work/'requirements.txt')],check=True,timeout=1800)
    os.replace(work,target)
    print('Erweiterung installiert. ComfyUI nach Abschluss neu starten.',flush=True)

def setup(base):
    """Public downloads only, immutable revisions, resumable and no inference API."""
    from huggingface_hub import HfApi,hf_hub_download
    base=Path(base);comfy=base/'apps/ComfyUI';api=HfApi();record=comfy/'models/Cay_Animation_Quellen.json'
    manifest=json.loads(record.read_text()) if record.exists() else {}
    if shutil.disk_usage(base).free<60*1024**3:raise RuntimeError('Für die vollständige Einrichtung bitte 60 GB frei halten (Modelle plus Download-Zwischenspeicher).')
    def download(repo,sha,remote,folder):
        manifest.setdefault(repo,{'revision':sha});record.parent.mkdir(parents=True,exist_ok=True)
        tmp_record=record.with_suffix('.partial');tmp_record.write_text(json.dumps(manifest,indent=2));os.replace(tmp_record,record)
        target=comfy/'models'/folder/remote
        if target.is_file() and target.stat().st_size>100000:
            print('Vorhanden: '+target.name,flush=True);return
        print('Lade: '+remote,flush=True)
        # Download straight into the model folder. No duplicate multi-GB copy.
        hf_hub_download(repo,remote,revision=sha,local_dir=comfy/'models'/folder)
    for remote in FAST_NAMES.values():download(FAST_REPO,FAST_REVISION,remote,'loras')
    repo='Kijai/WanVideo_comfy';sha=manifest.get(repo,{}).get('revision') or api.model_info(repo).sha
    files=api.list_repo_files(repo,revision=sha)
    expected=[('diffusion_models',TALK_MODEL),('diffusion_models','Wan2_1-InfiniTetalk-Single_fp16.safetensors'),
              ('vae','Wan2_1_VAE_bf16.safetensors'),('loras','lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors'),
              ('text_encoders','umt5-xxl-enc-bf16.safetensors')]
    for folder,name in expected:
        matches=[p for p in files if Path(p).name==name]
        if len(matches)!=1:raise RuntimeError('Offizielle Modelldatei nicht eindeutig gefunden: '+name+'. Schnellgewichte bleiben gespeichert; keine Ersatzdatei geraten.')
        download(repo,sha,matches[0],folder)
    for repo,remote,folder in [('Kijai/wav2vec2_safetensors','wav2vec2-chinese-base_fp16.safetensors','wav2vec2'),
                              ('Comfy-Org/Wan_2.1_ComfyUI_repackaged','split_files/clip_vision/clip_vision_h.safetensors','clip_vision')]:
        sha=manifest.get(repo,{}).get('revision') or api.model_info(repo).sha;download(repo,sha,remote,folder)
    install_wrapper(base)
    print('EINRICHTUNG BEENDET. ComfyUI neu starten und „Animation prüfen“ öffnen. Danach eine kurze Produktionsprobe.',flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);a=p.parse_args();setup(Path(a.base))
