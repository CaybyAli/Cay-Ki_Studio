"""Qwen Base dialogue adapter in the existing isolated voice environment."""
import argparse,hashlib,json,os,random,shutil,sys,time,types
from pathlib import Path
from speech_quality import clean_text,finish_voice,SPEECH_POLICY,performance_key,performance_key_v16,prosody_score
import tts_text

REPO='Qwen/Qwen3-TTS-12Hz-1.7B-Base'

def ready(base):
    model=base/'models/studio-voices/Base'
    return all(p.is_file() for p in [base/'envs/studio-voices/bin/python',model/'config.json',model/'bereit.json'])

def setup(base):
    from huggingface_hub import HfApi,snapshot_download
    model=base/'models/studio-voices/Base';model.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(base).free<10*1024**3:raise RuntimeError('Mindestens 10 GB freier Speicher für die zusätzliche Stimmeneinrichtung erforderlich.')
    source=model/'source.json'
    revision=json.loads(source.read_text())['revision'] if source.exists() else HfApi().model_info(REPO).sha
    source.write_text(json.dumps({'repo':REPO,'revision':revision}))
    print('Qwen-Dialogmodell herunterladen. Bestehende VoiceDesign-Stimmen bleiben erhalten.',flush=True)
    snapshot_download(REPO,revision=revision,local_dir=str(model),allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'])
    import torch
    from qwen_tts import Qwen3TTSModel
    if not torch.cuda.is_available() or not callable(getattr(Qwen3TTSModel,'create_voice_clone_prompt',None)):raise RuntimeError('Qwen-Dialogumgebung unterstützt CUDA oder Stimmklonen nicht.')
    temp=model/'bereit.partial.json';temp.write_text(json.dumps({'repo':REPO,'revision':revision,'installed':time.time()}));os.replace(temp,model/'bereit.json')
    print('QWEN-DIALOGSTUDIO BEREIT',flush=True)

# 0.19 (voice_policy 19, projects pinned with sound_policy 19; diagnosis r019 B5e "flat voices"): every line gets a
# second take and an emotional line a third, the liveliest one that still sounds like the speaker wins. A recording
# (own upload or library recording) had no performed references: every line cloned the same calm sample. Now the Base
# model clones each needed delivery's acted text (factory_voice.EMOTION_TEXTS) from the recording, the liveliest
# similar take becomes that delivery's reference, and its lines clone it with the exact transcript (ICL).
TAKES_19=(2,3)          # takes for a natural line, for an emotional line
REFERENCE_TAKES=3       # takes per performed reference (one figure and delivery, made once and cached)
SIMILAR_FLOOR=.5        # speaker-embedding cosine to the recording under which a take is not the same person;
SIMILAR_SPREAD=.08      # ... and a take may be at most this much less similar than the most similar one.
                        # Start values: real distances must be calibrated on Cay's PC.

def read_pcm(path):
    """16-bit mono WAV as float samples (wave + numpy: runs with the fakes too); (None, 0) for anything else."""
    import wave,numpy as np
    try:
        with wave.open(str(path)) as w:
            if w.getsampwidth()!=2 or w.getnchannels()!=1:return None,0
            return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768,w.getframerate()
    except (OSError,EOFError,wave.Error):return None,0

def embedding(model,data,sr):
    """Speaker embedding (qwen-tts Base: model.model.extract_speaker_embedding, 24 kHz); None when unavailable."""
    import numpy as np
    if data is None or sr!=24000:return None
    try:
        e=model.model.extract_speaker_embedding(audio=np.asarray(data,dtype=np.float32),sr=24000)
        return np.asarray(e.detach().float().cpu().numpy() if hasattr(e,'detach') else e,dtype=np.float64).reshape(-1)
    except Exception:return None

def similarity(a,b):
    import numpy as np
    if a is None or b is None or a.shape!=b.shape:return None
    return round(float(np.dot(a,b)/max(1e-9,float(np.linalg.norm(a)*np.linalg.norm(b)))),3)

def alike(takes):
    """Takes (score, data, quality) that still sound like the speaker; all of them when nothing could be measured."""
    known=[t[2]['similarity'] for t in takes if t[2].get('similarity') is not None]
    if not known:return takes
    top=max(known);return [t for t in takes if t[2].get('similarity') is None or t[2]['similarity']>=max(SIMILAR_FLOOR,top-SIMILAR_SPREAD)] or takes

def generate(base,path):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import numpy as np,soundfile as sf,torch
    from qwen_tts import Qwen3TTSModel
    if not ready(base):raise RuntimeError('Qwen-Dialogmodell fehlt. Unter Stimmenqualität einmal einrichten.')
    job=json.loads(Path(path).read_text());out=Path(job['output']);out.mkdir(parents=True,exist_ok=True)
    model_path=base/'models/studio-voices/Base';loaded=[];prompts={};voices={};cast={p['name']:p for p in job['cast']};result=[]
    model_identity=(model_path/'source.json').read_text() if (model_path/'source.json').is_file() else str(model_path)
    # Projects voiced before 0.17 keep 0.16 references, sampling and cache signatures.
    policy=int(job.get('voice_policy',17));legacy=policy<17;key=performance_key_v16 if legacy else lambda e:performance_key(e,policy)
    def load():
        if not loaded:loaded.append(Qwen3TTSModel.from_pretrained(str(model_path),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True))
        return loaded[0]
    def prompt(person):
        prompt_key=person['voice_hash']+person.get('voice_text','')
        if prompt_key not in prompts:
            transcript=person.get('voice_text') or None
            prompts[prompt_key]=load().create_voice_clone_prompt(ref_audio=str(person['voice_file']),ref_text=transcript,x_vector_only_mode=not bool(transcript))
        return prompts[prompt_key]
    def voice(name):
        # 0.19: the recording's own speaker embedding, the yardstick for every take of this figure.
        if name not in voices:voices[name]=embedding(load(),*read_pcm(cast[name]['voice_file']))
        return voices[name]
    def clone(options):
        try:return load().generate_voice_clone(**options,top_k=50)
        except TypeError:return load().generate_voice_clone(**options)
    def seeded(seed):random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if policy>=19:performed_references(job,cast,out,key,model_identity,types.SimpleNamespace(load=load,prompt=prompt,voice=voice,clone=clone,seeded=seeded,write=sf.write))
    for i,line in enumerate(job['lines']):
        person=dict(cast[line['speaker']]);performed=person.get('emotion_profiles',{}).get(key(line.get('emotion','')))
        if performed:person.update(voice_file=performed['file'],voice_hash=performed['sha256'],voice_text=performed['voice_text'])
        ref=Path(person['voice_file'])
        if hashlib.sha256(ref.read_bytes()).hexdigest()!=person['voice_hash']:raise RuntimeError('Stimmreferenz wurde verändert.')
        delivery=performance_key(line.get('emotion',''),policy)
        # 0.19 (job 'speech_text', projects pinned with sound_policy 19): the model reads tts_text.speakable;
        # the signature changes only for a line whose spoken text differs from the written one.
        signature=hashlib.sha256(json.dumps({'line':line,'voice':person['voice_hash'],'ref_text':person.get('voice_text',''),'model':model_identity,'processing':SPEECH_POLICY,'engine':'qwen-base-11-performance' if legacy else 'qwen-base-19-takes' if policy>=19 else 'qwen-base-17-takes',**tts_text.signature_fields(line,job)},sort_keys=True).encode()).hexdigest()
        target=out/(line['key']+'_'+signature[:12]+'.wav');meta=target.with_suffix('.json')
        cached=target.is_file() and meta.is_file() and json.loads(meta.read_text()).get('signature')==signature
        if not cached:
            model=load();voice_prompt=prompt(person)
            # Library defaults (0.9 / 1.0 / 50) instead of 0.7 / 0.9: more melody.
            # Emotional lines get two valid takes; the livelier one is kept (0.19: TAKES_19, the speaker kept).
            wanted=TAKES_19[delivery!='natural'] if policy>=19 else 1 if delivery=='natural' or legacy else 2;takes=[];error=None
            for attempt in range(wanted+1):
                if len(takes)>=wanted:break
                seed=(line['seed']+attempt)%2**32;seeded(seed)
                options=dict(text=tts_text.spoken(line,job),language='German',voice_clone_prompt=voice_prompt,non_streaming_mode=True,temperature=.7 if legacy else .9,top_p=.9 if legacy else 1.,max_new_tokens=min(650,max(128,len(line['text'].split())*15+80)))
                if legacy:waves,sr=model.generate_voice_clone(**options)
                else:waves,sr=clone(options)
                try:
                    data,quality=finish_voice(waves[0],sr,line['text'])
                    takes.append((prosody_score(data,sr),data,{**quality,'prosody':prosody_score(data,sr),'seed':seed,
                                                               **({'similarity':similarity(embedding(model,data,sr),voice(line['speaker']))} if policy>=19 else {})}))
                except RuntimeError as failure:error=failure
            if not takes:
                # Lets "Produktion fortsetzen" retake exactly this line with a new seed.
                (out/'Fehlgeschlagen.json').write_text(json.dumps({'key':line['key']}))
                raise RuntimeError(f"Folge {line['episode']+1}, Szene {line['scene']+1}, Figur {line['speaker']}: {error}") from error
            _,data,quality=max(alike(takes) if policy>=19 else takes,key=lambda x:x[0]);quality['takes']=len(takes)
            temp=target.with_suffix('.partial.wav');sf.write(temp,data,sr,subtype='PCM_16');os.replace(temp,target)
            meta.write_text(json.dumps({'signature':signature,'quality':quality,'engine':'qwen'}))
        info=sf.info(target)
        if not .15<info.duration<40:raise RuntimeError('Sprachdatei hat eine unplausible Dauer.')
        result.append({**line,'file':str(target),'duration':info.duration,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'engine':'qwen'})
        print(f'Dialog {i+1}/{len(job["lines"])} fertig',flush=True)
    # 0.19: how each figure was cloned (app and diagnosis); older jobs keep their exact result file.
    extra={'references':{n:{'mode':'icl' if p.get('voice_text') else 'x-vector','emotions':sorted(p.get('emotion_profiles') or {}),
                            'performed':sorted(m for m,e in (p.get('emotion_profiles') or {}).items() if e.get('performed'))} for n,p in cast.items()}} if policy>=19 else {}
    temp=out/'Ergebnis.partial.json';temp.write_text(json.dumps({'lines':result,**extra},ensure_ascii=False));os.replace(temp,out/'Ergebnis.json')

def performed_references(job,cast,out,key,identity,t):
    """0.19: a performed reference per needed delivery for every figure without one (own or library recording; a designed
    voice whose mood failed). REFERENCE_TAKES clones of the delivery's acted text from the figure's voice; the liveliest
    take that still sounds like it is kept (cached by voice, transcript, text and model). When none does, the lines of that
    delivery clone the voice itself. Updates cast[name]['emotion_profiles'] in place (copies, the job stays as written)."""
    from factory_voice import EMOTION_TEXTS
    needed={}
    for line in job['lines']:
        mood=key(line.get('emotion',''))
        if mood in EMOTION_TEXTS:needed.setdefault(line['speaker'],set()).add(mood)
    for name,moods in sorted(needed.items()):
        person=cast[name]=dict(cast[name]);have=person['emotion_profiles']=dict(person.get('emotion_profiles') or {})
        for mood in sorted(moods-set(have)):
            text=EMOTION_TEXTS[mood][1]
            sig=hashlib.sha256(json.dumps([person['voice_hash'],person.get('voice_text',''),text,identity,'performed19'],ensure_ascii=False).encode()).hexdigest()
            f=out/'Gefuehle'/(sig[:24]+'.wav');meta=f.with_suffix('.json')
            try:done=json.loads(meta.read_text())
            except (OSError,ValueError):done=None
            if done and done.get('skipped'):continue
            if not (done and f.is_file()):
                f.parent.mkdir(parents=True,exist_ok=True);takes=[];seed=int(sig[:8],16)
                for attempt in range(REFERENCE_TAKES):
                    t.seeded((seed+attempt)%2**32)
                    waves,sr=t.clone(dict(text=text,language='German',voice_clone_prompt=t.prompt(person),non_streaming_mode=True,temperature=.9,top_p=1.,max_new_tokens=650))
                    try:data,quality=finish_voice(waves[0],sr,text)
                    except RuntimeError:continue
                    takes.append((prosody_score(data,sr),data,{**quality,'prosody':prosody_score(data,sr),'seed':(seed+attempt)%2**32,
                                                               'similarity':similarity(embedding(t.load(),data,sr),t.voice(name))}))
                known=[x for x in takes if x[2]['similarity'] is None or x[2]['similarity']>=SIMILAR_FLOOR]
                if not known:
                    meta.write_text(json.dumps({'skipped':True,'emotion':mood,'takes':len(takes)}));print('Gefühlsprobe übersprungen: '+name+' '+mood,flush=True);continue
                _,data,quality=max(alike(known),key=lambda x:x[0])
                temp=f.with_suffix('.partial.wav');t.write(temp,data,sr,subtype='PCM_16');os.replace(temp,f)
                meta.write_text(json.dumps({'emotion':mood,'voice_text':text,'takes':len(takes),'quality':quality}))
            have[mood]={'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'voice_text':text,'performed':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--setup',action='store_true');p.add_argument('--job');a=p.parse_args()
    try:setup(Path(a.base)) if a.setup else generate(Path(a.base),a.job)
    except Exception as e:print('QWEN-DIALOG ANGEHALTEN: '+str(e),file=sys.stderr);sys.exit(1)
