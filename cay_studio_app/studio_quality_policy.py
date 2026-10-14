"""Shared render policy; source timebase stays separate from delivery FPS."""
import math

RENDER_POLICY = 11
PROFILES = {
    'draft': {'width':480, 'height':832, 'steps':4, 'cfg':1.0},
    'fast': {'width':576, 'height':1024, 'steps':4, 'cfg':1.0},
    'balanced': {'width':576, 'height':1024, 'steps':24, 'cfg':3.5},
    'high': {'width':720, 'height':1280, 'steps':40, 'cfg':3.5},
}

def settings(idea):
    # Historical projects keep their delivery rate until explicitly changed.
    return {'fps':idea.get('fps',25), 'quality':idea.get('quality','balanced'),
            'lip_sync':idea.get('lip_sync','audio'), 'smooth':idea.get('smooth',False), 'speech_engine':idea.get('speech_engine','auto')}

def segments(seconds, fps, maximum=5):
    if fps not in (25,30):raise ValueError('25 oder 30 FPS wählen.')
    frames=round(seconds*fps);count=max(1,math.ceil(frames/(fps*maximum)))
    return [(frames//count+(i<frames%count))/fps for i in range(count)]

TALK_SEGMENT = 15  # seconds of lip-sync per ComfyUI prompt

def scene_segments(seconds, fps, talking):
    """One rule for production and progress: InfiniteTalk computes full 81-frame
    windows, so a talking scene is one prompt (up to TALK_SEGMENT); silent motion
    clips stay at the 5 s limit of the image-to-video model."""
    return segments(seconds, fps, TALK_SEGMENT if talking else 5)

def cadence(fps, smooth=False, source_fps=16):
    if fps not in (25,30):raise ValueError('25 oder 30 FPS wählen.')
    # Talking shots are rendered natively at 25 FPS: never interpolate them,
    # motion-compensated interpolation warps limbs. Only 16 FPS motion clips.
    if not smooth or abs(float(source_fps)-fps)<.01:return f'fps={fps}'
    # Short look-ahead only, subsequently trimmed to the requested frame count.
    # Each shot is processed independently so cuts never blend across scenes.
    pad=3/max(1,source_fps)
    return (f'tpad=stop_mode=clone:stop_duration={pad:.6f},'
            f'minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:'
            'vsbmc=1:scd=fdiff:scd_threshold=6')

def motion_direction(scene, lines, start, duration):
    """Timed visible behaviour; no claim of phoneme-level lip synchronization.

    Up to 0.15 this asked for "restrained conversational gestures" and listeners
    with closed mouths. Together with the 4-step fast models that produced
    standing figures that only moved their lips, which felt like slow motion.
    """
    cues=[]
    for line in lines:
        a=max(start,line.get('offset',0));b=min(start+duration,line.get('offset',0)+line['duration'])
        if b>a:
            cues.append(f'From {a-start:.2f} to {b-start:.2f} seconds only {line["speaker"]} speaks, with lively expressive acting: '
                        'animated face, hands and arms gesturing, body leaning and turning. Other characters react with body language and closed mouths.')
    return ('One continuous full-frame shot. No cut, no montage, no split screen, no border. '
            'No written language, letters, subtitles, captions, menus or watermark in any frame. '
            'Energetic real-time movement at normal speed, never slow motion: the characters keep moving the whole time with clear physical action. '
            'Camera: subtle handheld motion or a slow push-in. Stable facial proportions and materials. '
            'Preserve the approved starting image, costume, head shape, props and lighting. Keep all mouths closed when nobody speaks and show visible action or reaction instead. '
            + ' '.join(cues))
