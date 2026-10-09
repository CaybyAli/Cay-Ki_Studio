"""One shot budget for individual films and series; review before any image GPU work."""
import math
from typing import Literal
from factory_models import Strict
from pydantic import Field

POLICY = 12

def shot_count(duration):
    return max(3,min(15,math.ceil(float(duration)/6)))

DIRECTION = '''Beginne mitten im Konflikt: Die erste Einstellung zeigt eine konkrete Störung, ein Geheimnis oder eine riskante Entscheidung, keine Begrüßung oder Ortsbeschreibung. Ein klares Ziel und ein persönlicher Einsatz. Jede folgende Szene verändert die Lage durch eine Entscheidung und deren Konsequenz. Früh eine offene Frage setzen, Hinweise dosiert geben, mindestens zwei echte Eskalationen, dann eine vorbereitete überraschende Wendung. Der Schluss beantwortet die zentrale Frage; ein Cliffhanger darf eine neue Frage öffnen, nicht die Auflösung ersetzen. Spannung oder Humor entstehen aus sichtbaren Handlungen und Reaktionen statt Erklärdialog. Höchstens zwei Orte; jeder Orts- oder Zeitsprung braucht einen sichtbaren Anlass. Keine zufälligen neuen Menschen bei Lebensmittel-Figuren. Unterschiedliche Motive und Sprechhaltungen. Keine Beispiele wörtlich kopieren. Dialog nur, wenn er eine Absicht verfolgt oder eine Entscheidung erzwingt. Pro Sprechszene genau eine sichtbare sprechende Figur, Gegenansichten für Antworten; Zuhörer außerhalb des Bilds. So wird die Stimme eindeutig dem sichtbaren Mund zugeordnet. Stumme Szenen zeigen eine konkrete Handlung, Münder bleiben geschlossen.'''

class StoryReview(Strict):
    hook:str=Field(min_length=3,max_length=500)
    stakes:str=Field(min_length=3,max_length=500)
    escalation:str=Field(min_length=3,max_length=700)
    payoff:str=Field(min_length=3,max_length=500)
    problems:list[str]=Field(default_factory=list,max_length=6)

class StoryNote(Strict):
    scene:int=Field(ge=1,le=30)
    beat:Literal['setup','problem','attempt','turn','payoff']
    because:str=Field(min_length=3,max_length=400)

class StoryNotes(Strict):
    notes:list[StoryNote]=Field(min_length=3,max_length=30)

def apply_notes(episode,notes):
    """Annotate existing actions; never replace valid scenes or invent connections."""
    expected=set(range(1,len(episode['scenes'])+1))
    supplied=[n['scene'] for n in notes['notes']]
    if set(supplied)!=expected or len(supplied)!=len(expected):
        raise ValueError('Jede vorhandene Szene genau einmal einordnen.')
    for note in notes['notes']:
        scene=episode['scenes'][note['scene']-1]
        scene.update(beat=note['beat'],because=note['because'])
    return episode

def dialogue_errors(episode):
    errors=[]
    for i,s in enumerate(episode['scenes']):
        lines=s.get('dialogues') or ([{'speaker':s.get('speaker'),'text':s.get('dialogue')}] if s.get('dialogue') else [])
        if lines and (len(s.get('cast',[]))!=1 or len({l['speaker'] for l in lines})!=1):
            errors.append(f'Szene {i+1}: Für eindeutige Lippensynchronität nur einen sichtbaren Sprecher zeigen; Antwort als Gegenansicht planen.')
    return errors

def structure_errors(episode,duration,strict_dialogue=True):
    scenes=episode['scenes'];errors=[]
    if len(scenes)!=shot_count(duration):errors.append(f'Exakt {shot_count(duration)} Szenen erforderlich; geliefert: {len(scenes)}.')
    if not scenes:return errors
    beats=[s.get('beat') for s in scenes]
    if not any(b in ('problem','turn') for b in beats[:2]):errors.append('In den ersten zwei Szenen fehlt ein sichtbares Problem oder eine Wendung.')
    if beats[-1]!='payoff':errors.append('Die letzte Szene muss eine konkrete Auflösung/Pointe zeigen (beat=payoff).')
    if len(scenes)>=5 and 'turn' not in beats[1:-1]:errors.append('Vor dem Schluss fehlt eine vorbereitete Wendung (beat=turn).')
    if strict_dialogue:errors.extend(dialogue_errors(episode))
    for i,s in enumerate(scenes):
        if i and (not s.get('because','').strip() or 'nicht erkennbar' in s.get('because','').lower()):errors.append(f'Szene {i+1}: Konkreter Anschluss zur vorherigen Handlung fehlt.')
    return errors
