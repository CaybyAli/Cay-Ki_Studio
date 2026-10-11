"""Shot/reverse-shot for audio-driven lip sync: one visible speaker per shot.

The animation model moves one face per shot. Earlier versions rejected scenes
in which two visible characters talk. That pushed the planner and the dialogue
extension towards dropping dialogue entirely, which produced silent films.
Splitting keeps every line and gives each speaker a single shot instead.
Only used before any picture exists: picture and render caches are keyed by
scene index, so splitting later would attach old images to new shots.
"""
import copy
from factory_timing import scene_lines

MAX_SHOTS = 30


def needs_split(scene):
    lines = scene_lines(scene)
    if not lines: return False
    speakers = {line['speaker'] for line in lines}
    return len(speakers) != 1 or list(scene.get('cast', [])) != [lines[0]['speaker']]


def has_pictures(episode):
    return any(scene.get('variants') or scene.get('selected') for scene in episode['scenes'])


def runs(lines):
    groups = []
    for line in lines:
        if groups and groups[-1][0]['speaker'] == line['speaker']: groups[-1].append(line)
        else: groups.append([line])
    return groups


def split_scene(scene):
    if not needs_split(scene): return [scene]
    groups = runs(copy.deepcopy(scene_lines(scene))); cast = list(scene.get('cast', [])); shots = []
    for k, group in enumerate(groups):
        speaker = group[0]['speaker']; others = [n for n in cast if n != speaker]
        offscreen = ', '.join(others) or 'die andere Figur'
        shot = copy.deepcopy(scene)
        shot.update(cast=[speaker], dialogues=group, dialogue='', speaker='',
            title=(scene['title'] + ' · ' + speaker)[:100],
            camera=(f'Einzeleinstellung auf {speaker}, Schuss/Gegenschuss. Nur {speaker} im Bild, {offscreen} außerhalb.')[:250],
            animation_prompt=(f'Medium close-up of {speaker} talking to {offscreen} off-screen, natural conversational '
                              f'gestures and expression, only {speaker} in frame, same location and lighting.')[:1400],
            shot_part=[k + 1, len(groups)])
        shot['motion'] = [shot['animation_prompt']]
        if k:
            shot['action'] = (f'{speaker} reagiert und spricht zu {offscreen} außerhalb des Bildes. Gleiche Situation: '
                              + scene['action'])[:800]
            shot['because'] = ('Antwort auf ' + groups[k - 1][0]['speaker'])[:400]
            shot['sound_cues'] = []
        shots.append(shot)
    return shots


def split_episode(episode, maximum=MAX_SHOTS):
    """Return a copy in which every speaking shot shows exactly its speaker."""
    if has_pictures(episode): raise ValueError('Szenen mit fertigen Bildern werden nicht nachträglich aufgeteilt.')
    result = copy.deepcopy(episode)
    result['scenes'] = [shot for scene in episode['scenes'] for shot in split_scene(copy.deepcopy(scene))]
    if len(result['scenes']) > maximum:
        raise ValueError(f'Für eindeutige Lippensynchronität wären {len(result["scenes"])} Einstellungen nötig; höchstens {maximum}. '
                         'Weniger Sprecherwechsel pro Szene planen.')
    return result


def spoken_words(episode):
    return sum(len(line['text'].split()) for scene in episode['scenes'] for line in scene_lines(scene))


MISSING_MARK = 'DIALOG FEHLT'


def silent_by_accident(idea, cast, episodes):
    """True when people should speak but the script has no line at all."""
    from dialogue_density import speech_requested
    return bool(cast) and speech_requested(idea) and not any(spoken_words(ep) for ep in episodes)
