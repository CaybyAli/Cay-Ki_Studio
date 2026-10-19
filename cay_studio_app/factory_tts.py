"""Runs only in Cay's existing Chatterbox environment. No downloads."""
import argparse,copy,hashlib,inspect,json,os,random,subprocess,sys
from pathlib import Path
from speech_quality import clean_text,sampling,finish_voice,SPEECH_POLICY
import tts_text
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'

def checkpoint(base):
    required=['ve.pt','s3gen.pt','t3_mtl23ls_v2.safetensors','grapheme_mtl_merged_expanded_v1.json']
    roots=[base/'models/chatterbox-cache/hub/models--ResembleAI--chatterbox/snapshots',Path.home()/'.cache/huggingface/hub/models--ResembleAI--chatterbox/snapshots']
    for env in ('HF_HOME','HUGGINGFACE_HUB_CACHE'):
        if os.environ.get(env):
            cache=Path(os.environ[env]);roots += [cache/'hub/models--ResembleAI--chatterbox/snapshots',cache/'models--ResembleAI--chatterbox/snapshots']
    roots += [base/'models/chatterbox/snapshots',base/'models/chatterbox-cache/models--ResembleAI--chatterbox/snapshots']
    choices=[p for root in roots if root.is_dir() for p in sorted(root.iterdir()) if p.is_dir() and all((p/f).is_file() for f in required)]
    if not choices:raise RuntimeError('Die vorhandenen mehrsprachigen Chatterbox-Dateien wurden nicht vollständig gefunden. Keine Downloads gestartet.')
    return next((p for p in choices if p.name=='5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18'),choices[0])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--probe',action='store_true');parser.add_argument('--job');args=parser.parse_args()
    base=Path(args.base);ckpt=checkpoint(base)
    import numpy as np
    import soundfile as sf
    import torch
    import perth
    if not callable(getattr(perth,'PerthImplicitWatermarker',None)):
        from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker
        perth.PerthImplicitWatermarker=PerthImplicitWatermarker
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    if not callable(getattr(ChatterboxMultilingualTTS,'from_local',None)):raise RuntimeError('Chatterbox unterstützt den vorhandenen lokalen Lader nicht.')
    if not torch.cuda.is_available():raise RuntimeError('Chatterbox: CUDA nicht verfügbar.')
    if args.probe:
        print(json.dumps({'ready':True,'default_voice':(ckpt/'conds.pt').is_file()}));return
    job=json.loads(Path(args.job).read_text());out=Path(job['output']);out.mkdir(parents=True,exist_ok=True)
    policy=int(job.get('voice_policy',17))  # before 0.17: same sampling, so cached lines stay valid
    options={'t3_model':'t3_mtl23ls_v2.safetensors'} if 't3_model' in inspect.signature(ChatterboxMultilingualTTS.from_local).parameters else {}
    model=ChatterboxMultilingualTTS.from_local(ckpt,device='cuda',**options);default=copy.deepcopy(model.conds)
    def generate(text,ref,emotion,seed,written):
        random.seed(seed);np.random.seed(seed%2**32);torch.manual_seed(seed)
        model.conds=copy.deepcopy(default)
        if not ref and model.conds is None:raise RuntimeError('Für erfundene Stimmen fehlt die lokale Standardstimme (conds.pt). Bitte eine Stimmprobe im Projekt ergänzen.')
        requested=sampling(emotion,policy)
        accepted=inspect.signature(model.generate).parameters
        requested={k:v for k,v in requested.items() if k in accepted}
        wave=model.generate(text=text,language_id='de',audio_prompt_path=str(ref) if ref else None,**requested)
        data=wave.detach().cpu().numpy().reshape(-1)
        return finish_voice(data,model.sr,written)
    voices={}
    for index,person in enumerate(job['cast']):
        name=person['name'];ref=person.get('voice_file');ident=hashlib.sha256(name.encode()).hexdigest()[:12]
        if ref:
            if hashlib.sha256(Path(ref).read_bytes()).hexdigest()!=person['voice_hash']:raise RuntimeError('Stimmreferenz verändert: '+name)
            voices[name]=ref;continue
        raise RuntimeError('Für '+name+' fehlt ein Stimmprofil. Zuerst Stimmenstudio einrichten.')
    result=[]
    for index,line in enumerate(job['lines']):
        # 0.19 (job 'speech_text', sound_policy 19): the model reads tts_text.speakable; other lines keep their signature.
        signature=hashlib.sha256(json.dumps({'line':line,'voice_sha256':hashlib.sha256(Path(voices[line['speaker']]).read_bytes()).hexdigest(),'checkpoint':str(ckpt),'processing':SPEECH_POLICY,'sampling':sampling(line['emotion'],policy),**tts_text.signature_fields(line,job)},sort_keys=True).encode()).hexdigest()
        target=out/(line['key']+'_'+signature[:12]+'.wav');meta=target.with_suffix('.json')
        if not(target.is_file() and meta.is_file() and json.loads(meta.read_text()).get('signature')==signature):
            for attempt in range(2):
                try:data,quality=generate(tts_text.spoken(line,job),voices[line['speaker']],line['emotion'],line['seed']+attempt,line['text']);break
                except RuntimeError as error:
                    if attempt:
                        # Lets "Produktion fortsetzen" retake exactly this line with a new seed.
                        (out/'Fehlgeschlagen.json').write_text(json.dumps({'key':line['key']}))
                        raise RuntimeError(f"Folge {line['episode']+1}, Szene {line['scene']+1}, Figur {line['speaker']}: {error}") from error
            temp=target.with_suffix('.partial.wav');sf.write(temp,data,model.sr,subtype='PCM_16');os.replace(temp,target)
            meta.write_text(json.dumps({'signature':signature,'quality':quality}))
        info=sf.info(target)
        if not 0.15<info.duration<40:raise RuntimeError('Sprachspur hat unerwartete Länge: '+line['key'])
        result.append({**line,'file':str(target),'duration':info.duration,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'engine':'chatterbox'})
        print(f'Sprache {index+1}/{len(job["lines"])} fertig',flush=True)
    target=out/'Ergebnis.json';temp=out/'Ergebnis.partial.json';temp.write_text(json.dumps({'lines':result,'voice_profiles':voices},ensure_ascii=False,indent=2));os.replace(temp,target)

if __name__=='__main__':
    try:main()
    except Exception as e:print('SPRACHE ANGEHALTEN: '+str(e),file=sys.stderr);sys.exit(1)
