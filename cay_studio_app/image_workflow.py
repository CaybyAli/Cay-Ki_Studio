"""Local, allowlisted Flux2 image graph. No user-supplied executable graph."""
from pathlib import Path
import hashlib, json, struct, zlib

MAFIA_TRAITS = {
 'Cay': '23-year-old young adult. Preserve his exact eyeglasses, short beard and youthful face. Dark charcoal suit and black shirt. Do not age him.',
 'Coach': 'Preserve exactly this man\'s own face, hair and build. Dark suit, black shirt and black tie. Bare hands. Never give him Cay\'s face or eyeglasses.',
 'Ali': 'Preserve the approved face and very heavy build. Dark tailored mafia suit.',
 'Marli': 'Preserve the exact bald head, short beard and facial proportions. Dark suit, white shirt, black tie.',
 'Tim': 'Preserve this distinct man\'s face and very heavy build. Fictional character is short, about 1.60 metres. Dark suit and leather gloves.',
}
MODEL_FIELDS = {'70': ('UNETLoader','unet_name','flux-2-klein-4b-fp8.safetensors'),
                '71': ('CLIPLoader','clip_name','qwen_3_4b.safetensors'),
                '72': ('VAELoader','vae_name','flux2-vae.safetensors')}


def png_info(path):
    path = Path(path)
    if not 45 <= path.stat().st_size <= 40 * 1024 * 1024:
        raise ValueError('PNG-Dateigröße ungültig: ' + path.name)
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError('Keine PNG-Datei: ' + path.name)
    offset, size, pixels, ended = 8, None, False, False
    while offset + 12 <= len(data):
        length = struct.unpack('>I', data[offset:offset+4])[0]
        chunk = data[offset+4:offset+8]; payload = data[offset+8:offset+8+length]
        if offset+12+length > len(data): raise ValueError('Unvollständige PNG-Datei.')
        crc = struct.unpack('>I', data[offset+8+length:offset+12+length])[0]
        if zlib.crc32(chunk+payload) & 0xffffffff != crc: raise ValueError('Beschädigte PNG-Datei.')
        if chunk == b'IHDR':
            if length != 13: raise ValueError('Ungültiger PNG-Header.')
            size = struct.unpack('>II',payload[:8])
            if not all(0 < n <= 8192 for n in size) or size[0]*size[1] > 16_000_000: raise ValueError('Unerwartete Bildabmessungen.')
        if chunk == b'IDAT': pixels = True
        if chunk == b'IEND': ended = True; break
        offset += length + 12
    if not size or not pixels or not ended: raise ValueError('Unvollständiges PNG-Bild.')
    return {'width':size[0],'height':size[1],'sha256':hashlib.sha256(data).hexdigest()}


def image_prompt(scene, roles, brief, traits=None, style=''):
    traits = traits or {}
    identities = ' '.join(f'Reference image {i+1} identifies ONLY {role}. {traits.get(role, "Preserve the supplied character design.")}' for i, role in enumerate(roles))
    return (
      'One coherent frame, vertical 9:16. Visual style: ' + style + '. '
      'No captions, logos, montage, panels or multiple times in one image. '
      + identities + ' Never blend, swap or duplicate identities. No extra characters. '
      'Reference images establish character identity and costume, not the scene background. '
      'Keep eye-lines and physical geography consistent. Use a medium shot if multiple characters interact. '
      + ('Exactly one visible character and face. ' if len(roles)==1 else 'Keep each named character visually distinct. ' if roles else 'Environment or object detail, no visible characters. ')
      + 'Approved project context: ' + brief[:2500] + '\n'
      + json.dumps({k:scene[k] for k in ('title','location','action','camera','continuity')},ensure_ascii=False)
    )


def build_graph(prompt, references, seed, prefix, models=None):
    models = models or {key: entry[2] for key,entry in MODEL_FIELDS.items()}
    graph = {
      '61': {'class_type':'KSamplerSelect','inputs':{'sampler_name':'euler'}},
      '62': {'class_type':'Flux2Scheduler','inputs':{'steps':4,'width':['68',0],'height':['69',0]}},
      '63': {'class_type':'CFGGuider','inputs':{'cfg':1.0,'model':['70',0],'positive':['74',0],'negative':['76',0]}},
      '64': {'class_type':'SamplerCustomAdvanced','inputs':{'noise':['73',0],'guider':['63',0],'sampler':['61',0],'sigmas':['62',0],'latent_image':['66',0]}},
      '65': {'class_type':'VAEDecode','inputs':{'samples':['64',0],'vae':['72',0]}},
      '66': {'class_type':'EmptyFlux2LatentImage','inputs':{'width':['68',0],'height':['69',0],'batch_size':1}},
      '68': {'class_type':'PrimitiveInt','inputs':{'value':864}},
      '69': {'class_type':'PrimitiveInt','inputs':{'value':1536}},
      '70': {'class_type':'UNETLoader','inputs':{'unet_name':models['70'],'weight_dtype':'default'}},
      '71': {'class_type':'CLIPLoader','inputs':{'clip_name':models['71'],'type':'flux2','device':'default'}},
      '72': {'class_type':'VAELoader','inputs':{'vae_name':models['72']}},
      '73': {'class_type':'RandomNoise','inputs':{'noise_seed':seed}},
      '74': {'class_type':'CLIPTextEncode','inputs':{'text':prompt,'clip':['71',0]}},
      '76': {'class_type':'ConditioningZeroOut','inputs':{'conditioning':['74',0]}},
      '77': {'class_type':'SaveImage','inputs':{'filename_prefix':prefix,'images':['65',0]}},
    }
    positive, negative = ['74',0], ['76',0]
    for i, ref in enumerate(references):
        a,b,c,d,e = [str(120+5*i+j) for j in range(5)]
        graph[a]={'class_type':'LoadImage','inputs':{'image':ref}}
        graph[b]={'class_type':'ImageScaleToTotalPixels','inputs':{'image':[a,0],'upscale_method':'lanczos','megapixels':1.0,'resolution_steps':16}}
        graph[c]={'class_type':'VAEEncode','inputs':{'pixels':[b,0],'vae':['72',0]}}
        graph[d]={'class_type':'ReferenceLatent','inputs':{'conditioning':positive,'latent':[c,0]}}
        graph[e]={'class_type':'ReferenceLatent','inputs':{'conditioning':negative,'latent':[c,0]}}
        positive,negative=[d,0],[e,0]
    graph['63']['inputs'].update(positive=positive,negative=negative)
    return graph


def validate_nodes(info):
    required = {n['class_type'] for n in build_graph('test',['ref.png'],1,'test').values()}
    missing = sorted(required - info.keys())
    if missing: raise ValueError('Im vorhandenen ComfyUI fehlen Nodes: ' + ', '.join(missing))
    models = {}
    for node,(kind,field,basename) in MODEL_FIELDS.items():
        choices = info[kind].get('input',{}).get('required',{}).get(field,[[]])[0]
        if not isinstance(choices,list): raise ValueError('Modellauswahl nicht lesbar: ' + kind)
        matches = [x for x in choices if isinstance(x,str) and x.replace('\\','/').split('/')[-1] == basename]
        if len(matches)!=1: raise ValueError('Modell fehlt oder ist mehrdeutig: ' + basename)
        models[node]=matches[0]
    return models
