"""Bounded VACE video editing adapter; original audio is only trimmed/muxed, never synthesized."""
from pathlib import Path
import json,math,os,subprocess,shutil
from factory_video import ff,probe,file_hash
from studio_quality_policy import cadence
from wan_text_encoder import choose as choose_text

MODEL='wan2.1_vace_1.3B_fp16.safetensors'
REPO='Comfy-Org/Wan_2.1_ComfyUI_repackaged'
REVISION='617a7633e636506f850e043bc4605f290a466a8e'
SAM_REPO='facebook/sam2.1-hiera-tiny'
FPS=16
SEGMENT_FRAMES=32
ANCHOR_STRIDE=16
PIPELINE_POLICY=12
PROMPT_POLICY=12

def anchor_indices(total):
    if total<1:raise ValueError('Keine Videobilder vorhanden.')
    return sorted(set([*range(0,total,ANCHOR_STRIDE),total-1]))

def dimensions(width,height):
    scale=min(1.,832/max(width,height),480/min(width,height))
    return max(32,math.ceil(width*scale/16)*16),max(32,math.ceil(height*scale/16)*16)

def edit_models(info,comfy=None):
    found={'clip':choose_text(info,comfy)}
    for key,kind,field,names in [('model','UNETLoader','unet_name',[MODEL]),
        ('vae','VAELoader','vae_name',['wan_2.1_vae.safetensors'])]:
        options=info.get(kind,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
        choices=[x for x in options if x.replace('\\','/').split('/')[-1] in names]
        if not choices:raise ValueError('Figurentausch-Modell fehlt: '+names[0]+'. Unter Figurentausch einmal einrichten.')
        found[key]=choices[0]
    required={'LoadVideo','GetVideoComponents','ImageToMask','WanVaceToVideo','TrimVideoLatent','KSampler','VAEDecode','CreateVideo','SaveVideo','LoadImage','ModelSamplingSD3','CLIPTextEncode'}
    missing=required-info.keys()
    if missing:raise ValueError('Diese ComfyUI-Nodes fehlen: '+', '.join(sorted(missing))+'. Die normale Filmproduktion bleibt verfügbar.')
    return found

def graph(control,masks,reference,prompt,models,width,height,frames,seed,quality='balanced',kind='reference'):
    if not 1<=frames<=81 or (frames-1)%4:raise ValueError('Ungültige Länge des Bearbeitungsabschnitts.')
    def n(kind,**inputs):return {'class_type':kind,'inputs':inputs}
    forbidden='human face, human skin, bald human head, morphing into a person, changing species, ' if kind in ('dog','cat','animal','object') else ''
    g={'1':n('LoadVideo',file=control),'2':n('GetVideoComponents',video=['1',0]),
       '3':n('LoadVideo',file=masks),'4':n('GetVideoComponents',video=['3',0]),
       '5':n('ImageToMask',image=['4',0],channel='red'),
       '6':n('UNETLoader',unet_name=models['model'],weight_dtype='default'),
       '7':n('CLIPLoader',clip_name=models['clip'],type='wan',device='default'),
       '8':n('VAELoader',vae_name=models['vae']),
       '9':n('CLIPTextEncode',clip=['7',0],text=prompt),
       '10':n('CLIPTextEncode',clip=['7',0],text=forbidden+'edge map, outline drawing, flat gray placeholder, unfinished inpainting, identity flicker, changing face, extra people, extra limbs, deformed body, captions, interface, logos, scene change'),
       '11':n('WanVaceToVideo',positive=['9',0],negative=['10',0],vae=['8',0],width=width,height=height,length=frames,batch_size=1,strength=1.0,control_video=['2',0],control_masks=['5',0]),
       '12':n('ModelSamplingSD3',model=['6',0],shift=8.0),
       '13':n('KSampler',model=['12',0],seed=seed,steps=40 if quality=='high' else 28,cfg=5.,sampler_name='uni_pc',scheduler='simple',positive=['11',0],negative=['11',1],latent_image=['11',2],denoise=1.),
       '16':n('TrimVideoLatent',samples=['13',0],trim_amount=['11',3]),
       '17':n('VAEDecode',samples=['16',0],vae=['8',0]),
       '14':n('CreateVideo',images=['17',0],fps=FPS),
       '15':n('SaveVideo',video=['14',0],filename_prefix='',format='mp4',codec='h264')}
    if reference:g['18']=n('LoadImage',image=reference);g['11']['inputs']['reference_image']=['18',0]
    return g

def segment_inputs(folder,index,total,previous=None,anchor=None,anchors=None,stride=SEGMENT_FRAMES):
    """Reinforce the approved subject every second, including internal frames.

    The boundary at start+take belongs to the following clip, so exports trim
    it exactly once. No frozen frame is inserted into the final rendered video.
    """
    folder=Path(folder);start=index*stride;take=min(stride,total-start);length=4*math.ceil(take/4)+1
    if take<=0:raise ValueError('Bearbeitungsabschnitt liegt außerhalb des Videos.')
    work=folder/f'Abschnitt_{index:03}';work.mkdir(exist_ok=True)
    continuation=work/'anschluss.png'
    approved={int(a['frame']):Path(a['file']) for a in (anchors or [])}
    if previous and start not in approved:ff(['-i',previous,'-vf',f'select=eq(n\\,{stride})','-frames:v','1',continuation])
    for a in anchors or []:
        if file_hash(a['file'])!=a['sha256']:raise RuntimeError('Ein freigegebenes Figurenbild wurde verändert.')
    info=probe(folder/'frames/000000.png')['streams'][0]
    black=work/'schwarz.png'
    ff(['-f','lavfi','-i',f'color=c=black:s={info["width"]}x{info["height"]}','-frames:v','1',black])
    for j in range(length):
        source_index=min(total-1,start+j)
        # Always rebuild from original RGB frames, including older tracked jobs.
        # Old control/ files contained the person's edges and must not be reused.
        shutil.copyfile(folder/'frames'/f'{source_index:06}.png',work/f'c_{j:03}.png')
        shutil.copyfile(folder/'masks'/f'{source_index:06}.png',work/f'm_{j:03}.png')
        if source_index in approved:
            shutil.copyfile(approved[source_index],work/f'c_{j:03}.png')
            shutil.copyfile(black,work/f'm_{j:03}.png')
    if start not in approved and (previous or anchor):
        first=continuation if previous else Path(anchor)
        shutil.copyfile(first,work/'c_000.png');shutil.copyfile(black,work/'m_000.png')
    # VACE inpainting: white = generate, black = retain. Remove the selected
    # person's appearance completely, including the feathered mask boundary.
    ff(['-framerate',FPS,'-i',work/'m_%03d.png','-vf',"lut=y='if(gt(val,8),255,0)'",'-frames:v',length,'-c:v','libx264','-crf','0','-pix_fmt','yuv420p',work/'mask.mp4'])
    info=probe(work/'c_000.png')['streams'][0]
    filters='[0:v]format=gbrp[base];[1:v]format=gray,format=gbrp[mask];[2:v]format=gbrp[fill];[base][fill][mask]maskedmerge[out]'
    ff(['-framerate',FPS,'-i',work/'c_%03d.png','-i',work/'mask.mp4','-f','lavfi','-i',f'color=c=0x7f7f7f:s={info["width"]}x{info["height"]}:r={FPS}',
        '-filter_complex',filters,'-map','[out]','-frames:v',length,'-c:v','libx264','-crf','0','-pix_fmt','yuv420p',work/'control.mp4'])
    return work/'control.mp4',work/'mask.mp4',length,take

def finish_edit(folder,source,start,seconds,segments,width,height,output,fps=25,smooth=False):
    if fps not in (25,30):raise ValueError('25 oder 30 FPS wählen.')
    folder=Path(folder);parts=[]
    for i,clip in enumerate(segments):
        if file_hash(clip['file'])!=clip['sha256']:raise RuntimeError('Bearbeitungsclip wurde verändert.')
        video=next(s for s in probe(clip['file'])['streams'] if s['codec_type']=='video')
        if float(video.get('duration',0))+1e-6<clip['frames']/FPS:raise RuntimeError('Ein erzeugter Bearbeitungsabschnitt ist zu kurz. Export angehalten.')
        name=f'edit_{i:03}.mp4';ff(['-i',clip['file'],'-an','-vf',f'fps={FPS}','-frames:v',clip['frames'],'-c:v','libx264','-crf','17','-pix_fmt','yuv420p',folder/name])
        trimmed=next(s for s in probe(folder/name)['streams'] if s['codec_type']=='video')
        if int(trimmed.get('nb_frames',0))!=clip['frames']:raise RuntimeError('Ein Bearbeitungsabschnitt ist unvollständig.')
        parts.append(name)
    (folder/'edit_list.txt').write_text(''.join(f"file '{x}'\n" for x in parts))
    ff(['-f','concat','-safe','1','-i','edit_list.txt','-an','-c','copy','edit_join.mp4'],folder)
    joined=next(s for s in probe(folder/'edit_join.mp4')['streams'] if s['codec_type']=='video')
    if int(joined.get('nb_frames',0))!=sum(c['frames'] for c in segments):raise RuntimeError('Im Figurentausch fehlen erzeugte Videoframes.')
    ow=max(2,int(width)//2*2);oh=max(2,int(height)//2*2)
    if max(ow,oh)>1920:
        factor=1920/max(ow,oh);ow=max(2,int(ow*factor)//2*2);oh=max(2,int(oh*factor)//2*2)
    # Composite over the original background and retain its audio/timebase.
    # Keep the original background at delivery cadence. Interpolate only the
    # generated character, before upscale, without retiming the original audio.
    # Compose through an alpha channel. Passing a gray stream directly into
    # maskedmerge can make FFmpeg negotiate the whole result as monochrome.
    # alphamerge keeps the generated RGB character and original RGB background
    # separate until overlay, so a colour replacement cannot become grayscale.
    filters=f'[0:v]setpts=PTS-STARTPTS,fps={fps},scale={ow}:{oh}:flags=lanczos,setsar=1,format=rgba[base];[1:v]setpts=PTS-STARTPTS,{cadence(fps,smooth,FPS)},scale={ow}:{oh}:flags=lanczos,setsar=1,format=rgba[edit];[2:v]setpts=PTS-STARTPTS,fps={fps},scale={ow}:{oh},format=gray[mask];[edit][mask]alphamerge[fg];[base][fg]overlay=0:0:format=auto,format=yuv420p,drawtext=text=KI-bearbeitet:fontcolor=white:fontsize=24:box=1:boxcolor=black@0.55:boxborderw=8:x=18:y=18[out]'
    temp=folder/'Figurentausch.partial.mp4'
    ff(['-protocol_whitelist','file,pipe','-ss',start,'-i',source,'-i',folder/'edit_join.mp4','-i',folder/'mask.mp4',
        '-filter_complex',filters,'-map','[out]','-map','0:a:0?','-t',seconds,'-c:v','libx264','-preset','medium','-crf','17','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','256k','-af','asetpts=PTS-STARTPTS','-movflags','+faststart',temp])
    check=probe(temp);video=next(s for s in check['streams'] if s['codec_type']=='video')
    if abs(float(check['format']['duration'])-seconds)>.12 or abs(float(video.get('duration',0))-seconds)>.081 or video['width']!=ow or video['height']!=oh:raise RuntimeError('Figurentausch-Export hat eine unerwartete Länge oder Bildgröße.')
    if any(s['codec_type']=='audio' for s in probe(source)['streams']) and not any(s['codec_type']=='audio' for s in check['streams']):raise RuntimeError('Originalton fehlt im Export.')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    transfer=output.with_suffix('.partial.mp4');shutil.copyfile(temp,transfer);os.replace(transfer,output);temp.unlink()
    return {'file':str(output),'sha256':file_hash(output),'seconds':float(check['format']['duration']),'fps':fps,'smooth':smooth,'width':ow,'height':oh,'label':'KI-bearbeitet'}
