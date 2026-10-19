"""Measured dialogue, original cartoon accompaniment and deterministic ducking."""
from array import array
from pathlib import Path
import hashlib,json,math,os,random,re,subprocess,wave
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
def duck_music(source,target,intervals):
    with wave.open(str(source)) as w:
        if w.getframerate()!=RATE or w.getnchannels()!=1 or w.getsampwidth()!=2:raise RuntimeError('Ungültiges Musikformat.')
        data=array('h',w.readframes(w.getnframes()))
    if __import__('sys').byteorder!='little':data.byteswap()
    envelope=array('f',[1])*len(data);low=.28;attack=.08;release=.28
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
