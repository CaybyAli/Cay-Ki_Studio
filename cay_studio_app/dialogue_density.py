"""Add relevant speech without discarding approved pictures or existing dialogue."""
import copy
import math
import re
from pydantic import Field
from factory_models import Strict, DialogLine
from factory_timing import scene_lines
from factory_cast import scene_errors
from story_policy import dialogue_errors
from lipsync_shots import split_episode, has_pictures


class AddedSceneLines(Strict):
    scene: int = Field(ge=1,le=30)
    lines: list[DialogLine] = Field(default_factory=list,max_length=4)


class DialogueAdditions(Strict):
    scenes: list[AddedSceneLines] = Field(min_length=1,max_length=30)


def word_count(episode):
    return sum(len(line['text'].split()) for scene in episode['scenes'] for line in scene_lines(scene))


def speech_requested(idea):
    return idea.get('characters')!='none' and not re.search(r'\b(?:stummfilm|rein visuell|ohne (?:dialoge?|sprache|worte))\b',idea.get('idea',''),re.I)


def apply_additions(episode, additions, names, lip_sync='audio'):
    result=copy.deepcopy(episode);seen=set()
    for item in additions['scenes']:
        index=item['scene']-1
        if index in seen or not 0<=index<len(result['scenes']):raise ValueError('Szenenzuordnung der Dialogergänzung ist nicht eindeutig.')
        seen.add(index);scene=result['scenes'][index];lines=copy.deepcopy(scene_lines(scene))
        for line in item['lines']:
            if any(old['speaker']==line['speaker'] and old['text']==line['text'] for old in lines):continue
            lines.append(line)
        if len(lines)>6:raise ValueError('Höchstens sechs Dialogbeiträge pro Szene.')
        if not item['lines']:continue
        scene['dialogues']=lines;scene['dialogue']='';scene['speaker']=''
        errors=scene_errors(scene,names)
        if errors:raise ValueError('; '.join(errors))
    if lip_sync=='audio':
        if not has_pictures(result):result=split_episode(result)
        else:
            # Picture caches are keyed by scene index; never split after images exist.
            errors=dialogue_errors(result)
            if errors:raise ValueError('; '.join(errors))
    result['dialogue_mode']='rich'
    return result


async def enrich(factory, document, episode, index, measured=None, force=False, request=None):
    duration=document['idea']['duration'];before=word_count(episode)
    desired=math.ceil(duration*1.95)
    if measured and measured.get('speech_share',1)<.84 and before:
        desired=min(math.ceil(duration*2.65),max(desired,math.ceil(before*.84/max(.1,measured['speech_share']))))
    silent=sum(not scene_lines(s) and bool(s.get('cast')) for s in episode['scenes'])
    if not force and before>=desired and silent<=1:return episode
    names=[p['name'] for p in document['plan']['cast']]
    if not names:return episode
    try:
        answer=await factory.llm(DialogueAdditions,
            'Ergänze ein vorhandenes deutsches Kurzfilm-Drehbuch um inhaltlich notwendige Dialoge. '
            'spine ist das Ziel des Films: jede neue Zeile treibt Haken, Steigerung, Wendung oder Pointe voran. '
            'Kurze Sätze, höchstens etwa acht Wörter je Beitrag. '
            'Antworte nur mit scenes: scene ist die vorhandene Szenennummer (ab 1), lines enthält ausschließlich NEUE Beiträge. '
            'Bestehende Dialoge, Bildhandlung, Figuren, Ort, Reihenfolge und Auflösung bleiben erhalten. '
            'Keine Wiederholungen, Füllwörter oder Beschreibungen des ohnehin sichtbaren Bilds. Ergänze Motive, Widerspruch, '
            'Verdacht, Entscheidungen oder konkrete Reaktionen passend zum Konflikt. Natürlich, emotional und knapp. '
            'Nur bereits in der jeweiligen Szene sichtbare Figuren sprechen lassen. Bei lip_sync=audio genau einen '
            'sichtbaren Sprecher je Szene beibehalten. Keine neuen Figuren oder Ereignisse erfinden. '
            'Verteile die zusätzlichen Wörter über die Handlung; nicht nur einen langen Schlussmonolog anhängen. '
            'Unterfülle Szenen zuerst. Insgesamt ungefähr target_total_words Wörter einschließlich bestehender Beiträge. '
            'Mindestens additional_words neue Wörter ergänzen, soweit die Handlung das sinnvoll trägt. '
            'Höchstens sechs alte und neue Beiträge zusammen pro Szene; pause_after meist 0.12 bis 0.25.',
            {'episode':episode,'episode_number':index+1,'series_cast':document['plan']['cast'],
             'spine':(document.get('spines') or {}).get(str(index)) or episode.get('spine'),
             'target_seconds':duration,'target_total_words':desired,
             'additional_words':max(0,desired-before),'lip_sync':document['idea'].get('lip_sync','audio'),
             'measured_timing':measured,'request':request})
        result=apply_additions(episode,answer,names,document['idea'].get('lip_sync','audio'))
    except (RuntimeError,ValueError) as error:
        result=copy.deepcopy(episode)
        result.setdefault('warnings',[]).append('Dialogergänzung nicht übernommen: '+str(error)[:250]+'. Vorhandene Texte und Bilder bleiben erhalten.')
        return result
    after=word_count(result)
    result['dialogue_density']={'before_words':before,'after_words':after,'target_words':desired,'policy':13}
    result['warnings']=[w for w in result.get('warnings',[]) if not w.startswith('Wenig Dialog:')]
    if after<duration*1.8:
        result.setdefault('warnings',[]).append(f'Wenig Dialog: {after} Wörter. Sprechanteil nach der Tonerzeugung prüfen; bei Bedarf Dialoge ergänzen.')
    return result
