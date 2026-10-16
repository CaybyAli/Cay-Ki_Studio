"""Conservative character identities shared by planning and scene repair."""
import re
import unicodedata
from pydantic import Field
from factory_models import Strict


def name_key(value):
    # Preserve punctuation: 'Ann-Marie' and 'Ann Marie' need not be one person.
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def resolve_name(value, allowed):
    key = name_key(value)
    exact = [name for name in allowed if name_key(name) == key]
    if len(exact) == 1:
        return exact[0]
    # Only a complete, unique first name is an alias. Never substring-match
    # 'Bibi Brombeere und unbekannter Gast', or silently guess an off-screen voice.
    short = [name for name in allowed if name_key(name).split(' ')[0] == key]
    return short[0] if len(short) == 1 else str(value or '').strip()


# Words that do not tell figures apart: titles, articles and the German cases of an epithet
# ("Larry der Hummer" / "Larry dem Hummer").
FILLER = {'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'sir', 'lady', 'herr', 'herrn', 'frau', 'fräulein',
          'the', 'der', 'die', 'das', 'dem', 'den', 'des', 'ein', 'eine', 'einen', 'von', 'van'}


def figure_words(value):
    words = re.sub(r"[.,;:!?\"'’„“”()]", ' ', unicodedata.normalize('NFKC', str(value or '')).casefold()).split()
    return tuple(w for w in words if w not in FILLER) or tuple(words)


TITLES = {'mr': 'mr', 'sir': 'mr', 'herr': 'mr', 'herrn': 'mr', 'mrs': 'mrs', 'ms': 'mrs', 'miss': 'mrs', 'lady': 'mrs',
          'frau': 'mrs', 'fräulein': 'mrs'}


def _title(value):
    words = re.sub(r"[.,]", ' ', unicodedata.normalize('NFKC', str(value or '')).casefold()).split()
    return next((TITLES[w] for w in words if w in TITLES), None)


def same_figure(a, b):
    """'SpongeBob' / 'SpongeBob Schwammkopf', 'Mr Krabs' / 'Mr. Krabs' / 'Krabs', 'Larry' / 'Larry der Hummer'.
    One name must be the other or its beginning: 'Perla Krabs' is not 'Mr. Krabs', 'Tim' is not 'Tims Oma',
    and 'Herr Müller' is not 'Frau Müller'."""
    if _title(a) and _title(b) and _title(a) != _title(b): return False
    a, b = figure_words(a), figure_words(b)
    if not a or not b: return False
    short, long = sorted((a, b), key=len)
    return long[:len(short)] == short


def merge_figure(name, known):
    """The one known name that means the same figure, else None (also when two would fit: 'Max' with 'Max Müller' and 'Max Schmidt')."""
    found = [k for k in known if same_figure(k, name)]
    return found[0] if len(found) == 1 else None


def canonical_scene(scene, allowed):
    scene['cast'] = list(dict.fromkeys(resolve_name(n, allowed) for n in scene.get('cast', [])))
    for line in scene.get('dialogues', []):
        line['speaker'] = resolve_name(line.get('speaker'), allowed)
    if scene.get('speaker'):
        scene['speaker'] = resolve_name(scene['speaker'], allowed)
    return scene


def scene_errors(scene, allowed):
    from factory_audio import turns
    unknown = [n for n in scene.get('cast', []) if n not in allowed]
    problems = ['Unbekannte Figuren: ' + ', '.join(repr(n) for n in unknown)] if unknown else []
    for line in turns(scene):
        if line['speaker'] not in scene.get('cast', []):
            problems.append('Sprecher ' + repr(line['speaker']) + ' fehlt in der Szenenbesetzung')
    return problems


def constrain_scene_schema(schema, allowed):
    shot = schema.get('$defs', {}).get('Shot', schema)
    properties = shot.get('properties', {})
    # These used to be optional in the JSON schema but mandatory in the later
    # story check, causing otherwise valid stories to fail repeatedly.
    if 'beat' in properties and 'because' in properties:
        shot['required']=list(dict.fromkeys([*shot.get('required',[]),'beat','because']))
        properties['because']['description']='Konkrete Ursache aus der vorherigen Handlung; in Szene 1 die Ausgangssituation.'
    if 'cast' in properties:
        if allowed:
            properties['cast']['items'] = {'type': 'string', 'enum': list(allowed)}
            properties['cast']['uniqueItems'] = True
        else:
            properties['cast']['maxItems'] = 0
        properties['speaker']['enum'] = ['', *allowed]
    line = schema.get('$defs', {}).get('DialogLine')
    if line:
        if allowed:
            line['properties']['speaker']['enum'] = list(allowed)
        else:
            properties['dialogues']['maxItems'] = 0
            properties['dialogue']['maxLength'] = 0
    return schema


def validate_header(result, data):
    required = [p['name'] for p in data.get('participants', [])]
    for person in result['cast']:
        person['name'] = resolve_name(person['name'], required)
    names = [p['name'] for p in result['cast']]
    if len({name_key(n) for n in names}) != len(names):
        raise ValueError('Figurennamen müssen eindeutig sein; Dopplung: ' + ', '.join(names))
    if data['characters'] == 'none' and names:
        raise ValueError('Ohne Figuren ist die Besetzung leer.')
    missing = set(required) - set(names)
    extra = set(names) - set(required)
    if missing or (data['characters'] == 'provided' and extra):
        raise ValueError('Besetzung korrigieren. Fehlende Namen: ' + ', '.join(sorted(missing)) +
                         '. Nicht erlaubte Ergänzungen: ' + ', '.join(sorted(extra) if data['characters'] == 'provided' else []) +
                         '. Vorgegebene Namen exakt übernehmen.')
    return result


class NamedCharacter(Strict):
    name: str = Field(min_length=1, max_length=60)
    quote: str = Field(min_length=1, max_length=600)


class SourceCast(Strict):
    characters: list[NamedCharacter] = Field(default_factory=list, max_length=24)


def evidenced_names(result, source):
    names = []
    for item in result['characters']:
        if item['quote'] not in source or item['name'] not in item['quote']:
            raise ValueError('Figurenname muss mit einem exakten Originalzitat belegt sein: ' + item['name'])
        if item['name'] not in names:
            names.append(item['name'])
    return names
