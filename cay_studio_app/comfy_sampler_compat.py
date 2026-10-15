"""CAY_STUDIO_COMPAT: a separate ComfyUI node; upstream files stay untouched.

Some WanWrapper releases pass None for disabled integer options. The upstream
model then compares these with zero (notably LongCat/RoPE reference counts).
Normalize only those documented disabled options, for this invocation only.
"""
import copy
import inspect

# Stays '13.0': it is a required graph input, and a new value would change the
# render key of every lip-sync window of projects already in progress. New
# abilities show up as optional inputs (cay_audio_cfg_steps) instead.
COMPAT_VERSION = '13.0'
COUNTS = {'longcat_num_ref_latents', 'longcat_num_cond_latents',
          'num_memory_frames', 'rope_negative_offset'}


def normalize_counts(signature, args, kwargs):
    bound = signature.bind_partial(*args, **kwargs)
    changed = False
    for name in COUNTS:
        parameter = signature.parameters.get(name)
        if parameter and name in bound.arguments and bound.arguments[name] is None:
            if type(parameter.default) is int:
                bound.arguments[name] = parameter.default
                changed = True
    return (bound.args, bound.kwargs) if changed else (args, kwargs)


def sampler_class():
    import nodes
    cls = nodes.NODE_CLASS_MAPPINGS.get('WanVideoSampler')
    if cls is None:
        raise RuntimeError('WanVideoWrapper fehlt. Animation einrichten und ComfyUI neu starten.')
    return cls


class CayWanVideoSampler:
    @classmethod
    def INPUT_TYPES(cls):
        schema = copy.deepcopy(sampler_class().INPUT_TYPES())
        schema['required']['cay_compatibility'] = ([COMPAT_VERSION], {'default': COMPAT_VERSION})
        # Audio guidance only in the first N steps (0 = every step, upstream behaviour).
        # At cfg 1 each guided step runs a second full transformer pass without audio
        # (nodes_sampler.py, wrapper 088128b): 4 steps = 8 passes, with N=1 only 5.
        schema.setdefault('optional', {})['cay_audio_cfg_steps'] = ('INT', {'default': 0, 'min': 0, 'max': 100})
        return schema

    RETURN_TYPES = ('LATENT', 'LATENT')
    RETURN_NAMES = ('samples', 'denoised_samples')
    FUNCTION = 'process'
    CATEGORY = 'Cay Studio'

    def process(self, **inputs):
        inputs.pop('cay_compatibility', None)
        guided = int(inputs.pop('cay_audio_cfg_steps', 0) or 0)
        embeds = inputs.get('multitalk_embeds')
        if guided > 0 and isinstance(embeds, dict) and not isinstance(embeds.get('audio_cfg_scale', 1.0), list):
            scale = float(embeds.get('audio_cfg_scale', 1.0)); steps = int(inputs.get('steps') or 0)
            # Copy: ComfyUI caches node outputs, the shared dict must stay unchanged.
            inputs['multitalk_embeds'] = {**embeds, 'audio_cfg_scale': [scale] * guided + [1.0] * max(1, steps + 1 - guided)}
        original = sampler_class()
        schema = original.INPUT_TYPES()
        for name, field in {**schema.get('required', {}), **schema.get('optional', {})}.items():
            options = field[1] if len(field) > 1 and isinstance(field[1], dict) else {}
            default = options.get('default')
            if inputs.get(name) is None and field[0] in ('INT', 'FLOAT', 'BOOLEAN') and default is not None:
                inputs[name] = default
        patcher = inputs.get('model')
        transformer = getattr(getattr(patcher, 'model', None), 'diffusion_model', None)
        handle = None
        if transformer is not None and hasattr(transformer, 'register_forward_pre_hook'):
            signature = inspect.signature(transformer.forward)
            def guard(module, args, kwargs):
                return normalize_counts(signature, args, kwargs)
            handle = transformer.register_forward_pre_hook(guard, with_kwargs=True)
        try:
            return original().process(**inputs)
        finally:
            if handle is not None:
                handle.remove()


NODE_CLASS_MAPPINGS = {'CayWanVideoSampler': CayWanVideoSampler}
NODE_DISPLAY_NAME_MAPPINGS = {'CayWanVideoSampler': 'Cay Studio · WanVideoSampler'}
