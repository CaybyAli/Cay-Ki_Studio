"""Local, bounded visual checks. This is a drift warning, not an identity guarantee.

Runs on CPU in the isolated remix environment after each generated section.
No images or videos are uploaded to an inference service.
"""
from pathlib import Path
import argparse,json,math,os
from factory_video import ff,file_hash

CHECK_REPO='google/siglip2-base-patch16-224'
CHECK_REVISION='75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2'
CHECK_POLICY=1
CHECK_FILES=('config.json','model.safetensors','preprocessor_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','tokenizer.model')
KINDS=('dog','cat','person','animal','object')
LABELS=('a dog with a canine head and muzzle','a cat with a feline head and ears','a human person with a human face','an animal other than a dog or cat','an inanimate object or a fantasy creature')

def model_ready(base):
    root=Path(base)/'models/studio-remix/Identity'
    try:
        record=json.loads((root/'ready.json').read_text())
        return record.get('revision')==CHECK_REVISION and all((root/name).is_file() and (root/name).stat().st_size==size for name,size in record['files'].items()) and set(record['files'])==set(CHECK_FILES)
    except (OSError,ValueError,KeyError,TypeError):return False

def download_model(base):
    from huggingface_hub import hf_hub_download
    root=Path(base)/'models/studio-remix/Identity';root.mkdir(parents=True,exist_ok=True)
    for name in CHECK_FILES:
        print('Figurenprüfung herunterladen: '+name,flush=True)
        hf_hub_download(CHECK_REPO,name,revision=CHECK_REVISION,local_dir=root)
    # A real offline load catches incomplete weights/tokenizers before marking ready.
    load_model(root)
    data={'revision':CHECK_REVISION,'files':{name:(root/name).stat().st_size for name in CHECK_FILES}}
    tmp=root/'ready.partial.json';tmp.write_text(json.dumps(data));os.replace(tmp,root/'ready.json')

def load_model(root):
    import torch
    from transformers import AutoModel,AutoProcessor
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    processor=AutoProcessor.from_pretrained(root,local_files_only=True,use_fast=False)
    model=AutoModel.from_pretrained(root,local_files_only=True).eval().to('cpu')
    return processor,model

def sample_indices(frames):
    # Four checks per second, plus the exact final delivered frame.
    return sorted(set([*range(0,frames,4),frames-1])) if frames>0 else []

def assess(rows,expected):
    suspects=[]
    for row in rows:
        if expected in ('dog','cat','animal','object'):
            wanted=max(row['scores'][k] for k in (('dog','cat','animal') if expected=='animal' else (expected,)))
            if row['scores']['person']-wanted>1.5:suspects.append(row['second'])
        if expected in ('dog','cat','person') and max(row['scores'][k] for k in ('dog','cat','person') if k!=expected)-row['scores'][expected]>2.5:
            suspects.append(row['second'])
        if row.get('reference_similarity',1)<.75 and row.get('original_similarity',0)>row.get('reference_similarity',1)+.12:
            suspects.append(row['second'])
    suspects=sorted(set(suspects))
    return {'status':'review' if suspects else 'pass','suspect_seconds':suspects,'sampled':len(rows),'expected_kind':expected,
            'reason':'Möglicher Wechsel zur ursprünglichen Figur erkannt.' if suspects else 'In den geprüften Bildern kein deutlicher Rückwechsel erkannt.',
            'policy':CHECK_POLICY,'checks':rows}

def crop_subject(image,mask=None,head=False):
    from PIL import Image
    image=image.convert('RGB')
    if mask is not None:
        mask=mask.convert('L').resize(image.size)
        box=mask.point(lambda v:255 if v>32 else 0).getbbox()
        if box:
            x0,y0,x1,y1=box;pad=max(4,int((x1-x0)*.04))
            box=(max(0,x0-pad),max(0,y0-pad),min(image.width,x1+pad),min(image.height,y1+pad))
            image=image.crop(box)
    if head:image=image.crop((0,0,image.width,max(1,int(image.height*.58))))
    return image

def check_video(base,job,model_root=None):
    from PIL import Image
    import torch
    root=Path(model_root) if model_root else Path(base)/'models/studio-remix/Identity'
    processor,model=load_model(root)
    folder=Path(job['folder']);count=int(job['frames']);start=int(job.get('start_frame',0))
    video=Path(job['video']);indices=sample_indices(count)
    if file_hash(video)!=job['sha256']:raise RuntimeError('Der zu prüfende Abschnitt wurde verändert.')
    work=folder/('Identitaetspruefung_'+file_hash(video)[:16]);work.mkdir(exist_ok=True)
    ff(['-i',video,'-vf','fps=16','-frames:v',count,'-start_number',0,work/'%06d.png'])
    prompts=['This is a photo of '+label+'.' for label in LABELS]
    def encode(images):
        inputs=processor(text=prompts,images=images,padding='max_length',max_length=64,truncation=True,return_tensors='pt')
        with torch.inference_mode():out=model(**inputs)
        return out.logits_per_image.float(),torch.nn.functional.normalize(out.image_embeds.float(),dim=-1)
    ref=Image.open(job['reference']).convert('RGB')
    logits,_=encode([ref])
    expected=job.get('kind','reference')
    inferred=KINDS[int(logits[0].argmax())]
    if expected=='reference':expected=inferred
    rows=[]
    for batch in range(0,len(indices),4):
        ids=indices[batch:batch+4];images=[];pairs=[]
        for local in ids:
            frame=min(start+local,int(job.get('total_frames',start+count))-1)
            mask_path=folder/'masks'/f'{frame:06}.png'
            mask=Image.open(mask_path) if mask_path.exists() else None
            image=Image.open(work/f'{local:06}.png')
            # Head crop makes human skin/muzzle changes visible when clothing
            # and a large unchanged background would dominate the whole image.
            images.append(crop_subject(image,mask,head=expected in ('dog','cat','person','animal')))
            originals=folder/'frames'/f'{frame:06}.png'
            nearest=min(job.get('anchors',[]),key=lambda a:abs(a['frame']-frame),default=None)
            if expected=='person' and nearest and originals.is_file():
                a_frame=nearest['frame'];a_mask=Image.open(folder/'masks'/f'{a_frame:06}.png')
                pairs.append((crop_subject(Image.open(nearest['file']),a_mask,head=True),crop_subject(Image.open(originals),mask,head=True)))
            else:pairs.append(None)
        logits,embeds=encode(images)
        comparable=[img for pair in pairs if pair for img in pair]
        pair_embeds=encode(comparable)[1] if comparable else None;pi=0
        for n,local in enumerate(ids):
            scores={k:round(float(logits[n,i]),4) for i,k in enumerate(KINDS)}
            row={'second':round((start+local)/16,3),'scores':scores}
            if pairs[n] and expected=='person':
                row.update(reference_similarity=round(float(embeds[n]@pair_embeds[pi]),4),original_similarity=round(float(embeds[n]@pair_embeds[pi+1]),4))
            if pairs[n]:pi+=2
            rows.append(row)
        print(f'Figurenprüfung: {min(batch+4,len(indices))}/{len(indices)} Bilder',flush=True)
    report=assess(rows,expected);report.update(video_sha256=job['sha256'],model_revision=CHECK_REVISION)
    if job.get('report'):
        dest=Path(job['report']);tmp=dest.with_suffix('.partial.json');tmp.write_text(json.dumps(report,ensure_ascii=False));os.replace(tmp,dest)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--job');p.add_argument('--download',action='store_true');p.add_argument('--model-root');a=p.parse_args()
    os.environ['HF_HUB_OFFLINE']='0' if a.download else '1';os.environ['TRANSFORMERS_OFFLINE']='0' if a.download else '1'
    if a.download:download_model(Path(a.base))
    else:print(json.dumps(check_video(Path(a.base),json.loads(Path(a.job).read_text()),a.model_root),ensure_ascii=False))
