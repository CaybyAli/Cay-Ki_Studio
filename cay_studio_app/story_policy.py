"""One shot budget for individual films and series; review before any image GPU work."""
import math
from typing import Literal
from factory_models import Strict
from factory_timing import off_screen
from pydantic import Field

POLICY = 12

def shot_count(duration):
    return max(3,min(15,math.ceil(float(duration)/6)))

DIRECTION = '''Beginne mitten im Konflikt: Die erste Einstellung zeigt in den ersten zwei Sekunden eine konkrete Störung, ein Geheimnis oder eine riskante Entscheidung, keine Begrüßung oder Ortsbeschreibung. Ein klares Ziel und ein persönlicher Einsatz. Jede folgende Szene verändert die Lage durch eine Entscheidung und deren Konsequenz. Früh eine offene Frage setzen, Hinweise dosiert geben, mindestens zwei echte Eskalationen, dann eine vorbereitete überraschende Wendung. Der Schluss beantwortet die zentrale Frage; ein Cliffhanger darf eine neue Frage öffnen, nicht die Auflösung ersetzen. Tempo wie ein erfolgreicher TikTok-Kurzfilm: alle zwei bis drei Sekunden passiert sichtbar etwas Neues, etwa eine Bewegung, eine Reaktion, ein Gag oder ein neuer Bildausschnitt. Niemand steht nur da und redet: Wer spricht, macht dabei etwas mit dem eigenen Körper oder einem Requisit (zeigen, etwas werfen, zurückweichen). Berührungen zwischen Figuren nur in stummen Einstellungen, in denen beide sichtbar sind. Natürliche gesprochene Sätze, meist 5 bis 14 Wörter, ab und zu ein kurzer Ausruf; kein Telegrammstil. Spannung oder Humor entstehen aus sichtbaren Handlungen und Reaktionen statt Erklärdialog. Höchstens zwei Orte; jeder Orts- oder Zeitsprung braucht einen sichtbaren Anlass. Keine zufälligen neuen Menschen bei Lebensmittel-Figuren. Unterschiedliche Motive und Sprechhaltungen. Keine Beispiele wörtlich kopieren. Dialog nur, wenn er eine Absicht verfolgt oder eine Entscheidung erzwingt. Pro Sprechszene genau eine sichtbare sprechende Figur, Gegenansichten für Antworten; Zuhörer außerhalb des Bilds. So wird die Stimme eindeutig dem sichtbaren Mund zugeordnet. Stumme Szenen zeigen eine schnelle, konkrete Handlung, Münder bleiben geschlossen. Alles dient dem Ziel des Films in spine: Haken, Steigerungen, Wendung und Pointe kommen in dieser Reihenfolge vor.'''

class StorySpine(Strict):
    """The whole film in one view, written before any scene. Every later
    planning call gets it, so no step plans a scene without knowing the goal."""
    logline:str=Field(min_length=10,max_length=300)
    viewer_question:str=Field(min_length=5,max_length=200)
    hook:str=Field(min_length=5,max_length=300)
    goal:str=Field(min_length=3,max_length=300)
    stakes:str=Field(min_length=3,max_length=300)
    escalations:list[str]=Field(min_length=2,max_length=3)
    twist:str=Field(min_length=3,max_length=300)
    payoff:str=Field(min_length=3,max_length=300)
    final_moment:str=Field(min_length=3,max_length=300)
    running_gag:str=Field(default='',max_length=200)

SPINE_INSTRUCTION=('Du bist Showrunner für virale Kurzfilme auf TikTok und YouTube Shorts. Lege zuerst das Ziel dieser Folge fest, '
    'noch keine Szenen. logline: wer will was, was steht im Weg, was steht auf dem Spiel, in einem Satz. '
    'viewer_question: die Frage, wegen der man bis zum Ende schaut. hook: was in den ersten zwei Sekunden sichtbar passiert. '
    'goal und stakes konkret. escalations: zwei bis drei Steigerungen, jede schlimmer oder lustiger als die vorige. '
    'twist: eine vorbereitete Überraschung. payoff: die Auflösung der Hauptfrage. final_moment: der letzte Gag oder bei einer Serienfolge '
    'genau der vorgegebene Cliffhanger. running_gag optional. Alles sichtbar und filmbar, keine Erklärungen. '
    'Bekannte Figuren verhalten sich wie im Original. Originalvorgaben und Figuren aus series.cast sind verbindlich. Deutsch.')

class StoryReview(Strict):
    hook:str=Field(min_length=3,max_length=500)
    stakes:str=Field(min_length=3,max_length=500)
    escalation:str=Field(min_length=3,max_length=700)
    payoff:str=Field(min_length=3,max_length=500)
    problems:list[str]=Field(default_factory=list,max_length=6)

class StoryNote(Strict):
    scene:int=Field(ge=1,le=30)
    beat:Literal['setup','problem','attempt','turn','payoff','cliffhanger']
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
        if off_screen(s):
            # 0.18 reaction: silent motion of the listener; only the voice from off-screen speaks.
            if any(l['speaker'] in s.get('cast',[]) or l['speaker']!=s.get('voice_of') for l in lines):
                errors.append(f'Szene {i+1}: In einer Reaktion spricht nur {s.get("voice_of") or "die Stimme aus dem Off"}; die Figur im Bild hört zu.')
            continue
        if lines and (len(s.get('cast',[]))!=1 or len({l['speaker'] for l in lines})!=1):
            errors.append(f'Szene {i+1}: Für eindeutige Lippensynchronität nur einen sichtbaren Sprecher zeigen; Antwort als Gegenansicht planen.')
    return errors

def structure_errors(episode,duration,strict_dialogue=True,cliffhanger_ok=False):
    scenes=episode['scenes'];errors=[]
    if len(scenes)!=shot_count(duration):errors.append(f'Exakt {shot_count(duration)} Szenen erforderlich; geliefert: {len(scenes)}.')
    if not scenes:return errors
    beats=[s.get('beat') for s in scenes]
    if not any(b in ('problem','turn') for b in beats[:2]):errors.append('In den ersten zwei Szenen fehlt ein sichtbares Problem oder eine Wendung.')
    if cliffhanger_ok:
        # Series episode before the last: the main question is answered, then a new one opens.
        if beats[-1]!='cliffhanger' or 'payoff' not in beats[:-1]:errors.append('Serienfolge: zuerst die Hauptfrage auflösen (beat=payoff), die letzte Szene endet mit einem Cliffhanger (beat=cliffhanger).')
    elif beats[-1]!='payoff':errors.append('Die letzte Szene muss eine konkrete Auflösung/Pointe zeigen (beat=payoff).')
    if len(scenes)>=5 and 'turn' not in beats[1:-1]:errors.append('Vor dem Schluss fehlt eine vorbereitete Wendung (beat=turn).')
    if strict_dialogue:errors.extend(dialogue_errors(episode))
    for i,s in enumerate(scenes):
        if i and (not s.get('because','').strip() or 'nicht erkennbar' in s.get('because','').lower()):errors.append(f'Szene {i+1}: Konkreter Anschluss zur vorherigen Handlung fehlt.')
    return errors
