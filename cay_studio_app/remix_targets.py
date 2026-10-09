"""Ordered independent identity tracks; checkpoints live in the parent project."""
from pathlib import Path
import copy,math,json,os,shutil
from factory_video import ff,file_hash,probe
from image_workflow import build_graph,validate_nodes
from remix_engine import FPS,anchor_indices,PIPELINE_POLICY
from factory import digest

KINDS={'reference':'the exact subject and species in reference image 2','person':'a human person','dog':'a dog with a canine head, fur, muzzle and paws; never a human face or human skin','cat':'a cat with feline anatomy, fur, ears and paws; never a human face','animal':'the animal species in reference image 2, animal head and anatomy; never a human face','object':'the object in reference image 2; preserve its material and shape, never a human head'}

def targets(request):
    return request.get('targets') or [{k:request.get(k) for k in ('x','y','reference','prompt','kind')}]

def target_document(parent,index):
    item=parent['target_work'][index];req={**parent['request'],**parent['request']['targets'][index]};req.pop('targets',None)
    return {**copy.deepcopy(item),'id':parent['id'],'_target_index':index,'_parent_id':parent['id'],'request':req,'title':parent['title'],'state':item.get('state','tracking')}

def save_child(engine,child):
    parent=engine.get(child['_parent_id']);i=child['_target_index']
    parent['target_work'][i]={k:v for k,v in child.items() if k not in ('id','_parent_id','_target_index','request','title','revision','updated')}
    parent['phase']=f'Punkt {i+1}/{len(parent["request"]["targets"])} · '+child.get('phase','')
    engine.save(parent)

async def prepare_multi(engine,parent):
    if 'target_work' not in parent:parent['target_work']=[{} for _ in parent['request']['targets']];engine.save(parent)
    for index in range(len(parent['request']['targets'])):
        parent=engine.get(parent['id']);child=target_document(parent,index)
        if child.get('state')=='mask_review' and child.get('identity_policy')==PIPELINE_POLICY:continue
        if engine.paused(parent['id']):return
        await engine._prepare_one(child)
        if child['state']=='awaiting_setup':parent=engine.get(parent['id']);parent.update(state='awaiting_setup',phase=child['phase']);engine.save(parent);return
        if child['state']!='mask_review':return
    parent=engine.get(parent['id']);parent.update(state='mask_review',phase='Alle Zuordnungen, Masken und tatsächlich ersetzten Startbilder prüfen.');engine.save(parent)

async def produce_multi(engine,parent):
    for index in range(len(parent['request']['targets'])):
        parent=engine.get(parent['id']);child=target_document(parent,index)
        if child.get('state')=='done':continue
        if engine.paused(parent['id']):return
        child['approval']=parent.get('approval');await engine._produce_one(child)
        if child['state']=='quality_review':
            parent=engine.get(parent['id']);parent.update(state='quality_review',quality_target=index,phase=child['phase']);engine.save(parent);return
        if child['state']=='tracking':
            parent=engine.get(parent['id']);parent.update(state='tracking',phase=child['phase']);engine.save(parent);return
        if child['state']!='finishing':return
        # Each identity pass retains the original timing. Final compositing is CPU work.
        await engine._finish_one(child)
    parent=engine.get(parent['id']);parent.update(state='finishing',phase='Alle Figuren mit Originalton zusammensetzen');engine.save(parent)

def composite_targets(engine,parent):
    source=engine.source(parent['request']['asset_id']);req=parent['request'];folder=engine.folder(parent);fps=req.get('fps',30)
    width,height=source['width']//2*2,source['height']//2*2
    if max(width,height)>1920:
        scale=1920/max(width,height);width=int(width*scale)//2*2;height=int(height*scale)//2*2
    args=['-ss',req['start'],'-i',source['file']];filters=[f'[0:v]setpts=PTS-STARTPTS,fps={fps},scale={width}:{height},format=rgba[base]'];last='base'
    for i,work in enumerate(parent['target_work']):
        clip=work['export'];child=target_document(parent,i);mask=engine.folder(child)/'Verfolgung/mask.mp4'
        if file_hash(clip['file'])!=clip['sha256'] or file_hash(mask)!=work['mask_hash']:raise RuntimeError('Eine freigegebene Figur oder Maske wurde verändert.')
        args+=['-i',clip['file'],'-i',str(mask)];a=1+2*i;b=a+1
        filters += [f'[{a}:v]setpts=PTS-STARTPTS,fps={fps},scale={width}:{height},format=rgba[v{i}]',f'[{b}:v]setpts=PTS-STARTPTS,fps={fps},scale={width}:{height},format=gray[m{i}]',f'[v{i}][m{i}]alphamerge[f{i}]',f'[{last}][f{i}]overlay=0:0:format=auto[b{i}]'];last='b'+str(i)
    filters.append(f'[{last}]format=yuv420p,drawtext=text=KI-bearbeitet:fontcolor=white:fontsize=24:box=1:boxcolor=black@0.55:boxborderw=8:x=18:y=18[out]')
    tmp=folder/'Mehrere_Figuren.partial.mp4'
    ff([*args,'-filter_complex',';'.join(filters),'-map','[out]','-map','0:a:0?','-af','asetpts=PTS-STARTPTS','-t',req['seconds'],'-c:v','libx264','-crf','17','-c:a','aac','-b:a','256k','-movflags','+faststart',tmp])
    meta=probe(tmp);duration=float(meta['format']['duration'])
    if abs(duration-req['seconds'])>.12:raise RuntimeError('Mehrfiguren-Export hat eine falsche Laufzeit.')
    dest=folder/'Figurentausch_Vorschau.mp4';dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(tmp,dest.with_suffix('.partial.mp4'));os.replace(dest.with_suffix('.partial.mp4'),dest);tmp.unlink()
    return {'file':str(dest),'sha256':file_hash(dest),'seconds':duration,'fps':fps,'width':width,'height':height,'targets':len(parent['target_work'])}

async def prepare_anchor(engine,d):
    """Identity anchors cover the whole clip, using the same visual reference."""
    folder=engine.folder(d)/'Verfolgung';req=d['request'];kind=req.get('kind') or 'reference'
    total=d['tracking']['frames'];indices=anchor_indices(total)
    anchors=d.setdefault('identity_anchors',[])
    if d.get('identity_policy')!=PIPELINE_POLICY:
        anchors=[];d['identity_anchors']=anchors;d.pop('clips',None);d.pop('approval',None)
    prompt=('Edit reference image 1. Reference image 3 marks the ONLY subject to replace in blue. Remove that entire original subject, including its face, head, hair, torso and clothes where appropriate. '
            'Replace that subject with '+KINDS[kind]+'. Reference image 2 is the identity to use, never a style suggestion. '
            'Keep all other people, background, camera and lighting unchanged. Preserve the current pose and hand positions of image 1. '
            'Render the replacement naturally inside this scene, same framing, no panels, no text, no blue marking. '+req.get('prompt',''))
    models=validate_nodes(await engine.object_info())
    d['identity_policy']=PIPELINE_POLICY;engine.save(d)
    for position,index in enumerate(indices):
        if any(a['frame']==index and Path(a['file']).is_file() and file_hash(a['file'])==a['sha256'] for a in anchors):continue
        if engine.paused(d['id']):return
        frame=folder/'frames'/f'{index:06}.png';mask=folder/'masks'/f'{index:06}.png';overlay=folder/'overlay'/f'{index:06}.png'
        refs=[engine.stage(frame),engine.stage(d['reference_file']),engine.stage(overlay)]
        text=prompt
        if anchors:
            refs.append(engine.stage(anchors[0]['file']))
            text+=' Reference image 4 shows this exact replacement already in the scene. Match its face, species, markings and clothing; use the current pose from image 1.'
        g=build_graph(text,refs,int(digest([d['id'],d.get('_target_index',0),'anchor12'])[:12],16),'',models)
        g['68']['inputs']['value']=d['tracking']['width'];g['69']['inputs']['value']=d['tracking']['height']
        d['phase']=f'Figur über den Verlauf festlegen · Bild {position+1}/{len(indices)}';engine.save(d)
        result=await engine.render(d,'anchor12:'+str(index)+':'+digest([req,d['reference_hash'],d['mask_hash'],file_hash(frame)])[:16],g)
        dest=folder/f'Figurenbild_{index:06}.png'
        await engine.cpu(ff,['-i',str(frame),'-i',result['output'],'-i',str(mask),'-filter_complex',f'[0:v]format=rgba[bg];[1:v]scale={d["tracking"]["width"]}:{d["tracking"]["height"]},format=rgba[fg];[2:v]format=gray[m];[fg][m]alphamerge[a];[bg][a]overlay=0:0:format=auto[out]','-map','[out]','-frames:v','1',dest])
        anchors[:]=[a for a in anchors if a['frame']!=index];anchors.append({'frame':index,'seconds':index/FPS,'file':str(dest),'sha256':file_hash(dest)})
        anchors.sort(key=lambda a:a['frame']);d['anchor_file']=anchors[0]['file'];d['anchor_hash']=anchors[0]['sha256'];engine.save(d)
