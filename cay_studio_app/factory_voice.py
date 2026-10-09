"""Isolated Qwen VoiceDesign setup and persistent reference generation."""
import argparse,fcntl,hashlib,json,os,random,shutil,subprocess,sys,time
from pathlib import Path
from speech_quality import finish_voice,performance_key
PRESETS={'child_boy':'A fictional boy around ten, naturally youthful light voice, curious and energetic, not an adult falsetto.','child_girl':'A fictional girl around ten, naturally youthful bright voice, expressive and confident, not an adult falsetto.','young_man':'A young adult man, light tenor, relaxed and lively.','young_woman':'A young adult woman, clear bright voice, lively.','man':'An adult man, resonant mid-low baritone, confident.','woman':'An adult woman, rich warm midrange voice, expressive.','grandpa':'An elderly man, warm weathered baritone, slight gravel and breath texture, animated rather than excessively slow.','grandma':'An elderly woman, warm mature alto, subtle grain and expressive melody, animated rather than excessively slow.','creature':'A whimsical cartoon creature, distinctive texture and expressive articulation.'}
REPO='Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
REFERENCE_TEXT='Heute beginnt unsere Geschichte. Ich weiß noch nicht, was uns erwartet. Aber eines ist sicher: Wir halten zusammen. Hör genau zu, dann finden wir den richtigen Weg.'
def description(person,index):return PRESETS.get(person.get('voice_preset'),PRESETS['man'])+' Native German actor, natural conversational delivery, relaxed breath, varied intonation, never a synthetic announcer or exaggerated imitation. '+person.get('voice_description','')+' Character: '+person.get('personality','')+'. Clean dry studio speech, no music, reverb or background noise. '+['Precise consonants, dry smile.','Soft consonants, rounded resonance.','Light textured timbre, clear articulation.','Melodic, crisp diction.'][index%4]
def setup(base):
    env=base/'envs/studio-voices';model=base/'models/studio-voices/VoiceDesign';marker=env/'bereit.json';env.parent.mkdir(parents=True,exist_ok=True)
    def run(args):subprocess.run(list(map(str,args)),check=True)
    with (env.parent/'studio-voices.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if marker.is_file() and (model/'config.json').is_file():run([env/'bin/python',__file__,'--base',base,'--probe']);return
        if shutil.disk_usage(base).free<16*1024**3:raise RuntimeError('Mindestens 16 GB freier Speicher für Modell und separate Umgebung erforderlich.')
        python=base/'envs/chatterbox/bin/python'
        if not python.is_file():raise RuntimeError('Vorhandene Chatterbox-Umgebung fehlt.')
        print('1/3: Separate Stimmenumgebung einrichten.',flush=True)
        if not (env/'bin/python').is_file():run([python,'-m','venv',env])
        target=env/'bin/python';run([target,'-m','pip','install','--disable-pip-version-check','qwen-tts==0.1.1']);print('2/3: VoiceDesign-Modell herunterladen.',flush=True)
        code="from huggingface_hub import HfApi,snapshot_download\nfrom pathlib import Path\nimport json,sys\nrepo=sys.argv[1];dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=True);manifest=dest/'source.json'\nsha=json.loads(manifest.read_text())['revision'] if manifest.exists() else HfApi().model_info(repo).sha\nmanifest.write_text(json.dumps({'repo':repo,'revision':sha}))\nsnapshot_download(repo,revision=sha,local_dir=str(dest),allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'])"
        run([target,'-c',code,REPO,model]);print('3/3: Pakete, Modelldateien und CUDA prüfen.',flush=True);run([target,__file__,'--base',base,'--probe']);(env/'installierte_pakete.txt').write_bytes(subprocess.check_output([str(target),'-m','pip','freeze']));marker.write_text(json.dumps({'repo':REPO,'installed':time.time()}));print('STIMMENSTUDIO BEREIT',flush=True)
def generate(base,job_path,probe=False):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch,numpy as np,soundfile as sf
    from qwen_tts import Qwen3TTSModel
    model_path=base/'models/studio-voices/VoiceDesign'
    if not (model_path/'config.json').is_file():raise RuntimeError('Stimmenmodell fehlt. Stimmenstudio einrichten.')
    if not torch.cuda.is_available():raise RuntimeError('CUDA in der Stimmenumgebung nicht verfügbar.')
    if probe:print(json.dumps({'ready':True}));return
    job=json.loads(Path(job_path).read_text());out=Path(job['output']);out.mkdir(parents=True,exist_ok=True);profiles={};model=None
    for i,p in enumerate(job['cast']):
        if p.get('voice_file'):
            f=Path(p['voice_file'])
            if hashlib.sha256(f.read_bytes()).hexdigest()!=p['voice_hash']:raise RuntimeError('Stimmprobe verändert.')
            profiles[p['name']]={'file':str(f),'sha256':p['voice_hash'],'source':'upload'};continue
        instruction=description(p,i);sig=hashlib.sha256(json.dumps([instruction,p.get('voice_variant',0),job['run_id'],p['name'],REFERENCE_TEXT,'design08'],ensure_ascii=False).encode()).hexdigest();f=out/(sig+'.wav')
        if not f.is_file():
            if model is None:model=Qwen3TTSModel.from_pretrained(str(model_path),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
            seed=int(hashlib.sha256((job['run_id']+p['name']+str(p.get('voice_variant',0))).encode()).hexdigest()[:8],16)
            for attempt in range(2):
                random.seed(seed+attempt);np.random.seed((seed+attempt)%2**32);torch.manual_seed(seed+attempt)
                waves,sr=model.generate_voice_design(text=REFERENCE_TEXT,language='German',instruct=instruction,temperature=.7,top_p=.9,max_new_tokens=650)
                try:data,quality=finish_voice(waves[0],sr,REFERENCE_TEXT);break
                except RuntimeError:
                    if attempt:raise
            temp=f.with_suffix('.partial.wav');sf.write(temp,data,sr,subtype='PCM_16');os.replace(temp,f);f.with_suffix('.json').write_text(json.dumps({'description':instruction,'seed':seed+attempt,'quality':quality}))
        profiles[p['name']]={'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'source':'designed','preset':p.get('voice_preset','man'),'voice_text':REFERENCE_TEXT};print('Stimme gestaltet: '+p['name'],flush=True)
    # Reuse the same identity description and seed while changing acting direction.
    # The clone adapter can condition on a performed reference instead of ignoring emotion.
    for i,p in enumerate(job['cast']):
        if p.get('voice_file') or not job.get('performances'):continue
        moods=sorted({performance_key(line.get('emotion','Natürlich')) for line in job.get('lines',[]) if line['speaker']==p['name']})
        profiles[p['name']]['emotion_profiles']={}
        for emotion in moods:
            if emotion=='natural':continue
            instruction=description(p,i)+' Acting direction for this take: '+{'angry':'angry, controlled intensity','afraid':'afraid, tense breath','joy':'joyful and animated','sad':'sad, vulnerable','quiet':'intimate low whisper','firm':'firm and determined'}[emotion]+'. Keep the same age, vocal identity and timbre. Do not speak the direction aloud.'
            sig=hashlib.sha256(json.dumps([instruction,p.get('voice_variant',0),job['run_id'],p['name'],REFERENCE_TEXT,'performance11'],ensure_ascii=False).encode()).hexdigest();f=out/(sig+'.wav')
            if not f.is_file():
                if model is None:model=Qwen3TTSModel.from_pretrained(str(model_path),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
                seed=int(hashlib.sha256((job['run_id']+p['name']+str(p.get('voice_variant',0))).encode()).hexdigest()[:8],16)
                for attempt in range(2):
                    random.seed(seed+attempt);np.random.seed((seed+attempt)%2**32);torch.manual_seed(seed+attempt)
                    waves,sr=model.generate_voice_design(text=REFERENCE_TEXT,language='German',instruct=instruction,temperature=.7,top_p=.9,max_new_tokens=650)
                    try:data,quality=finish_voice(waves[0],sr,REFERENCE_TEXT);break
                    except RuntimeError:
                        if attempt:raise
                temp=f.with_suffix('.partial.wav');sf.write(temp,data,sr,subtype='PCM_16');os.replace(temp,f)
            profiles[p['name']]['emotion_profiles'][emotion]={'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'voice_text':REFERENCE_TEXT}
    temp=out/'Profile.partial.json';temp.write_text(json.dumps(profiles));os.replace(temp,out/'Profile.json')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--setup',action='store_true');parser.add_argument('--probe',action='store_true');parser.add_argument('--job');args=parser.parse_args()
    try:setup(Path(args.base)) if args.setup else generate(Path(args.base),args.job,args.probe)
    except Exception as e:print('STIMMEN ANGEHALTEN: '+str(e),file=sys.stderr);sys.exit(1)
