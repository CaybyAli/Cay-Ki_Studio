"""Core ComfyUI UMT5 selection; native WanVideoWrapper files are not aliases."""
from pathlib import Path
import json,struct

CORE_TEXT='umt5_xxl_fp8_e4m3fn_scaled.safetensors'
CORE_NAMES=(CORE_TEXT,'umt5_xxl_fp16.safetensors')
WRAPPER_TEXT='umt5-xxl-enc-fp8_e4m3fn.safetensors'
TEXT_REPO='Comfy-Org/Wan_2.1_ComfyUI_repackaged'
TEXT_REVISION='8072741caa96024b736e668b98b4099d3156b1ff'
TEXT_SHA256='c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68'

def choose(info,comfy=None):
    options=info.get('CLIPLoader',{}).get('input',{}).get('required',{}).get('clip_name',[[]])[0]
    for name in CORE_NAMES:
        matches=[x for x in options if isinstance(x,str) and x.replace('\\','/').split('/')[-1]==name]
        if len(matches)>1:raise ValueError('Wan-Textmodell mehrfach vorhanden: '+name+'. Eindeutige Modelldatei verwenden.')
        if matches:
            if comfy is not None:
                try:validate_selected(comfy,matches[0])
                except (ValueError,OSError,TypeError):continue
            return matches[0]
    raise ValueError('Passendes Wan-Textmodell für ComfyUI fehlt. Unter Figurentausch die Einrichtung erneut starten; vorhandene Modelle bleiben erhalten. Die Datei '+WRAPPER_TEXT+' ist kein gleichwertiger Ersatz für den Core-Lader.')

def validate_file(path):
    """Read only the safetensors header, never tensor data or a GPU model."""
    path=Path(path)
    with path.open('rb') as f:
        size=path.stat().st_size;first=f.read(8)
        if len(first)!=8:raise ValueError('Textmodelldatei ist unvollständig.')
        length=struct.unpack('<Q',first)[0]
        if not 2<=length<=8*1024**2 or length+8>=size:raise ValueError('Textmodelldatei hat keinen gültigen Safetensors-Header.')
        header=json.loads(f.read(length))
    key='encoder.block.23.layer.1.DenseReluDense.wi_1.weight'
    if key not in header:raise ValueError('Falsches UMT5-Dateiformat für den ComfyUI-Core-Lader. Figurenstudio erneut einrichten.')
    shared=header.get('shared.weight',header.get('encoder.embed_tokens.weight',{}))
    if shared.get('shape')!=[256384,4096]:raise ValueError('Textmodell passt nicht zu Wan UMT5-XXL. Figurenstudio erneut einrichten.')
    for name,value in header.items():
        if name=='__metadata__':continue
        offsets=value.get('data_offsets',[])
        if len(offsets)!=2 or not 0<=offsets[0]<=offsets[1]<=size-8-length:raise ValueError('Textmodelldatei ist beschädigt oder unvollständig.')
    return True

def local_candidates(comfy):
    for name in CORE_NAMES:
        for directory in ('text_encoders','clip'):
            root=Path(comfy)/'models'/directory
            if root.is_dir():yield from sorted(root.rglob(name))

def local_ready(comfy):
    for path in local_candidates(comfy):
        try:
            if validate_file(path):return True
        except (ValueError,OSError,TypeError):pass
    return False

def validate_selected(comfy,name):
    # Extra model folders can be configured in ComfyUI. Only inspect a file
    # when its exact Core-listed name resolves inside the usual local folders.
    for directory in ('text_encoders','clip'):
        relative=Path(name.replace('\\','/'))
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Ungültiger Textmodellpfad.')
        root=Path(comfy)/'models'/directory;path=root/relative
        if path.is_file():validate_file(path);return
