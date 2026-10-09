"""Allowlisted local video adapter and a reproducible FFmpeg finish."""
import copy,hashlib,json,math,os,subprocess,shutil,time,uuid
from pathlib import Path
from studio_quality_policy import PROFILES, cadence
from studio_resources_options import cpu_options
from wan_text_encoder import choose as choose_text
import speech_check

VIDEO_MODELS={
 'high':('UNETLoader','unet_name','wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors'),
 'low':('UNETLoader','unet_name','wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors'),
 'clip':('CLIPLoader','clip_name','umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
 'vae':('VAELoader','vae_name','wan_2.1_vae.safetensors')}

def video_models(info,comfy=None):
    result={}
    for key,(kind,field,name) in VIDEO_MODELS.items():
        if key=='clip':result[key]=choose_text(info,comfy);continue
        options=info.get(kind,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
        names=[name]
        found=[x for n in names for x in options if x.replace('\\','/').split('/')[-1]==n]
        if not found:raise ValueError('Vorhandenes Videomodell fehlt: '+name)
        result[key]=found[0]
    result['tiled_vae']='VAEDecodeTiled' in info
    from render_studio import fast_models
    try:result['fast_loras']=fast_models(info)
    except ValueError:result['fast_loras']=None
    missing={n['class_type'] for n in motion_graph('x','x',1,'x',result,1).values()}-info.keys()
    if missing:raise ValueError('Video-Nodes fehlen: '+', '.join(sorted(missing)))
    return result

def motion_graph(image,prompt,seed,prefix,models,seconds,quality='balanced'):
    if not .1<=seconds<=5.1:raise ValueError('Ein Bewegungsabschnitt muss höchstens fünf Sekunden dauern.')
    def n(kind,**inputs):return {'class_type':kind,'inputs':inputs}
    frames=4*math.ceil(seconds*16/4)+1
    profile=PROFILES[quality];steps=profile['steps'];split=steps//2
    graph={
      '1':n('LoadImage',image=image),
      '2':n('UNETLoader',unet_name=models['high'],weight_dtype='default'),
      '3':n('UNETLoader',unet_name=models['low'],weight_dtype='default'),
      '4':n('CLIPLoader',clip_name=models['clip'],type='wan',device='default'),
      '5':n('VAELoader',vae_name=models['vae']),
      '6':n('CLIPTextEncode',clip=['4',0],text=prompt),
      '7':n('CLIPTextEncode',clip=['4',0],text='identity changes, changing head shape, duplicate characters, extra limbs, distorted faces, frozen image, slow motion, subtitles, captions, letters, gibberish text, menus, logos, watermark, collage, split screen, panels, scene transitions, zoom through faces, excessive camera shake'),
      '8':n('WanImageToVideo',positive=['6',0],negative=['7',0],vae=['5',0],start_image=['1',0],width=profile['width'],height=profile['height'],length=frames,batch_size=1),
      '9':n('ModelSamplingSD3',model=['2',0],shift=5.0),
      '10':n('ModelSamplingSD3',model=['3',0],shift=5.0),
      '11':n('KSamplerAdvanced',model=['9',0],add_noise='enable',noise_seed=seed,steps=steps,cfg=profile['cfg'],sampler_name='euler',scheduler='simple',positive=['8',0],negative=['8',1],latent_image=['8',2],start_at_step=0,end_at_step=split,return_with_leftover_noise='enable'),
      '12':n('KSamplerAdvanced',model=['10',0],add_noise='disable',noise_seed=0,steps=steps,cfg=profile['cfg'],sampler_name='euler',scheduler='simple',positive=['8',0],negative=['8',1],latent_image=['11',0],start_at_step=split,end_at_step=steps,return_with_leftover_noise='disable'),
      '13':n('VAEDecode',samples=['12',0],vae=['5',0]),
      '14':n('CreateVideo',images=['13',0],fps=16),
      '15':n('SaveVideo',video=['14',0],filename_prefix=prefix,format='mp4',codec='h264')}
    if quality=='fast':
        if not models.get('fast_loras'):raise ValueError('Schnellmodus braucht die beiden Wan-2.2-Lightning-Gewichte. Unter Animation einrichten ergänzen oder bewusst ein anderes Profil wählen.')
        for key,loader,sampling in [('high','2','9'),('low','3','10')]:
            ident='16' if key=='high' else '17'
            graph[ident]=n('LoraLoaderModelOnly',model=[loader,0],lora_name=models['fast_loras'][key],strength_model=1.)
            graph[sampling]['inputs']['model']=[ident,0]
    if models.get('tiled_vae'):graph['13']=n('VAEDecodeTiled',samples=['12',0],vae=['5',0],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)
    return graph

def talk_graph(template,image,audio,prompt,seed,prefix,seconds):
    g=copy.deepcopy(template)
    expected={'1':'LoadImage','2':'LoadAudio','7':'MultiTalkWav2VecEmbeds','11':'WanVideoTextEncodeCached','12':'WanVideoImageToVideoMultiTalk','13':'WanVideoSampler','14':'WanVideoPassImagesFromSamples','15':'CreateVideo','16':'SaveVideo'}
    for key,kind in expected.items():
        if g.get(key,{}).get('class_type')!=kind:raise ValueError('Der vorhandene Sprechworkflow passt nicht zum geprüften Adapter: '+key)
    for item in g.values():
        item.pop('is_changed',None)
    g['1']['inputs']['image']=image;g['2']['inputs']['audio']=audio
    g['7']['inputs'].update(num_frames=4*math.ceil(seconds*25/4)+1,fps=25.0,audio_scale=1.,audio_cfg_scale=4.)
    g['11']['inputs']['positive_prompt']=prompt+' Natural restrained speaking motion synchronized to the supplied audio. Keep identity and texture stable.'
    g['12']['inputs'].update(width=576,height=1024,frame_window_size=81,motion_frame=9,mode='infinitetalk',output_path='',force_offload=True,tiled_vae=True)
    g['13']['inputs'].update(steps=40,cfg=1.,seed=seed,start_step=0,end_step=-1)
    g['15']['inputs']['fps']=25;g['16']['inputs']['filename_prefix']=prefix
    return g

def ff(args,cwd=None):
    # FFmpeg may otherwise report success after a concat demuxer stopped early.
    options=cpu_options()
    r=subprocess.run(['ffmpeg','-nostdin','-y','-xerror','-hide_banner','-loglevel','error','-filter_threads',str(options['filter_threads']),'-filter_complex_threads',str(options['filter_threads']),*map(str,args[:-1]),'-threads',str(options['threads']),str(args[-1])],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1800)
    if r.returncode:raise RuntimeError('FFmpeg: '+r.stderr.decode(errors='replace')[-1600:])

def probe(path):
    r=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(path)],capture_output=True,timeout=20,check=True)
    return json.loads(r.stdout)

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()

def stamp(seconds):
    cs=round(seconds*100);h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'

def prepare(spec):
    """Encode available sections while the GPU produces subsequent animation."""
    folder=Path(spec['folder']);folder.mkdir(parents=True,exist_ok=True);fps=spec['fps'];parts=[];cursor=0;events=[]
    timings={'encode_seconds':0.,'mux_seconds':0.,'cached_parts':0,'lossy_passes':1,'encoder':'libx264','cpu_options':cpu_options()}
    for scene in spec['scenes']:
        if not spec.get('_only_part') and abs(sum(c['seconds'] for c in scene['clips'])-scene['seconds'])>1e-5:raise RuntimeError('Schnittabschnitte passen nicht zur Szenendauer.')
        for line in scene.get('lines') or ([scene['line']] if scene.get('line') else []):
            if file_hash(line['file'])!=line['sha256']:raise RuntimeError('Eine freigegebene Sprachspur wurde verändert.')
            start=cursor+line.get('offset',.15)
            text=line['text_de'].replace('\\','／').replace('{','(').replace('}',')').replace('\n',' ')
            events.append(f'Dialogue: 0,{stamp(start)},{stamp(start+line["duration"])},Default,,0,0,0,,{text}')
        cursor+=scene['seconds']
    ass='''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,DejaVu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00101010,&H50000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,180,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
    (folder/'Untertitel.ass').write_text(ass+'\n'.join(events)+'\n',encoding='utf-8')
    subtitle_hash=file_hash(folder/'Untertitel.ass');scene_offset=0.
    for i,scene in enumerate(spec['scenes']):
        offset=scene_offset;scene_offset+=scene['seconds']
        for j,clip in enumerate(scene['clips']):
            if spec.get('_only_part') is not None and spec['_only_part']!=[i,j]:
                offset+=round(clip['seconds']*fps)/fps;continue
            source=Path(clip['file'])
            if file_hash(source)!=clip['sha256']:raise RuntimeError('Ein Renderclip wurde nachträglich verändert.')
            info=probe(source);native=next(s for s in info['streams'] if s['codec_type']=='video')
            if float(native.get('duration',info['format']['duration']))+.01<clip['seconds']:raise RuntimeError('Renderclip zu kurz. Kein Einfrieren des letzten Bildes.')
            expected_frames=round(clip['seconds']*fps)
            from fractions import Fraction
            native_fps=float(Fraction(native.get('avg_frame_rate','16/1')))
            filtering=('setpts=PTS-STARTPTS,'+cadence(fps,spec.get('smooth',False),native_fps)+
                f',trim=end_frame={expected_frames},setpts=PTS-STARTPTS,'+
                'scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,'+
                f'setpts=PTS+{offset:.9f}/TB,subtitles=Untertitel.ass,setpts=PTS-STARTPTS')
            key=hashlib.sha256(json.dumps([9,clip['sha256'],filtering,subtitle_hash,expected_frames,'libx264-medium-crf17'],sort_keys=True).encode()).hexdigest()
            name=f'Part_{i:03}_{j:03}_{key[:16]}.mp4';dest=folder/name;metadata=dest.with_suffix('.json')
            cached=False
            try:
                saved=json.loads(metadata.read_text())
                cached=saved['key']==key and saved['sha256']==file_hash(dest)
            except (OSError,ValueError,KeyError):pass
            if cached:timings['cached_parts']+=1
            else:
                temp_part=dest.with_name(dest.stem+'.'+uuid.uuid4().hex+'.partial.mp4');started=time.monotonic()
                try:
                    ff(['-i',source,'-an','-vf',filtering,'-frames:v',expected_frames,'-c:v','libx264','-preset','medium','-crf','17','-pix_fmt','yuv420p',temp_part],folder)
                    stream=next(s for s in probe(temp_part)['streams'] if s['codec_type']=='video')
                    if int(stream.get('nb_frames',0))!=expected_frames:raise RuntimeError('Ein Schnittabschnitt ist unvollständig. Erzeugte Animationen bleiben erhalten.')
                    os.replace(temp_part,dest)
                    info={'key':key,'sha256':file_hash(dest)};temp_meta=metadata.with_suffix('.partial.json')
                    temp_meta.write_text(json.dumps(info));os.replace(temp_meta,metadata)
                finally:temp_part.unlink(missing_ok=True)
                timings['encode_seconds']+=time.monotonic()-started
            parts.append(name);offset+=expected_frames/fps
    return {'parts':parts,'seconds':cursor,'performance':timings}


def finish(spec):
    """Complete cached parts and mux the approved audio without resampling video."""
    prepared=prepare(spec)
    folder=Path(spec['folder']);fps=spec['fps'];parts=prepared['parts'];cursor=prepared['seconds'];timings=prepared['performance']
    (folder/'Clips.txt').write_text(''.join("file '"+p+"'\n" for p in parts))
    preview=spec.get('audio_mix')
    if preview:
        audio=Path(preview['file'])
        if file_hash(audio)!=preview['sha256']:raise RuntimeError('Freigegebene Tonmischung verändert.')
    else:
        from factory_audio import mix
        audio=Path(mix(folder/'Ton',spec['scenes'],spec['mood'],spec.get('music'),spec.get('mix')))
    if abs(float(probe(audio)['format']['duration'])-cursor)>.05:raise RuntimeError('Ton und Bild haben unterschiedliche Laufzeiten.')
    args=['-f','concat','-safe','1','-i','Clips.txt','-i',str(audio)]
    out=Path(spec['output']);out.parent.mkdir(parents=True,exist_ok=True);tmp=folder/('Export.'+uuid.uuid4().hex+'.partial.mp4');mux_start=time.monotonic()
    ff([*args,'-map','0:v','-map','1:a','-t',cursor,'-c:v','copy','-c:a','aac','-ar','48000','-b:a','256k','-movflags','+faststart',tmp],folder)
    info=probe(tmp);video=next(x for x in info['streams'] if x['codec_type']=='video')
    if video['width']!=1080 or video['height']!=1920 or abs(float(info['format']['duration'])-cursor)>.12 or int(video.get('nb_frames',0))!=round(cursor*fps):raise RuntimeError('Exportprüfung fehlgeschlagen: Bildlänge oder Bildgröße stimmt nicht.')
    if not any(x['codec_type']=='audio' for x in info['streams']):raise RuntimeError('Export hat keine Tonspur.')
    if float(video.get('duration',info['format']['duration']))+1e-6<spec.get('minimum_seconds',0):raise RuntimeError('Export ist kürzer als die gewählte Mindestdauer. Tonvorschau neu erzeugen.')
    # The exported film must contain every line of the approved mix; a muxed
    # audio stream alone does not prove that speech survived encoding.
    placed=speech_check.placed(spec['scenes'])
    if placed:
        try:
            exported=speech_check.decode(tmp);approved=speech_check.decode(audio)
            report=speech_check.summary(speech_check.compare_export(exported,approved,24000,placed),'export')
            speech_check.write_report(folder/'Exportpruefung.json',report)
            if report['blocking']:raise speech_check.SpeechCheckError(speech_check.message(report,'„Fehlerbericht speichern“ und mitschicken. Die freigegebene Tonvorschau und alle Animationen bleiben erhalten.'),report)
        except BaseException:
            tmp.unlink(missing_ok=True);raise
    timings['mux_seconds']=time.monotonic()-mux_start
    # The Linux workspace and Windows project drive may be different filesystems.
    transfer=out.with_name(out.name+'.'+uuid.uuid4().hex+'.partial')
    try:
        with tmp.open('rb') as source,transfer.open('xb') as target:
            shutil.copyfileobj(source,target,4*1024**2);target.flush();os.fsync(target.fileno())
        if file_hash(transfer)!=file_hash(tmp):raise RuntimeError('Exportkopie konnte nicht bestätigt werden.')
        os.replace(transfer,out)
    finally:transfer.unlink(missing_ok=True);tmp.unlink(missing_ok=True)
    return {'file':str(out),'sha256':file_hash(out),'seconds':cursor,'fps':fps,'performance':timings}
