"""Qwen Base dialogue adapter in the existing isolated voice environment."""
import argparse,hashlib,json,os,random,shutil,sys,time
from pathlib import Path
from speech_quality import clean_text,finish_voice,SPEECH_POLICY,performance_key

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

def generate(base,path):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import numpy as np,soundfile as sf,torch
    from qwen_tts import Qwen3TTSModel
    if not ready(base):raise RuntimeError('Qwen-Dialogmodell fehlt. Unter Stimmenqualität einmal einrichten.')
    job=json.loads(Path(path).read_text());out=Path(job['output']);out.mkdir(parents=True,exist_ok=True)
    model_path=base/'models/studio-voices/Base';model=None;prompts={};cast={p['name']:p for p in job['cast']};result=[]
    model_identity=(model_path/'source.json').read_text() if (model_path/'source.json').is_file() else str(model_path)
    for i,line in enumerate(job['lines']):
        person=dict(cast[line['speaker']]);performed=person.get('emotion_profiles',{}).get(performance_key(line.get('emotion','')))
        if performed:person.update(voice_file=performed['file'],voice_hash=performed['sha256'],voice_text=performed['voice_text'])
        ref=Path(person['voice_file'])
        if hashlib.sha256(ref.read_bytes()).hexdigest()!=person['voice_hash']:raise RuntimeError('Stimmreferenz wurde verändert.')
        signature=hashlib.sha256(json.dumps({'line':line,'voice':person['voice_hash'],'ref_text':person.get('voice_text',''),'model':model_identity,'processing':SPEECH_POLICY,'engine':'qwen-base-11-performance'},sort_keys=True).encode()).hexdigest()
        target=out/(line['key']+'_'+signature[:12]+'.wav');meta=target.with_suffix('.json')
        cached=target.is_file() and meta.is_file() and json.loads(meta.read_text()).get('signature')==signature
        if not cached:
            if model is None:model=Qwen3TTSModel.from_pretrained(str(model_path),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
            prompt_key=person['voice_hash']+person.get('voice_text','')
            if prompt_key not in prompts:
                transcript=person.get('voice_text') or None
                prompts[prompt_key]=model.create_voice_clone_prompt(ref_audio=str(ref),ref_text=transcript,x_vector_only_mode=not bool(transcript))
            for attempt in range(2):
                seed=(line['seed']+attempt)%2**32;random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
                waves,sr=model.generate_voice_clone(text=clean_text(line['text']),language='German',voice_clone_prompt=prompts[prompt_key],non_streaming_mode=True,temperature=.7,top_p=.9,max_new_tokens=min(650,max(128,len(line['text'].split())*15+80)))
                try:data,quality=finish_voice(waves[0],sr,line['text']);break
                except RuntimeError:
                    if attempt:raise
            temp=target.with_suffix('.partial.wav');sf.write(temp,data,sr,subtype='PCM_16');os.replace(temp,target)
            meta.write_text(json.dumps({'signature':signature,'quality':quality,'engine':'qwen'}))
        info=sf.info(target)
        if not .15<info.duration<40:raise RuntimeError('Sprachdatei hat eine unplausible Dauer.')
        result.append({**line,'file':str(target),'duration':info.duration,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'engine':'qwen'})
        print(f'Dialog {i+1}/{len(job["lines"])} fertig',flush=True)
    temp=out/'Ergebnis.partial.json';temp.write_text(json.dumps({'lines':result},ensure_ascii=False));os.replace(temp,out/'Ergebnis.json')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--setup',action='store_true');p.add_argument('--job');a=p.parse_args()
    try:setup(Path(a.base)) if a.setup else generate(Path(a.base),a.job)
    except Exception as e:print('QWEN-DIALOG ANGEHALTEN: '+str(e),file=sys.stderr);sys.exit(1)
