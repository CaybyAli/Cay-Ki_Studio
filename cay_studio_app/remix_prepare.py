"""Isolated model setup and streaming SAM2 masks. No changes to existing ML environments."""
from pathlib import Path
import argparse,fcntl,json,math,os,shutil,subprocess,sys,time
from remix_engine import MODEL,REPO,REVISION,SAM_REPO,FPS,dimensions
from wan_text_encoder import CORE_TEXT,TEXT_REPO,TEXT_REVISION,TEXT_SHA256,local_ready,validate_file
from factory_video import ff,probe,file_hash
from remix_identity import download_model,model_ready

def prepare_environment(source,env):
    """Share the existing CUDA wheels read-only, not the unrelated system Python."""
    python=env/'bin/python'
    if not python.is_file():subprocess.run([str(source),'-m','venv',str(env)],check=True)
    query='import json,site;print(json.dumps(site.getsitepackages()))'
    roots=json.loads(subprocess.check_output([str(source),'-c',query],text=True))
    target=json.loads(subprocess.check_output([str(python),'-c',query],text=True))[0]
    allowed=[str(Path(p).resolve()) for p in roots if Path(p).is_dir()]
    if not allowed:raise RuntimeError('Die vorhandenen CUDA-Pakete konnten nicht gefunden werden.')
    Path(target,'cay_comfy_packages.pth').write_text('\n'.join(allowed)+'\n')
    return python

def setup(base):
    env=base/'envs/studio-remix';env.parent.mkdir(parents=True,exist_ok=True)
    with (env.parent/'studio-remix.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        python=env/'bin/python';source=base/'envs/comfyui/bin/python'
        if not source.is_file():raise RuntimeError('Vorhandene ComfyUI-Python-Umgebung fehlt.')
        existing=local_ready(base/'apps/ComfyUI') and (base/'apps/ComfyUI/models/diffusion_models'/MODEL).is_file()
        needed=3 if existing else 32
        if shutil.disk_usage(base).free<needed*1024**3:raise RuntimeError(f'Mindestens {needed} GB freier Speicher für diese Figurentausch-Einrichtung erforderlich.')
        def run(args):subprocess.run(list(map(str,args)),check=True)
        print('1/3: Separate Umgebung für Maskenverfolgung.',flush=True)
        prepare_environment(source,env)
        run([python,'-m','pip','install','--disable-pip-version-check','transformers==4.57.6','huggingface-hub>=0.34,<1','Pillow>=10,<13','sentencepiece>=0.2,<0.3'])
        print('2/3: Fehlende Videomodelle und lokale Figurenprüfung ergänzen. Vorhandene Modelle bleiben erhalten.',flush=True)
        run([python,__file__,'--base',base,'--download'])
        print('3/3: Dateien, Pakete und CUDA prüfen.',flush=True);run([python,__file__,'--base',base,'--probe'])
        (env/'bereit.json').write_text(json.dumps({'installed':time.time(),'model':MODEL,'revision':REVISION}));print('FIGURENTAUSCH EINGERICHTET',flush=True)

def download(base):
    from huggingface_hub import HfApi,hf_hub_download,snapshot_download
    target=base/'apps/ComfyUI/models/diffusion_models'/MODEL;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.is_file():
        # Avoid downloading a second multi-GB cache copy when an existing
        # installation only needs the new, small visual checker.
        staging=target.parent/'cay_vace_download';staging.mkdir(exist_ok=True)
        source=hf_hub_download(REPO,'split_files/diffusion_models/'+MODEL,revision=REVISION,local_dir=staging)
        os.replace(source,target)
    model=base/'models/studio-remix/SAM2';model.mkdir(parents=True,exist_ok=True)
    manifest=model/'source.json';revision=json.loads(manifest.read_text())['revision'] if manifest.exists() else HfApi().model_info(SAM_REPO).sha
    manifest.write_text(json.dumps({'repo':SAM_REPO,'revision':revision}));snapshot_download(SAM_REPO,revision=revision,local_dir=model,allow_patterns=['*.json','*.safetensors'])
    ensure_text(base)
    if not model_ready(base):download_model(base)

def ensure_text(base):
    from huggingface_hub import hf_hub_download
    comfy=base/'apps/ComfyUI'
    if local_ready(comfy):return
    print('Passendes UMT5-Textmodell für ComfyUI fehlt. Etwa 6,74 GB zusätzlich herunterladen.',flush=True)
    source=Path(hf_hub_download(TEXT_REPO,'split_files/text_encoders/'+CORE_TEXT,revision=TEXT_REVISION))
    if file_hash(source)!=TEXT_SHA256:raise RuntimeError('Prüfsumme des UMT5-Downloads stimmt nicht. Keine Installation.')
    validate_file(source)
    target=comfy/'models/text_encoders'/CORE_TEXT;target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.partial');shutil.copyfile(source,temp)
    if target.exists():os.replace(target,target.with_name(target.name+'.vor_0_8_'+str(time.time_ns())))
    os.replace(temp,target)

def track(base,job_path=None,probe_only=False):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch,numpy as np
    from PIL import Image,ImageFilter
    from transformers import Sam2VideoModel,Sam2VideoProcessor
    model_dir=base/'models/studio-remix/SAM2'
    if not torch.cuda.is_available():raise RuntimeError('CUDA ist in der Figurentausch-Umgebung nicht verfügbar.')
    if not (model_dir/'config.json').is_file():raise RuntimeError('SAM2 fehlt.')
    if not (base/'apps/ComfyUI/models/diffusion_models'/MODEL).is_file():raise RuntimeError('VACE fehlt.')
    if not local_ready(base/'apps/ComfyUI'):raise RuntimeError('Passendes UMT5-Textmodell fehlt. Figurenstudio erneut einrichten.')
    if not model_ready(base):raise RuntimeError('Lokale Figurenprüfung fehlt. Figurenstudio einmal ergänzen.')
    if probe_only:print(json.dumps({'ready':True}));return
    job=json.loads(Path(job_path).read_text());folder=Path(job['folder']);folder.mkdir(parents=True,exist_ok=True)
    if file_hash(job['source'])!=job['source_hash']:raise RuntimeError('Originalvideo wurde verändert.')
    width,height=dimensions(job['width'],job['height']);total=math.ceil(job['seconds']*FPS)
    for sub in ('frames','masks','control','overlay'):(folder/sub).mkdir(exist_ok=True)
    ff(['-protocol_whitelist','file,pipe','-ss',job['start'],'-i',job['source'],'-an','-vf',f'fps={FPS},scale={width}:{height}',
        '-frames:v',total,'-start_number',0,folder/'frames/%06d.png'])
    actual=len(list((folder/'frames').glob('*.png')))
    if actual<total:raise RuntimeError('Ausschnitt reicht über das Ende des Originalvideos. Einen kürzeren Ausschnitt wählen.')
    model=Sam2VideoModel.from_pretrained(model_dir,local_files_only=True).to('cuda',dtype=torch.bfloat16).eval()
    processor=Sam2VideoProcessor.from_pretrained(model_dir,local_files_only=True)
    session=processor.init_video_session(inference_device='cuda',dtype=torch.bfloat16)
    missing=0;areas=[]
    with torch.inference_mode():
        for index in range(total):
            with Image.open(folder/'frames'/f'{index:06}.png') as img:frame=img.convert('RGB')
            inputs=processor(images=frame,device='cuda',return_tensors='pt')
            if index==0:
                processor.add_inputs_to_inference_session(inference_session=session,frame_idx=0,obj_ids=1,
                    input_points=[[[[p[0]*width,p[1]*height] for p in [job['point'],*job.get('exclude_points',[])]]]],input_labels=[[[1]+[0]*len(job.get('exclude_points',[]))]],original_size=inputs.original_sizes[0])
            output=model(inference_session=session,frame=inputs.pixel_values[0].to(dtype=torch.bfloat16))
            raw=processor.post_process_masks([output.pred_masks],original_sizes=inputs.original_sizes,binarize=False)[0]
            pixels=(raw[0,0]>0).cpu().numpy().astype(np.uint8)*255
            fraction=float((pixels>0).mean());areas.append(fraction)
            if fraction<.002:missing+=1
            if index==0 and not .002<fraction<.92:raise RuntimeError('Markierung erkennt keine einzelne Figur. Im ersten Bild genauer auf die Person klicken.')
            # Keep a soft boundary for compositing, but the VACE control mask
            # itself is thresholded later so white always means "generate".
            margin=max(17,min(31,int(max(width,height)*.035)//2*2+1))
            mask=Image.fromarray(pixels,'L').filter(ImageFilter.MaxFilter(margin)).filter(ImageFilter.GaussianBlur(2))
            mask.save(folder/'masks'/f'{index:06}.png')
            # Official VACE Swap Anything input: missing region is neutral gray,
            # not the original person's edges (which condition its appearance).
            Image.composite(Image.new('RGB',frame.size,(127,127,127)),frame,mask.point(lambda v:255 if v>8 else 0)).save(folder/'control'/f'{index:06}.png')
            overlay=Image.composite(Image.new('RGB',frame.size,(30,154,255)),frame,mask.point(lambda v:int(v*.4)))
            overlay.save(folder/'overlay'/f'{index:06}.png')
            if index%16==0:print(f'Maske verfolgen: {index+1}/{total} Bilder',flush=True)
    if missing>max(2,total*.1):raise RuntimeError('Die ausgewählte Figur geht in zu vielen Bildern verloren. Kürzeren Ausschnitt ohne Schnitt wählen oder Markierung korrigieren.')
    for sub,name in [('masks','mask.mp4'),('overlay','Maske_Vorschau.mp4')]:
        ff(['-framerate',FPS,'-start_number',0,'-i',folder/sub/'%06d.png','-frames:v',total,'-c:v','libx264','-crf','0' if sub=='masks' else '22','-pix_fmt','yuv420p',folder/name])
    meta={'width':width,'height':height,'frames':total,'seconds':job['seconds'],'lost_frames':missing,'source_hash':job['source_hash']}
    temp=folder/'Tracking.partial.json';temp.write_text(json.dumps(meta));os.replace(temp,folder/'Tracking.json')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--setup',action='store_true');p.add_argument('--download',action='store_true');p.add_argument('--probe',action='store_true');p.add_argument('--job');a=p.parse_args()
    try:
        base=Path(a.base)
        if a.setup:setup(base)
        elif a.download:download(base)
        else:track(base,a.job,a.probe)
    except Exception as e:print('FIGURENTAUSCH ANGEHALTEN: '+str(e),file=sys.stderr);sys.exit(1)
