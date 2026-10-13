"""Turbo: SageAttention for the lip-sync animation (InfiniteTalk), optional.

Animation is 95 % of the measured time and at these frame sizes attention is
the expensive part. SageAttention computes attention with quantised kernels on
the RTX 4090. It is used only when all of this holds:
  1. installed into ComfyUI's own environment (pip --no-deps, torch untouched),
  2. a real CUDA probe returned correct values,
  3. ComfyUI was started after that (the wrapper imports it at start-up),
  4. ComfyUI offers 'sageattn' for the WanVideo model loader.
Any failed animation that used it switches Turbo off again; the next attempt
renders with the standard attention. Nothing else (images, silent motion
clips) uses Turbo.
"""
import json
import os
import time
from pathlib import Path

PACKAGE = 'sageattention==1.0.6'   # Triton kernels, no CUDA compiler needed
PROBE = r'''
import json, time, torch
from sageattention import sageattn
torch.manual_seed(0)
q, k, v = (torch.randn(1, 8, 512, 64, device='cuda', dtype=torch.float16) for _ in range(3))
start = time.time()
out = sageattn(q, k, v, tensor_layout='HND', is_causal=False)
ref = torch.nn.functional.scaled_dot_product_attention(q, k, v)
torch.cuda.synchronize()
error = (out.float() - ref.float()).abs().mean().item()
print(json.dumps({'mean_abs_error': error, 'seconds': time.time() - start, 'torch': torch.__version__}))
assert error < 0.02, error
'''


def path(runtime):
    return Path(runtime) / 'config' / 'turbo.json'


def read(runtime):
    try: return json.loads(path(runtime).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def write(runtime, data):
    target = path(runtime); target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.partial'); temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8'); os.replace(temp, target)


def comfy_started(runtime):
    """Start time of the ComfyUI process the launcher recorded, or None."""
    try:
        pid = json.loads((Path(runtime) / 'logs' / 'comfyui_prozess.json').read_text())['pid']
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        boot = next(float(l.split()[1]) for l in Path('/proc/stat').read_text().splitlines() if l.startswith('btime'))
        return boot + int(fields[19]) / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, KeyError, IndexError, StopIteration):
        return None


def state(runtime):
    data = read(runtime)
    if data.get('disabled'): return {'state': 'off', 'message': 'Turbo ist aus: ' + data.get('reason', 'abgeschaltet') + '.', **data}
    if not data.get('installed'): return {'state': 'missing', 'message': 'Turbo ist nicht eingerichtet.'}
    started = comfy_started(runtime)
    if not started or started < data['installed']:
        return {'state': 'restart', 'message': 'Turbo ist eingerichtet. Wirksam nach dem nächsten PC-Neustart und Cay_Studio_Starten.cmd.', **data}
    return {'state': 'active', 'message': 'Turbo ist aktiv für Sprechszenen.', **data}


def attention(runtime, info):
    """Attention mode for the WanVideo loader: 'sageattn' only when proven and offered."""
    if state(runtime)['state'] != 'active': return 'sdpa'
    try:
        fields = info['WanVideoModelLoader']['input']
        options = {**fields.get('required', {}), **fields.get('optional', {})}['attention_mode'][0]
    except (KeyError, IndexError, TypeError):
        return 'sdpa'
    return 'sageattn' if isinstance(options, list) and 'sageattn' in options else 'sdpa'


def disable(runtime, reason):
    data = read(runtime); data.update(disabled=True, reason=reason[:300], disabled_at=time.time()); write(runtime, data)


async def setup(runtime, python, log):
    """pip install without touching torch, then a real CUDA probe. Raises on failure."""
    import asyncio
    with Path(log).open('ab') as stream:
        for args in ([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps', PACKAGE],
                     [str(python), '-c', PROBE]):
            process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(process.communicate(), 900)
            stream.write(out)
            if process.returncode:
                raise RuntimeError(out.decode(errors='replace')[-900:])
    probe = json.loads(out.decode().strip().splitlines()[-1])
    write(runtime, {'installed': time.time(), 'package': PACKAGE, 'probe': probe})
    return probe
