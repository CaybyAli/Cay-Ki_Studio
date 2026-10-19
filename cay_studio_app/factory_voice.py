"""Isolated Qwen VoiceDesign setup and persistent reference generation."""
import argparse,fcntl,hashlib,json,os,random,shutil,subprocess,sys,time
from pathlib import Path
from speech_quality import finish_voice,performance_key,performance_key_v16
PRESETS={'child_boy':'A fictional boy around ten, naturally youthful light voice, curious and energetic, not an adult falsetto.','child_girl':'A fictional girl around ten, naturally youthful bright voice, expressive and confident, not an adult falsetto.','young_man':'A young adult man, light tenor, relaxed and lively.','young_woman':'A young adult woman, clear bright voice, lively.','man':'An adult man, resonant mid-low baritone, confident.','woman':'An adult woman, rich warm midrange voice, expressive.','grandpa':'An elderly man, warm weathered baritone, slight gravel and breath texture, animated rather than excessively slow.','grandma':'An elderly woman, warm mature alto, subtle grain and expressive melody, animated rather than excessively slow.','creature':'A whimsical cartoon creature, distinctive texture and expressive articulation.'}
REPO='Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
# The clone continues the melody of its reference. 0.16 used one calm narrator
# text for every reference, also for "angry" or "afraid" takes, so every line
# sounded like the next sentence of a quiet story. Each delivery now has a
# reference text that is itself angry, afraid, joyful … (Qwen adapts tone to
# the meaning of the text; the reference transcript goes into the clone prompt).
REFERENCE_TEXT='Na endlich! Weißt du eigentlich, wie lange ich hier schon warte? Egal, komm rein, schnell, ich muss dir unbedingt was zeigen. Du wirst es nicht glauben!'
EMOTION_TEXTS={
 'angry':('furious, loud and sharp, clipped consonants','Jetzt reicht es mir aber! Ich hab dir hundertmal gesagt, du sollst das lassen! Gib das sofort her!'),
 'shout':('shouting at full volume, strained and urgent','Hey! Stehen bleiben! Hörst du mich nicht? Sofort stehen bleiben, hab ich gesagt!'),
 'panic':('panicked, breathless, fast and high-pitched','Nein, nein, nein! Was machen wir jetzt? Die kommen hierher, schnell, versteck dich!'),
 'afraid':('afraid and tense, trembling, hesitant','Hast du das gehört? Da … da ist irgendwas. Bitte, lass uns einfach hier verschwinden.'),
 'joy':('happy and warm, bright smile in the voice, light laughter','Ja! Wir haben es wirklich geschafft! Das ist der beste Tag überhaupt, ich freu mich so!'),
 'excited':('bursting with excitement, fast, high energy, enthusiastic','Oh, oh, oh! Schau dir das an! Das ist ja unglaublich, das müssen wir sofort ausprobieren!'),
 'triumph':('triumphant and gloating, savouring every word, a short evil laugh','Ha! Endlich gehört alles mir! Ihr hättet besser aufpassen sollen. Hahaha!'),
 'surprised':('genuinely surprised, rising pitch, disbelief','Was?! Das ist doch nicht dein Ernst! Wie bist du denn hier reingekommen?'),
 'sad':('sad and quiet, heavy, slow and vulnerable','Es ist vorbei. Alles, wofür ich gearbeitet habe, ist einfach weg.'),
 'whisper':('whispering, very soft and breathy, secretive','Psst, ganz leise. Da drüben ist jemand. Keinen Mucks jetzt, versprochen?'),
 'threat':('quietly threatening, low and slow, menacing','Hör mir jetzt ganz genau zu. Du zahlst. Heute noch. Sonst wird es sehr ungemütlich.'),
 'mocking':('mocking and sarcastic, drawn-out vowels, condescending','Ach wirklich? Der Wind hat es weggeweht? Na klar, und ich bin der Kaiser von China.'),
 'annoyed':('annoyed and impatient, sighing, clipped','Ernsthaft? Schon wieder? Ich hab wirklich keine Zeit für so was, mach einfach.'),
 'pleading':('pleading and desperate, voice cracking','Bitte, bitte, ich mach alles, was du willst! Nur nicht das, ich flehe dich an!'),
 'confused':('confused and puzzled, slow, questioning','Moment mal … Wie jetzt? Ich versteh gar nichts mehr. Wer war das denn dann?'),
 'firm':('firm and determined, steady and strong','Nein. Wir machen das jetzt so, wie ich es sage. Keine Diskussion mehr.'),
}
CARTOON='German cartoon dubbing voice actor, highly animated and theatrical, wide pitch range, comedic timing, characterful and instantly recognisable. '
NATURAL='Native German actor, natural conversational delivery, varied intonation, never a synthetic announcer. '
def cartoonish(person,look):return look in ('cartoon','clay','paper') or bool(person.get('original')) or person.get('voice_preset')=='creature'
def description(person,index,look=''):return PRESETS.get(person.get('voice_preset'),PRESETS['man'])+' '+(CARTOON if cartoonish(person,look) else NATURAL)+person.get('voice_description','')+' Character: '+person.get('personality','')+'. Clean dry studio speech, no music, reverb or background noise. '+['Precise consonants, dry smile.','Soft consonants, rounded resonance.','Light textured timbre, clear articulation.','Melodic, crisp diction.'][index%4]
# Projects voiced before 0.17 keep their voices: these texts are part of the cache
# signature, so a later partial re-voice reuses the approved 0.16 references.
REFERENCE_TEXT_V16='Heute beginnt unsere Geschichte. Ich weiß noch nicht, was uns erwartet. Aber eines ist sicher: Wir halten zusammen. Hör genau zu, dann finden wir den richtigen Weg.'
ACTING_V16={'angry':'angry, controlled intensity','afraid':'afraid, tense breath','joy':'joyful and animated','sad':'sad, vulnerable','quiet':'intimate low whisper','firm':'firm and determined'}
def description_v16(person,index):return PRESETS.get(person.get('voice_preset'),PRESETS['man'])+' Native German actor, natural conversational delivery, relaxed breath, varied intonation, never a synthetic announcer or exaggerated imitation. '+person.get('voice_description','')+' Character: '+person.get('personality','')+'. Clean dry studio speech, no music, reverb or background noise. '+['Precise consonants, dry smile.','Soft consonants, rounded resonance.','Light textured timbre, clear articulation.','Melodic, crisp diction.'][index%4]
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
    legacy=int(job.get('voice_policy',17))<17;transcript=int(job.get('voice_policy',17))>=18;reference=REFERENCE_TEXT_V16 if legacy else REFERENCE_TEXT
    for i,p in enumerate(job['cast']):
        if p.get('voice_file'):
            f=Path(p['voice_file'])
            if hashlib.sha256(f.read_bytes()).hexdigest()!=p['voice_hash']:raise RuntimeError('Stimmprobe verändert.')
            # 0.18: keep the transcript of an own recording (the clone is much closer with it).
            # The transcript conditions the clone (more exact voice); only from voice policy 18 on, so
            # 0.17 projects keep their x-vector clones and cached lines.
            profiles[p['name']]={'file':str(f),'sha256':p['voice_hash'],'source':'upload',**({'voice_text':p.get('voice_text','')} if transcript else {})};continue
        instruction=description_v16(p,i) if legacy else description(p,i,job.get('look',''))
        sig=hashlib.sha256(json.dumps([instruction,p.get('voice_variant',0),job['run_id'],p['name'],reference,'design08' if legacy else 'design17'],ensure_ascii=False).encode()).hexdigest();f=out/(sig+'.wav')
        if not f.is_file():
            if model is None:model=Qwen3TTSModel.from_pretrained(str(model_path),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
            seed=int(hashlib.sha256((job['run_id']+p['name']+str(p.get('voice_variant',0))).encode()).hexdigest()[:8],16)
            for attempt in range(2):
                random.seed(seed+attempt);np.random.seed((seed+attempt)%2**32);torch.manual_seed(seed+attempt)
                waves,sr=model.generate_voice_design(text=reference,language='German',instruct=instruction,temperature=.7,top_p=.9,max_new_tokens=650)
                try:data,quality=finish_voice(waves[0],sr,reference);break
                except RuntimeError:
                    if attempt:raise
            temp=f.with_suffix('.partial.wav');sf.write(temp,data,sr,subtype='PCM_16');os.replace(temp,f);f.with_suffix('.json').write_text(json.dumps({'description':instruction,'seed':seed+attempt,'quality':quality}))
        profiles[p['name']]={'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'source':'designed','preset':p.get('voice_preset','man'),'voice_text':reference};print('Stimme gestaltet: '+p['name'],flush=True)
    # Reuse the same identity description and seed while changing acting direction.
    # The clone adapter can condition on a performed reference instead of ignoring emotion.
    for i,p in enumerate(job['cast']):
        # Own recordings get no emotion takes (VoiceDesign cannot clone them); library voices
        # bring their design recipe and get emotion takes in the same designed voice.
        recipe=p.get('voice_design') if p.get('voice_file') and not legacy else None
        if (p.get('voice_file') and not recipe) or not job.get('performances'):continue
        key=performance_key_v16 if legacy else lambda e:performance_key(e,int(job.get('voice_policy',17)))
        moods=sorted({key(line.get('emotion','Natürlich')) for line in job.get('lines',[]) if line['speaker']==p['name']})
        profiles[p['name']]['emotion_profiles']={}
        for emotion in moods:
            if emotion=='natural':continue
            if legacy:
                text=reference;sampling={'temperature':.7,'top_p':.9}
                instruction=description_v16(p,i)+' Acting direction for this take: '+ACTING_V16[emotion]+'. Keep the same age, vocal identity and timbre. Do not speak the direction aloud.'
                sig=hashlib.sha256(json.dumps([instruction,p.get('voice_variant',0),job['run_id'],p['name'],text,'performance11'],ensure_ascii=False).encode()).hexdigest()
            else:
                acting,text=EMOTION_TEXTS.get(emotion,EMOTION_TEXTS['firm']);sampling={'temperature':.9,'top_p':1.}
                base=recipe['instruction'] if recipe else description(p,i,job.get('look',''))
                instruction=base+' Acting for this take, strongly performed: '+acting+'. Same person, same age and timbre. Do not speak the direction aloud.'
                sig=hashlib.sha256(json.dumps([instruction,p.get('voice_variant',0),job['run_id'],p['name'],text,'performance17'],ensure_ascii=False).encode()).hexdigest()
            f=out/(sig+'.wav')
            if not f.is_file():
                if model is None:model=Qwen3TTSModel.from_pretrained(str(model_path),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
                # Own seed per mood (0.17): moods do not share one unlucky seed.
                seed=(int(recipe['seed'])+int(hashlib.sha256(emotion.encode()).hexdigest()[:6],16))%2**31 if recipe else int(hashlib.sha256((job['run_id']+p['name']+str(p.get('voice_variant',0))+('' if legacy else emotion)).encode()).hexdigest()[:8],16);data=None
                for attempt in range(2):
                    random.seed(seed+attempt);np.random.seed((seed+attempt)%2**32);torch.manual_seed(seed+attempt)
                    waves,sr=model.generate_voice_design(text=text,language='German',instruct=instruction,max_new_tokens=650,**sampling)
                    try:data,quality=finish_voice(waves[0],sr,text);break
                    except RuntimeError:pass
                if data is None:
                    # One failed mood must not stop the whole cast: these lines use the base voice.
                    print('Gefühlsprobe übersprungen: '+p['name']+' '+emotion,flush=True);continue
                temp=f.with_suffix('.partial.wav');sf.write(temp,data,sr,subtype='PCM_16');os.replace(temp,f)
            profiles[p['name']]['emotion_profiles'][emotion]={'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'voice_text':text}
    temp=out/'Profile.partial.json';temp.write_text(json.dumps(profiles));os.replace(temp,out/'Profile.json')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--setup',action='store_true');parser.add_argument('--probe',action='store_true');parser.add_argument('--job');args=parser.parse_args()
    try:setup(Path(args.base)) if args.setup else generate(Path(args.base),args.job,args.probe)
    except Exception as e:print('STIMMEN ANGEHALTEN: '+str(e),file=sys.stderr);sys.exit(1)
