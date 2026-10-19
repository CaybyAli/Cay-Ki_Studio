"""Measured dialogue, original cartoon accompaniment and deterministic ducking."""
from array import array
from pathlib import Path
import hashlib,json,math,os,random,re,subprocess,sys,wave
from factory_timing import audio_layout,audio_layout_v16
import speech_check
from speech_quality import level_db,performance_key
RATE=24000
TARGET_LUFS=-14  # TikTok/Shorts: phones play quiet mixes thin; measured film before: -23.9 dB mean
def turns(s):
    return s.get('dialogues') or ([{'speaker':s['speaker'],'text':s['dialogue'],'emotion':s.get('emotion','Natürlich'),'pause_after':.18}] if s.get('dialogue') else [])
def layout(episodes,lines,minimum_seconds=None,fps=25,version=17):
    return (audio_layout if version>=17 else audio_layout_v16)(episodes,lines,minimum_seconds,fps)
def write_wav(path,data):
    if not isinstance(data,array):data=array('f',data)
    Path(path).parent.mkdir(parents=True,exist_ok=True);peak=max((abs(x) for x in data),default=1);scale=min(1,.96/max(peak,1e-9));pcm=array('h',(round(max(-.99,min(.99,x*scale))*32767) for x in data))
    if __import__('sys').byteorder!='little':pcm.byteswap()
    with wave.open(str(path),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE);f.writeframes(pcm.tobytes())
def synth_music(path,seconds,mood,variant=0,tempo=1):
    n=math.ceil(seconds*RATE);data=array('f',[0])*n;beat=60/({'playful':112,'gentle':78,'suspense':86,'energetic':126}.get(mood,100)*max(.65,min(1.5,tempo)))
    chords=([48,51,55],[44,48,51],[46,50,53],[43,47,50]) if mood=='suspense' else ([48,52,55],[45,48,52],[41,45,48],[43,47,50])
    def note(start,length,midi,amp,bright=False):
        first=int(start*RATE);freq=440*2**((midi-69)/12)
        for j in range(max(0,min(int(length*RATE),n-first))):
            t=j/RATE;env=min(1,t/.015)*math.exp(-t/(.27 if bright else .7))*min(1,(length-t)/.1)
            data[first+j]+=amp*env*(math.sin(math.tau*freq*t)+(.22*math.sin(math.tau*freq*2*t) if bright else .08*math.sin(math.tau*freq*3*t)))
    k=0
    while k*beat<seconds:
        chord=chords[(k//4+variant)%4];note(k*beat,beat*.95,chord[(k+variant)%3]+12+(variant%3-1 if variant else 0),.10,True)
        if k%2==0:note(k*beat,beat*1.8,chord[0]-12,.10)
        if mood in ('playful','energetic') and k%2:note(k*beat,.12,78,.025,True)
        k+=1
    fade=int(RATE*.5)
    for i in range(min(fade,n)):data[i]*=i/fade;data[n-i-1]*=i/fade
    write_wav(path,data)
def edit_spec(d):
    """0.18 export look (captions, camera, sound bed) only for projects created with it: specs of older
    projects stay byte-identical, so their queued mixes and cached parts keep their keys."""
    return {'edit_policy':d['edit_policy']} if d.get('edit_policy',17)>=18 else {}
SOUND_POLICY=19     # d['sound_policy'] from which the mix levels every line and follows the place (see mix19)
def sound_spec(d):
    """0.19 sound only for projects created with it: older specs stay byte-identical, so their queued mixes
    keep their keys and approved previews their sound."""
    return {'sound_policy':d['sound_policy']} if d.get('sound_policy',0)>=SOUND_POLICY else {}
def place(scene):
    return ' '.join(str(scene.get('location') or '').lower().split())[:120]
def scene_kinds(d,scenes):
    # 0.19: the place travels with each shot, so the ambience follows the location instead of the shot.
    where=bool(sound_spec(d))
    return [{**({'kind':sc.get('kind','line')} if edit_spec(d) else {}),**({'location':place(sc)} if where else {})} for sc in scenes]
# 0.18 sound bed: the room tone of 0.17 measured about -58 dBFS in Cay's film (inaudible, silent
# shots felt dead); his templates keep a continuous bed about 25 dB under the dialogue.
BED_POLICY=18
BED_RMS=.0105       # every scene's ambience at one level (room tone was ~19 dB under wind): with the
                    # default ambience level 0.6 this lands near -40 dBFS RMS after the final loudness pass
def bed_cues(scenes):
    """A short whoosh opens each silent action shot that has no cue of its own."""
    return [dict(s,sound_cues=s.get('sound_cues') or ([{'kind':'whoosh','position':0}] if s.get('kind')=='action' else [])) for s in scenes]
def synth_environment(path,scenes,level=1,bed=False):
    data=array('f',[0])*math.ceil(sum(s['seconds'] for s in scenes)*RATE);rng=random.Random(173);cursor=0
    for s in scenes:
        first=round(cursor*RATE);end=min(len(data),round((cursor+s['seconds'])*RATE));kind=s.get('ambience','room');smooth=0.
        if bed and end>first:
            # 0.18: synthesise this scene at unit level, then bring it to BED_RMS (fades stay).
            part=[0.]*(end-first);sm=0.;raw=[]
            for i in range(first,end):
                t=(i-first)/RATE;sm=.96*sm+.04*rng.uniform(-1,1)
                v=(.005*sm if kind=='room' else .045*sm*(.65+.35*math.sin(t*.8)) if kind=='wind' else .016*rng.uniform(-1,1)+.025*sm if kind=='rain'
                   else .02*sm+(.009*math.sin(math.tau*(1600+150*math.sin(t*7))*t) if t%3<.25 else 0) if kind=='forest'
                   else .02*sm+.009*math.sin(math.tau*65*t)+(.03*rng.uniform(-1,1) if t%.65<.02 else 0) if kind=='train' else 0.)
                raw.append(v)
            rms=math.sqrt(sum(v*v for v in raw)/len(raw)) if raw else 0
            gain=BED_RMS*level/rms if rms>1e-9 else 0
            # Continuous across cuts: fade only where the sound of the place changes (and at both ends).
            index=scenes.index(s);same_before=index>0 and scenes[index-1].get('ambience','room')==kind
            same_after=index+1<len(scenes) and scenes[index+1].get('ambience','room')==kind
            for j,v in enumerate(raw):
                t=j/RATE;fade=min(1,1 if same_before else t/.15,1 if same_after else (s['seconds']-t)/.15)
                data[first+j]+=v*gain*max(0,fade)
            cursor+=s['seconds'];continue
        for i in range(first,end):
            t=(i-first)/RATE;smooth=.96*smooth+.04*rng.uniform(-1,1);v=0.
            if kind=='room':v=.005*smooth
            elif kind=='wind':v=.045*smooth*(.65+.35*math.sin(t*.8))
            elif kind=='rain':v=.016*rng.uniform(-1,1)+.025*smooth
            elif kind=='forest':v=.02*smooth+(.009*math.sin(math.tau*(1600+150*math.sin(t*7))*t) if t%3<.25 else 0)
            elif kind=='train':v=.02*smooth+.009*math.sin(math.tau*65*t)+(.03*rng.uniform(-1,1) if t%.65<.02 else 0)
            data[i]+=v*max(0,min(1,t/.2,(s['seconds']-t)/.2))*level
        cursor+=s['seconds']
    write_wav(path,data)
def synth_effects(path,scenes,level=1):
    data=array('f',[0])*math.ceil(sum(s['seconds'] for s in scenes)*RATE);rng=random.Random(49);cursor=0
    for s in scenes:
        for cue in s.get('sound_cues',[]):
            kind=cue['kind'];start=cursor+min(s['seconds']-.08,max(0,cue['position']*s['seconds']));duration={'magic':.8,'impact':.22,'whoosh':.5,'footstep':.2,'door':.5,'page':.35,'bell':1.,'splash':.6}[kind];first=round(start*RATE)
            for j in range(min(int(duration*RATE),len(data)-first)):
                t=j/RATE;env=math.sin(math.pi*t/duration)**.5;noise=rng.uniform(-1,1)
                if kind=='magic':v=.15*math.sin(math.tau*(660*t+700*t*t))*math.exp(-t*2)+.035*math.sin(math.tau*1320*t)
                elif kind=='bell':v=.14*(math.sin(math.tau*880*t)+.3*math.sin(math.tau*1320*t))*math.exp(-t*4)
                elif kind in ('impact','footstep','door'):v=(.2*math.sin(math.tau*90*t)+.1*noise)*math.exp(-t*25)
                elif kind=='splash':v=.1*noise*math.exp(-t*5)+.05*math.sin(math.tau*(360*t-100*t*t))
                else:v=(.10 if kind=='whoosh' else .045)*noise*env
                data[first+j]+=v*env*level
        cursor+=s['seconds']
    write_wav(path,data)
# FFmpeg's loudnorm shifts its output timestamps. Cutting by time (-t, atrim)
# then loses the end whenever the length is not whole tenths: 60.12 s came out
# as 60.04 s, "Tonmischung unvollständig". Since 0.16 lengths are whole video
# frames. Renumber timestamps from the sample count, then cut exactly.
def exact(chain,duration):
    return f'apad=pad_dur=0.5,{chain},asetpts=N/SR/TB,atrim=duration={duration}'
def ff(args,cwd):
    r=subprocess.run(['ffmpeg','-nostdin','-y','-v','error',*map(str,args)],cwd=cwd,capture_output=True,timeout=600)
    if r.returncode:raise RuntimeError('Tonmischung: '+r.stderr.decode(errors='replace')[-1500:])
def duck_music(source,target,intervals,low=.28,attack=.08,release=.28):
    with wave.open(str(source)) as w:
        if w.getframerate()!=RATE or w.getnchannels()!=1 or w.getsampwidth()!=2:raise RuntimeError('Ungültiges Musikformat.')
        data=array('h',w.readframes(w.getnframes()))
    if __import__('sys').byteorder!='little':data.byteswap()
    envelope=array('f',[1])*len(data)
    for start,end in intervals:
        for i in range(max(0,int((start-attack)*RATE)),min(len(data),math.ceil((end+release)*RATE))):
            t=i/RATE;g=(1-(1-low)*(t-start+attack)/attack) if t<start else (low if t<=end else low+(1-low)*(t-end)/release);envelope[i]=min(envelope[i],max(low,min(1,g)))
    write_wav(target,(v/32768*g for v,g in zip(data,envelope)))
CLEAR_DB=10.        # a masked line gets the bed this far under it (speech_check: masked < 3, crowded < 8)
def clear_lines(stems,entries,attack=.08,release=.28):
    """Lower music, ambience and effects under each masked line until the voice is CLEAR_DB above them.
    Returns {key: dB lowered}. The speech check compares the same stems, so it sees the change."""
    lowered={}
    for path in stems:
        data,rate=speech_check.read_wav(path);out=array('f',(v/32767 for v in data))
        for e in entries:
            lower=min(40.,CLEAR_DB-float(e.get('margin_db',0))+1);gain=10**(-lower/20);start=e['start'];end=start+e['seconds']
            lowered[e['key'] or e['label']]=round(lower,1)
            for i in range(max(0,int((start-attack)*rate)),min(len(out),math.ceil((end+release)*rate))):
                t=i/rate;ramp=(t-start+attack)/attack if t<start else 1 if t<=end else 1-(t-end)/release
                out[i]*=1-(1-gain)*max(0.,min(1.,ramp))
        write_wav(path,out)
    return lowered
def mix(folder,scenes,mood,music=None,settings=None,policy=17,sound=0):
    if int(sound or 0)>=SOUND_POLICY:return mix19(folder,scenes,mood,music,settings)
    bed=int(policy)>=BED_POLICY
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);settings={'music_mode':'uploaded' if music else 'auto','music_level':1.,'effects_level':1.,'ambience_level':1.,**(settings or {})};duration=sum(s['seconds'] for s in scenes);cursor=0.;args=[];filters=[];labels=[];index=0;intervals=[]
    for s in scenes:
        for l in s.get('lines') or ([s['line']] if s.get('line') else []):
            p=Path(l['file'])
            if hashlib.sha256(p.read_bytes()).hexdigest()!=l['sha256']:raise RuntimeError('Sprachspur wurde verändert.')
            start=cursor+l.get('offset',.15)
            if start+l['duration']>cursor+s['seconds']+.03:raise RuntimeError('Dialog passt nicht zur Szenendauer.')
            # Shouts stand out, whispers sit lower (speech_quality.LEVEL_DB).
            gain=level_db(l.get('emotion',''))
            args+=['-i',str(p)];filters.append(f'[{index}:a]highpass=f=55,aresample=24000,volume={gain:+.1f}dB,adelay={round(start*1000)}:all=1[d{index}]');labels.append(f'[d{index}]');index+=1;intervals.append((start,start+l['duration']))
        cursor+=s['seconds']
    dialogue=folder/'Dialogschnitt.wav'
    if labels:
        # Pad each delayed voice before amix.  Padding the result after
        # loudnorm can make FFmpeg's filter graph emit an entirely silent
        # stream even though every individual voice file is valid.
        padded=[]
        for label in labels:
            src=label[1:-1]
            padded_label=f'[vp{len(padded)}]'
            filters.append(f'{label}apad=whole_dur={duration}{padded_label}')
            padded.append(padded_label)
        filters.append(''.join(padded)+f'amix=inputs={len(padded)}:normalize=0:duration=longest[voice]')
    else:args+=['-f','lavfi','-i',f'anullsrc=r=24000:cl=mono:d={duration}'];filters.append(f'[{index}:a]anull[voice]')
    # Float until loudnorm: +2.5 dB on a shouted line must not clip in 16 bit.
    ff([*args,'-filter_complex',';'.join(filters),'-map','[voice]','-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_f32le' if labels else 'pcm_s16le',dialogue],folder)
    if labels:
        # Normalize the complete performance, retaining differences between
        # whispering and emphatic lines. A separate pass avoids amix buffering.
        normalized_voice=folder/'Dialog_Normalisiert.wav'
        # Gentle broadcast-style levelling: rumble off, soft compression, then loudness.
        ff(['-i',dialogue,'-af','highpass=f=70,acompressor=threshold=-20dB:ratio=2:attack=8:release=160:makeup=1.5,'+exact('loudnorm=I=-18:TP=-2.5:LRA=9,aresample=24000',duration),'-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_s16le',normalized_voice],folder)
        os.replace(normalized_voice,dialogue)
    # A successful FFmpeg exit is not enough here: an invalid filter graph can
    # still produce a full-length silent dialogue file. Catch that before the
    # user can approve a preview that would export without voices.
    with wave.open(str(dialogue)) as stream:
        samples=array('h',stream.readframes(stream.getnframes()))
    dialogue_peak=max((abs(x) for x in samples),default=0)
    dialogue_rms=math.sqrt(sum(x*x for x in samples)/len(samples)) if samples else 0
    if labels and (dialogue_peak<500 or dialogue_rms<30):
        raise RuntimeError('Die Dialogspur ist stumm. Tonvorschau wurde nicht freigegeben; Stimmen bitte erneut erzeugen.')
    if settings['music_mode']=='uploaded' and not music:raise RuntimeError('Keine eigene Musikdatei vorhanden.')
    if music and settings['music_mode']=='uploaded':
        path=Path(music['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=music['sha256']:raise RuntimeError('Musikdatei wurde verändert.')
        args=['-stream_loop','-1','-i',str(path)]
    elif settings['music_mode']=='off':args=['-f','lavfi','-i',f'anullsrc=r=24000:cl=mono:d={duration}']
    else:path=folder/'Musik.wav';synth_music(path,duration,mood,settings.get('music_variant',0),settings.get('tempo',1));args=['-i',str(path)]
    gain=0 if settings['music_mode']=='off' else settings['music_level'];normalized=folder/'Musik_Normalisiert.wav';ducked=folder/'Musik_Dialogabsenkung.wav'
    ff([*args,'-af',exact('loudnorm=I=-24:TP=-5:LRA=7,aresample=24000',duration)+f',volume={gain},afade=t=out:st={max(0,duration-.5)}:d=0.5','-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_s16le',normalized],folder);duck_music(normalized,ducked,intervals)
    ambience=folder/'Umgebung.wav';effects=folder/'Effekte.wav';synth_environment(ambience,scenes,settings['ambience_level'],bed);synth_effects(effects,bed_cues(scenes) if bed else scenes,settings['effects_level'])
    args=['-i',str(dialogue),'-i',str(ducked),'-i',str(ambience),'-i',str(effects)];graph=f'[0:a][1:a][2:a][3:a]amix=inputs=4:normalize=0:duration=longest,alimiter=limit=0.94:level=0:latency=1,atrim=duration={duration},'+exact(f'loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11,aresample=48000',duration)+'[sound]';target=folder/'Tonmischung.wav';temp=folder/'Tonmischung.partial.wav'
    stems=(ducked,ambience,effects);cleared={}
    for attempt in range(3):
        ff([*args,'-filter_complex',graph,'-map','[sound]','-t',duration,'-ac','2','-c:a','pcm_s16le',temp],folder)
        with wave.open(str(temp)) as w:
            if abs(w.getnframes()/w.getframerate()-duration)>.03:raise RuntimeError('Tonmischung unvollständig; keine Freigabe.')
        # Every planned line must be audible on its own, not only the track as a
        # whole. The report is written before blocking so the retake knows which
        # lines to speak again; unaffected lines keep their cached takes.
        entries=speech_check.check_lines(samples,RATE,speech_check.placed(scenes),tuple(speech_check.read_wav(p)[0] for p in stems))
        # Cay 0.18.1: a quiet line under an effect or the music ("übertönen die Stimme") came back after every
        # retake, because a new take of the same line does not make the bed quieter. Lower the bed under just
        # that line instead. Mixes without a masked line stay byte-identical.
        masked=[e for e in entries if e['status']=='überdeckt']
        if not masked or attempt==2:break
        for key,lower in clear_lines(stems,masked).items():cleared[key]=round(cleared.get(key,0)+lower,1)
    for e in entries:
        lowered=cleared.get(e['key'] or e['label'])
        if lowered and not e['blocking']:e.update(cleared_db=lowered,note=(e['note']+'; ' if e['note'] else '')+f'Hintergrund hier um {lowered} dB abgesenkt')
        if lowered and e['status']=='ok':e['status']='abgesenkt'
    report=speech_check.summary(entries,'mix')
    speech_check.write_report(folder/'Sprachpruefung.json',report)
    if report['blocking']:
        temp.unlink(missing_ok=True)
        raise speech_check.SpeechCheckError(speech_check.message(report,'„Produktion fortsetzen“ spricht nur diese Beiträge neu ein. Bleibt eine Zeile stumm, ihren Text oder die Stimme der Figur ändern.'),report)
    os.replace(temp,target);(folder/'Tonbericht.json').write_text(json.dumps({'seconds':duration,'lines':len(intervals),'music_mode':settings['music_mode'],'effects':sum(len(s.get('sound_cues',[])) for s in scenes),'dialogue_peak':dialogue_peak,'dialogue_rms':round(dialogue_rms,2),'speech_check':{k:report[k] for k in ('policy','checked','blocking','warnings')},'speech_warnings':[e['label']+' – '+e['note'] for e in report['lines'] if e['status']!='ok']},ensure_ascii=False));return str(target)

# 0.19 sound (projects created with sound_policy 19; the code above stays the mix of every older project).
# Cay's 0.18 films, measured in the 0.19 diagnosis: a white-noise whoosh opened every silent action shot; the
# single-pass loudnorm lifted music, room tone and hiss between the lines by up to 12 dB ("Rauschen kommt und
# geht", music only 3-5 LU under the voices); a quiet reference voice made a quiet figure (Patrick 2.4 LU under
# the others, speech check stops); the hiss of noisy references came and went with every line.
DIALOGUE_LUFS=-18.  # dialogue stem after its one measured gain; music and ambience are set relative to it
SPEECH_LUFS=-20.    # active speech loudness of every take (K-weighted) before its emotion offset
# Delivery offsets after levelling: a shout clearly louder, a whisper softer but well above the music.
LEVEL_DB_19={'shout':3.,'angry':2.,'panic':2.,'excited':1.5,'triumph':1.,'threat':-1.,'pleading':-1.,'afraid':-1.,'sad':-2.,'whisper':-5.}
MAX_BOOST,MAX_CUT=24.,12.
PEAK_OVER_SPEECH=13.  # peak ceiling of a take over its loudness: a -14 LUFS master leaves about 13 dB
QUIET_TAKE_DB=12.   # a take lifted more than this is reported: the reference voice is quiet (or noisy)
DENOISE_NR=15       # afftdn reduction in dB; above ~20 real sibilants turn watery
MUSIC_LUFS=-26.     # music at level 1.0 between lines: 8 LU under the dialogue (11 LU at the default 0.7)
DUCK_DB,DUCK_ATTACK,DUCK_RELEASE,DUCK_BRIDGE=7.,.25,.7,1.   # gentle dip; stays down across short gaps
FINAL_LIMIT=-2.     # dBFS sample peak per channel at 48 kHz; lowered once more if the true peak still exceeds
TRUE_PEAK=-1.       # dBTP
AMBIENCE_DBFS={'room':-47.,'forest':-43.,'wind':-41.,'rain':-41.,'train':-41.}   # bed RMS at level 1.0
AMBIENCE_FADE=.4    # crossfade where the location changes, nowhere else
def r128(source,chain='',data=None):
    """Run FFmpeg with an EBU R128 meter (ebur128) at the end of chain. Returns integrated loudness (LUFS,
    silence reads -70), true peak (dBTP) and, for float samples piped in (data), the processed samples."""
    out=['-f','f32le','-'] if data is not None else ['-f','null','-']
    r=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-nostats',*source,'-af',chain+'ebur128=peak=true',*out],input=None if data is None else f32_bytes(data),capture_output=True,timeout=600)
    text=r.stderr.decode(errors='replace');i=re.findall(r'\bI:\s+(-?[\d.]+|-inf) LUFS',text);p=re.findall(r'\bPeak:\s+(-?[\d.]+|-inf) dBFS',text)
    if r.returncode or not i:raise RuntimeError('Tonmischung: Lautheit nicht messbar. '+text[-600:])
    samples=array('f')
    if data is not None:
        samples.frombytes(r.stdout[:len(r.stdout)//4*4])
        if sys.byteorder!='little':samples.byteswap()
    return max(-70.,float(i[-1])),(float(p[-1]) if p else 0.),samples
def loudness(path):
    return r128(['-i',str(path)])[:2]
PIPE=['-f','f32le','-ar',str(RATE),'-ac','1','-i','pipe:']
def read_f32(path):
    r=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-map','0:a:0','-ac','1','-ar',str(RATE),'-f','f32le','-'],capture_output=True,timeout=600)
    if r.returncode:raise RuntimeError('Sprachspur nicht lesbar: '+r.stderr.decode(errors='replace')[-600:])
    data=array('f');data.frombytes(r.stdout[:len(r.stdout)//4*4])
    if sys.byteorder!='little':data.byteswap()
    return data
def f32_bytes(data):
    data=array('f',data)
    if sys.byteorder!='little':data.byteswap()
    return data.tobytes()
def power_db(values):
    return 10*math.log10(max(sum(v*v for v in values)/max(1,len(values)),1e-20))
def kweight(data):
    """BS.1770 K-weighting (shelf plus high-pass, coefficients for RATE) by FFmpeg's biquad: a deep voice and a
    bright one at the same RMS are not equally loud."""
    k=math.tan(math.pi*1681.974450955533/RATE);vh=10**(3.999843853973347/20);vb=vh**.4996667741545416;q=.7071752369554196;a0=1+k/q+k*k
    shelf=(vh+vb*k/q+k*k)/a0,2*(k*k-vh)/a0,(vh-vb*k/q+k*k)/a0,1,2*(k*k-1)/a0,(1-k/q+k*k)/a0
    k=math.tan(math.pi*38.13547087602444/RATE);q=.5003270373238773;a0=1+k/q+k*k;high=1,-2,1,1,2*(k*k-1)/a0,(1-k/q+k*k)/a0
    graph=','.join('biquad='+':'.join(f'{n}={v:.12g}' for n,v in zip(('b0','b1','b2','a0','a1','a2'),c)) for c in (shelf,high))
    r=subprocess.run(['ffmpeg','-nostdin','-v','error','-f','f32le','-ar',str(RATE),'-ac','1','-i','pipe:','-af',graph,'-f','f32le','-'],input=f32_bytes(data),capture_output=True,timeout=300)
    if r.returncode:raise RuntimeError('Tonmischung: '+r.stderr.decode(errors='replace')[-600:])
    out=array('f');out.frombytes(r.stdout[:len(r.stdout)//4*4])
    if sys.byteorder!='little':out.byteswap()
    return out
def active_level(fr):
    """Active speech level (dB re full scale) from 10 ms RMS frames: the frames within 25 dB of the loud end
    (98th percentile, so a single click does not set the reference). None for a take without sound.
    On K-weighted frames, minus 0.691 dB, this is the loudness (LUFS) of the spoken part."""
    loud=sorted(fr)[int(.98*(len(fr)-1))] if fr else 0.
    if loud<=1e-6:return None
    return power_db([min(v,2*loud) for v in fr if v>=loud*10**(-25/20)])
def noise_window(fr,active):
    """Frames (first, last) to learn this take's hiss from: the 50 ms lead-in finish_voice leaves before the
    first word when it is as quiet as the take's floor, else the quietest 50 ms pause. None for a clean take
    (or digital silence) and for a take without any pause."""
    if active is None or len(fr)<12:return None
    floor=power_db(sorted(fr)[:max(1,len(fr)//10)])
    if floor<-80 or floor>active-15:return None
    if power_db(fr[1:6])<=floor+6:return 1,6,'Vorlauf'
    level,i=min((power_db(fr[i:i+5]),i) for i in range(1,len(fr)-5))
    return (i,i+5,'Pause') if level<=floor+6 else None
def run_f32(graph,data):
    """Float samples through an FFmpeg filter chain at RATE (mono); None if FFmpeg fails."""
    try:r=subprocess.run(['ffmpeg','-nostdin','-v','error',*PIPE,'-af',graph,'-f','f32le','-'],input=f32_bytes(data),capture_output=True,timeout=300)
    except (OSError,subprocess.SubprocessError):return None
    out=array('f');out.frombytes(r.stdout[:len(r.stdout)//4*4])
    if sys.byteorder!='little':out.byteswap()
    return None if r.returncode else out
DENOISE_PAD=.25     # tail played after a take so afftdn's delay does not cut its end
afftdn_measured=[]   # per process: [delay in samples or None]
def afftdn_delay():
    """afftdn delays its output (25 ms in FFmpeg 6.1) and keeps the length; uncorrected, every denoised line
    came 25 ms late. Measured once per process: energy centre of a tone burst before and after. None if odd."""
    if not afftdn_measured:
        n=RATE;x=array('f',[0.])*n;size=int(.05*RATE);rng=random.Random(5)
        for i in range(n):x[i]=.001*rng.uniform(-1,1)
        for j in range(size):x[n//2+j]+=.5*math.sin(math.tau*1000*j/RATE)*math.sin(math.pi*j/size)**2
        y=run_f32(f'afftdn=nr={DENOISE_NR}:nf=-50',x)
        def centre(v):
            part=range(n//2-RATE//10,n//2+RATE//5);return sum(i*v[i]*v[i] for i in part)/max(1e-12,sum(v[i]*v[i] for i in part))
        delay=round(centre(y)-centre(x)) if y is not None and len(y)==n else -1
        afftdn_measured.append(delay if 0<=delay<DENOISE_PAD*RATE-RATE//50 else None)
    return afftdn_measured[0]
def denoise(data,first,last):
    """Gentle FFT denoise (afftdn) with the noise profile learnt from frames first..last. That stretch is played
    first (mirrored to 0.1 s), sampled and cut off again together with afftdn's own delay, so the take keeps its
    exact length and timing. Returns None when FFmpeg fails; the caller then mixes the take as it is."""
    delay=afftdn_delay()
    if delay is None:return None
    hop=round(RATE*speech_check.HOP);seg=data[first*hop:last*hop];pre=array('f')
    while len(pre)<.1*RATE:pre.extend(seg if len(pre)//len(seg)%2==0 else seg[::-1])
    floor=max(-80.,min(-20.,power_db(seg)+6))   # afftdn only reduces noise under its floor setting
    out=run_f32(f"asendcmd=c='0 afftdn sn start;{len(pre)/RATE:.4f} afftdn sn stop',afftdn=nr={DENOISE_NR}:nf={floor:.1f}",pre+data+array('f',[0.])*round(DENOISE_PAD*RATE))
    if out is None or len(out)!=len(pre)+len(data)+round(DENOISE_PAD*RATE):return None
    out=out[len(pre)+delay:len(pre)+delay+len(data)]
    return out if all(math.isfinite(v) for v in out) else None
def speech_loudness(data,measured):
    """Loudness of the spoken part: BS.1770 gating drops the pauses; a take under 0.5 s has too few blocks,
    so its active K-weighted frames decide."""
    if len(data)>=RATE//2 and measured>-70:return measured
    level=active_level(speech_check.frames(kweight(data),RATE,0,len(data)/RATE));return None if level is None else level-.691
def prepare_take(line):
    """Read one take, denoise it gently and measure the loudness of its speech. The line file stays untouched."""
    data=read_f32(line['file'])
    fr=speech_check.frames(data,RATE,0,len(data)/RATE);active=active_level(fr);window=noise_window(fr,active);status='sauber'
    if window:
        cleaned=denoise(data,window[0],window[1]);status='Fehler'
        if cleaned is not None:
            after=speech_check.frames(cleaned,RATE,0,len(cleaned)/RATE);level=active_level(after)
            # The voice must come through unchanged (level, first and last word in the same 10 ms frame, give
            # or take one); otherwise mix the take as it is.
            def edges(values):
                loud=[i for i,v in enumerate(values) if v>=10**((active-20)/20)];return (loud[0],loud[-1]) if loud else (-9,-9)
            if level is not None and abs(level-active)<=1 and all(abs(a-b)<=1 for a,b in zip(edges(fr),edges(after))):data,status=cleaned,window[2]
            else:status='verworfen'
    elif active is not None and len(fr)>=12:status='ohne' if power_db(sorted(fr)[:max(1,len(fr)//10)])>=-80 else 'sauber'
    loud=None if active is None else speech_loudness(data,r128(PIPE,'',data)[0])
    goal=SPEECH_LUFS+LEVEL_DB_19.get(performance_key(line.get('emotion','')),0.)
    return {'data':data,'loud':loud,'goal':goal,'level':None if loud is None else round(loud,1),'denoise':status,'label':speech_check.label(line)}
def shape_take(take,peak_over,path):
    """Level a prepared take to its goal and limit its peaks to peak_over dB above that loudness. Peaks are
    controlled per take, so the final limiter has (almost) nothing to do: it took up to 1.4 dB more off deep
    voices than off bright ones and lowered the bed under every loud word. The small rest after the limit is a
    constant gain, at most +0.5 dB so the peaks stay under the ceiling. Writes raw float with the exact length."""
    data,goal=take['data'],take['goal'];gain=correction=0.
    if take['loud'] is not None:
        gain=first=max(-MAX_CUT,min(MAX_BOOST,goal-take['loud']));tried=[]
        for attempt in range(4):
            chain=(f'apad=pad_dur=0.1,highpass=f=60:poles=1,volume={gain:+.2f}dB,alimiter=limit={10**((goal+peak_over)/20):.5f}:release=80:level=0:latency=1,'
                   f'asetpts=N/SR/TB,atrim=end_sample={len(take["data"])},')
            measured,_,data=r128(PIPE,chain,take['data'])
            if len(data)!=len(take['data']):raise RuntimeError('Tonmischung: Sprachspur nach der Pegelung unvollständig.')
            after=speech_loudness(data,measured)
            if after is None:correction=0.;break
            correction=goal-after;tried.append((gain,after))
            if abs(correction)<=.3:break
            # The limit takes a little off: more gain, peaks stay at the ceiling. Secant step, bounded.
            slope=(tried[-1][1]-tried[-2][1])/(tried[-1][0]-tried[-2][0]) if len(tried)>1 and tried[-1][0]!=tried[-2][0] else 1.
            step=max(-MAX_CUT,min(MAX_BOOST,first+8,gain+correction/max(.25,min(1.,slope))))
            if abs(step-gain)<.05:break
            gain=step
        correction=max(-3.,min(.5,correction))
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(f32_bytes(data))
    take.update(gain=round(gain+correction,2),correction=round(correction,2))
    return take
def places(scenes):
    """Consecutive shots of one location share one ambience bed; the place sounds like its most frequent kind."""
    groups=[];cursor=0.
    for s in scenes:
        kind=s.get('ambience') or 'room';where=s.get('location') or '#'+kind
        if groups and groups[-1]['location']==where:groups[-1]['kinds'].append(kind);groups[-1]['end']=cursor+s['seconds']
        else:groups.append({'location':where,'start':cursor,'end':cursor+s['seconds'],'kinds':[kind]})
        cursor+=s['seconds']
    for g in groups:g['kind']=max(g['kinds'],key=g['kinds'].count)
    return groups
def unit(x):
    rms=math.sqrt(sum(v*v for v in x)/len(x)) if x else 0
    return [v/rms for v in x] if rms>1e-12 else x
def bed_texture(kind,n,rng):
    """Band-limited textures at unit RMS: no white noise, nothing that hisses on a phone speaker."""
    def lowpass(fc,hp=.99,mod=None):
        out=[0.]*n;a1=a2=dc=prev=0.;k=1-math.exp(-math.tau*fc/RATE)
        for i in range(n):
            c=k if mod is None else 1-math.exp(-math.tau*fc*mod[i]/RATE)
            a1+=c*(rng.uniform(-1,1)-a1);a2+=c*(a1-a2);dc=hp*(dc+a2-prev);prev=a2;out[i]=dc
        return unit(out)
    def slow(step,lo,hi):   # smooth random control curve (cosine between points every step seconds)
        pts=[rng.uniform(lo,hi) for _ in range(int(n/RATE/step)+3)];out=[0.]*n
        for i in range(n):
            t=i/RATE/step;j=int(t);u=(1-math.cos(math.pi*(t-j)))/2;out[i]=pts[j]*(1-u)+pts[j+1]*u
        return out
    def blips(rate,freqs,taus,length):   # sparse damped sines (drops, clacks, chirps)
        out=[0.]*n;t=rng.expovariate(rate)
        while t<n/RATE:
            f=rng.uniform(*freqs);tau=rng.uniform(*taus);amp=rng.uniform(.3,1);start=int(t*RATE)
            for j in range(min(int(length*RATE),n-start)):out[start+j]+=amp*math.exp(-j/RATE/tau)*math.sin(math.tau*f*j/RATE)
            t+=rng.expovariate(rate)
        return out
    if kind=='wind':
        gust=slow(1.3,.2,1.);base=lowpass(1.,.975,[180+520*g for g in gust])
        return unit([v*(.35+.65*g) for v,g in zip(base,gust)])
    if kind=='rain':
        bed=lowpass(1500,.95);drops=unit(blips(28,(900,2800),(.003,.007),.035)) if n else []
        return unit([b+.45*d for b,d in zip(bed,drops)])
    if kind=='forest':
        bed=lowpass(400);birds=[0.]*n;t=rng.uniform(.8,2.5)
        while t<n/RATE-.5:
            f0=rng.uniform(2600,3800)
            for note in range(rng.randint(2,4)):
                start=int((t+note*.12)*RATE)
                for j in range(min(int(.07*RATE),n-start)):
                    u=j/(.07*RATE);birds[start+j]+=math.sin(math.pi*u)*math.sin(math.tau*(f0-600*u)*j/RATE)
            t+=rng.uniform(2.5,6)
        return unit([b+.08*c for b,c in zip(bed,birds)])
    if kind=='train':
        rumble=lowpass(110,.995);clack=[0.]*n;t=0.
        while t<n/RATE:
            for at in (t,t+.11):
                start=int(at*RATE)
                for j in range(max(0,min(int(.12*RATE),n-start))):clack[start+j]+=math.exp(-j/RATE/.025)*math.sin(math.tau*150*j/RATE)
            t+=.72
        return unit([r+.25*math.sin(math.tau*52*i/RATE)+.35*c for i,(r,c) in enumerate(zip(rumble,clack))])
    return lowpass(230)   # room tone: about 40-400 Hz
def synth_ambience(path,scenes,level=1.):
    """0.19 bed: one continuous texture per location, crossfaded (equal power) only where the location
    changes; 'none' stays silent. Returns the places for the sound report."""
    total=math.ceil(sum(s['seconds'] for s in scenes)*RATE);data=array('f',[0])*total;rng=random.Random(173);fade=round(AMBIENCE_FADE*RATE);edge=round(.3*RATE)
    groups=places(scenes)
    for g in groups:
        if g['kind']=='none' or level<=0:continue
        a=max(0,round(g['start']*RATE)-fade//2);b=min(total,round(g['end']*RATE)+fade//2)
        if b<=a:continue
        x=bed_texture(g['kind'] if g['kind'] in AMBIENCE_DBFS else 'room',b-a,rng);gain=10**(AMBIENCE_DBFS.get(g['kind'],AMBIENCE_DBFS['room'])/20)*level
        fin=fade if a>0 else edge;fout=fade if b<total else edge
        for j,v in enumerate(x):
            e=min(1.,(j+.5)/fin,(b-a-j-.5)/fout);data[a+j]+=v*gain*math.sin(math.pi/2*max(0.,e))
    write_wav(path,data)
    return [{'location':g['location'],'kind':g['kind'],'start':round(g['start'],3),'seconds':round(g['end']-g['start'],3)} for g in groups]
def bridged(intervals,gap=DUCK_BRIDGE):
    out=[]
    for start,end in sorted(intervals):
        if out and start-out[-1][1]<gap:out[-1]=(out[-1][0],max(out[-1][1],end))
        else:out.append((start,end))
    return out
def mix19(folder,scenes,mood,music=None,settings=None):
    """Mix of sound policy 19: every take denoised gently and levelled on its own, measured linear stages
    (dialogue, then one constant gain on the whole mix to TARGET_LUFS with a peak limiter that has next to
    nothing to do), music well under the voices with a gentle dip, one ambience bed per location, effects only
    where the plan asks for one. Writes the same files and reports as mix(), plus levels per line."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);settings={'music_mode':'uploaded' if music else 'auto','music_level':1.,'effects_level':1.,'ambience_level':1.,**(settings or {})}
    duration=sum(s['seconds'] for s in scenes);cursor=0.;placed=[];takes={};intervals=[]
    for s in scenes:
        for l in s.get('lines') or ([s['line']] if s.get('line') else []):
            p=Path(l['file'])
            if hashlib.sha256(p.read_bytes()).hexdigest()!=l['sha256']:raise RuntimeError('Sprachspur wurde verändert.')
            start=cursor+l.get('offset',.15)
            if start+l['duration']>cursor+s['seconds']+.03:raise RuntimeError('Dialog passt nicht zur Szenendauer.')
            key=l.get('key') or speech_check.label(l);takes[key]=prepare_take(l);placed.append((start,key));intervals.append((start,start+l['duration']))
        cursor+=s['seconds']
    dialogue=folder/'Dialogschnitt.wav';raw=folder/'Dialog_roh.wav'
    def voices(peak_over):
        """Dialogue stem: every take shaped and placed, then one measured gain to DIALOGUE_LUFS. Returns the
        gain and the true peak after it."""
        args=[];filters=[];gain=0.;peak=-70.
        for i,(start,key) in enumerate(placed):
            path=folder/'Zeilen'/f'{i:03}.f32';take=shape_take(takes[key],peak_over,path);args+=['-f','f32le','-ar',str(RATE),'-ac','1','-i',str(path)]
            filters.append(f'[{i}:a]volume={take["correction"]:+.2f}dB,adelay={round(start*1000)}:all=1,apad=whole_dur={duration}[d{i}]')
        if placed:filters.append(''.join(f'[d{i}]' for i in range(len(placed)))+f'amix=inputs={len(placed)}:normalize=0:duration=longest[voice]')
        else:args+=['-f','lavfi','-i',f'anullsrc=r=24000:cl=mono:d={duration}'];filters.append('[0:a]anull[voice]')
        ff([*args,'-filter_complex',';'.join(filters),'-map','[voice]','-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_f32le',raw],folder)
        if placed:
            measured,peak=loudness(raw);gain=max(-20.,min(20.,DIALOGUE_LUFS-measured)) if measured>-70 else 0.;peak+=gain
        # One constant gain for the whole dialogue (the takes are level already); peaks caught for 16 bit.
        ff(['-i',raw,'-af',exact(f'volume={gain:+.2f}dB,alimiter=limit=0.891:level=0:latency=1',duration),'-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_s16le',dialogue],folder)
        raw.unlink(missing_ok=True)
        for path in (folder/'Zeilen').glob('*.f32'):path.unlink()
        return gain,peak
    if settings['music_mode']=='uploaded' and not music:raise RuntimeError('Keine eigene Musikdatei vorhanden.')
    if music and settings['music_mode']=='uploaded':
        path=Path(music['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=music['sha256']:raise RuntimeError('Musikdatei wurde verändert.')
        args=['-stream_loop','-1','-i',str(path)]
    elif settings['music_mode']=='off':args=['-f','lavfi','-i',f'anullsrc=r=24000:cl=mono:d={duration}']
    else:path=folder/'Musik.wav';synth_music(path,duration,mood,settings.get('music_variant',0),settings.get('tempo',1));args=['-i',str(path)]
    source=folder/'Musik_roh.wav';normalized=folder/'Musik_Normalisiert.wav';ducked=folder/'Musik_Dialogabsenkung.wav'
    ff([*args,'-af',exact('aresample=24000',duration),'-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_f32le',source],folder)
    level=0. if settings['music_mode']=='off' else float(settings['music_level']);measured=loudness(source)[0]
    music_gain=min(20.,MUSIC_LUFS-measured) if measured>-70 and level>0 else 0.
    ff(['-i',source,'-af',exact(f'volume={level*10**(music_gain/20):.6f},alimiter=limit=0.891:level=0:latency=1',duration)+f',afade=t=out:st={max(0,duration-.5)}:d=0.5','-t',duration,'-ar',RATE,'-ac','1','-c:a','pcm_s16le',normalized],folder)
    source.unlink(missing_ok=True)
    duck_music(normalized,ducked,bridged(intervals),low=10**(-DUCK_DB/20),attack=DUCK_ATTACK,release=DUCK_RELEASE)
    ambience=folder/'Umgebung.wav';effects=folder/'Effekte.wav';beds=synth_ambience(ambience,scenes,float(settings['ambience_level']))
    synth_effects(effects,scenes,settings['effects_level'])   # only cues the plan asks for: no automatic whoosh
    premix=folder/'Vormischung.wav';stems=(ducked,ambience,effects)
    def premixed():
        ff(['-i',dialogue,*sum((['-i',str(p)] for p in stems),[]),'-filter_complex',f'[0:a][1:a][2:a][3:a]amix=inputs=4:normalize=0:duration=longest,atrim=duration={duration}[m]','-map','[m]','-t',duration,'-ac','1','-c:a','pcm_f32le',premix],folder)
        measured=loudness(premix)[0]
        # One constant gain to the platform loudness (no dynamic loudnorm: it lifted music and hiss between the
        # lines). Without speech the music keeps its place relative to where the dialogue would be.
        return measured,TARGET_LUFS-measured if placed and measured>-70 else TARGET_LUFS-DIALOGUE_LUFS
    peak_over=PEAK_OVER_SPEECH
    for attempt in range(2):
        dialogue_gain,peak=voices(peak_over);measured,final_gain=premixed()
        # Speech peaks after the final gain and the stereo split (-3 dB) must stay under the limit, with room
        # for the bed beneath them. If not, the takes get a lower ceiling (same for all, levels stay).
        over=peak+final_gain-3-(FINAL_LIMIT-.7)
        if not placed or attempt or over<=.3 or peak_over<=9:break
        peak_over=max(9.,peak_over-over-.2)
    samples=speech_check.read_wav(dialogue)[0];dialogue_peak=max((abs(x) for x in samples),default=0);dialogue_rms=math.sqrt(sum(x*x for x in samples)/len(samples)) if samples else 0
    if placed and (dialogue_peak<500 or dialogue_rms<30):raise RuntimeError('Die Dialogspur ist stumm. Tonvorschau wurde nicht freigegeben; Stimmen bitte erneut erzeugen.')
    # Speech check on the stems before the final gain (it scales everything alike). The 0.18.2 safety net
    # stays: a masked line gets the bed lowered under it, a missing line still stops the mix.
    cleared={}
    for attempt in range(3):
        entries=speech_check.check_lines(samples,RATE,speech_check.placed(scenes),tuple(speech_check.read_wav(p)[0] for p in stems))
        masked=[e for e in entries if e['status']=='überdeckt']
        if not masked or attempt==2:break
        for key,lower in clear_lines(stems,masked).items():cleared[key]=round(cleared.get(key,0)+lower,1)
    for e in entries:
        key=e['key'] or e['label'];lowered=cleared.get(key);take=takes.get(key) or {}
        if take:e['line_gain_db']=take['gain']
        if lowered and not e['blocking']:e.update(cleared_db=lowered,note=(e['note']+'; ' if e['note'] else '')+f'Hintergrund hier um {lowered} dB abgesenkt')
        if lowered and e['status']=='ok':e['status']='abgesenkt'
        if take.get('gain',0)>QUIET_TAKE_DB and not e['blocking']:
            e['note']=(e['note']+'; ' if e['note'] else '')+f'Stimmprobe sehr leise, um {take["gain"]:.1f} dB angehoben'
            if e['status']=='ok':e['status']='angehoben'
    report=speech_check.summary(entries,'mix');speech_check.write_report(folder/'Sprachpruefung.json',report)
    if report['blocking']:raise speech_check.SpeechCheckError(speech_check.message(report,'„Produktion fortsetzen“ spricht nur diese Beiträge neu ein. Bleibt eine Zeile stumm, ihren Text oder die Stimme der Figur ändern.'),report)
    if cleared:measured,final_gain=premixed()
    target=folder/'Tonmischung.wav';temp=folder/'Tonmischung.partial.wav';limit=FINAL_LIMIT
    for attempt in range(3):
        # Stereo split first (each channel 3 dB under the mono sum, the loudness stays), then the peak limiter.
        ff(['-i',premix,'-af',exact(f'volume={final_gain:+.2f}dB,aresample=48000,pan=stereo|c0=0.70710678*c0|c1=0.70710678*c0,alimiter=limit={10**(limit/20):.5f}:level=0:latency=1',duration),
            '-t',duration,'-ac','2','-c:a','pcm_s16le',temp],folder)
        with wave.open(str(temp)) as w:
            if abs(w.getnframes()/w.getframerate()-duration)>.03:raise RuntimeError('Tonmischung unvollständig; keine Freigabe.')
        result,peak=loudness(temp)
        # A true peak over TRUE_PEAK lowers the limit; a loudness off target moves the one constant gain.
        retry=False
        if peak>TRUE_PEAK and limit>-6:limit-=min(3.,peak-TRUE_PEAK+.2);retry=True
        if placed and abs(TARGET_LUFS-result)>.3:final_gain+=max(-2.,min(2.,TARGET_LUFS-result));retry=True
        if not retry or attempt==2:break
    os.replace(temp,target)
    quiet=[f'{t["label"]} (+{t["gain"]:.1f} dB)' for t in takes.values() if t['gain']>QUIET_TAKE_DB]
    (folder/'Tonbericht.json').write_text(json.dumps({'seconds':duration,'lines':len(intervals),'music_mode':settings['music_mode'],'effects':sum(len(s.get('sound_cues',[])) for s in scenes),
        'dialogue_peak':dialogue_peak,'dialogue_rms':round(dialogue_rms,2),'speech_check':{k:report[k] for k in ('policy','checked','blocking','warnings')},
        'speech_warnings':[e['label']+' – '+e['note'] for e in report['lines'] if e['status']!='ok'],'sound_policy':SOUND_POLICY,
        'line_gain_db':{k:t['gain'] for k,t in takes.items()},'line_loudness_lufs':{k:t['level'] for k,t in takes.items()},'denoise':{k:t['denoise'] for k,t in takes.items()},'quiet_takes':quiet,
        'loudness':{'dialogue_gain_db':round(dialogue_gain,2),'peak_over_speech_db':round(peak_over,2),'music_gain_db':round(music_gain,2),'premix_lufs':measured,'final_gain_db':round(final_gain,2),
                    'limit_dbfs':round(limit,2),'integrated_lufs':result,'true_peak_dbtp':peak},
        'ambience':beds},ensure_ascii=False));return str(target)
