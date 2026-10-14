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

def motion_direction_v16(scene, lines, start, duration):
    """0.16 text, kept only so projects already rendering keep their cached windows."""
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

def motion_direction(scene, lines, start, duration):
    """Visible behaviour for one shot. The text conditioning is global for every
    81-frame window, so per-second cues do nothing; negatives do nothing at cfg 1.

    0.16 asked for movement "the whole time" in speaking shots. With up to 4 s
    of silence after each line that meant mouths and hands moving without any
    voice (Cay: "bewegen den Mund oder die Hände ohne dass Text da ist").
    0.17: gestures while the voice speaks, stillness with a closed mouth in the
    pauses, and only the visible figure is named."""
    names = list(scene.get('cast') or [])
    frame = (f'Exactly one character in the whole frame: {names[0]}. No other characters or figures anywhere, also not in the background. '
             if len(names) == 1 else f'Only {" and ".join(names)} in the frame, nobody else. ' if names else 'No characters in the frame. ')
    base = ('One continuous full-frame shot. No cut, no montage, no split screen, no border. '
            'No written language, letters, subtitles, captions, menus or watermark in any frame. ' + frame +
            'Stable facial proportions, materials, costume, head shape, props and lighting as in the starting image. Normal real-time speed, never slow motion. ')
    if lines:
        speaker = lines[0]['speaker']
        return base + (f'{speaker} talks with an expressive face and natural hand gestures while the voice speaks. '
                       'In pauses and after the last word the mouth stays closed and the body is calm, only breathing and a small reaction. '
                       'Camera: steady, a subtle slow push-in.')
    return base + ('Energetic, clearly visible physical action at normal speed. All mouths stay closed, nobody talks. '
                   'Camera: dynamic but smooth, following the action.')
