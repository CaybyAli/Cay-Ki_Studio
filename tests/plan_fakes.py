"""A whole planning run without models: fixed answers per schema, every planner call recorded.

Used by test_own_script.py, and to record tests/fixtures/v18_ai_plan_reference.json from the
sources before 'Mein Drehbuch' (git 6ac0794): an idea without the new field must send the planner
exactly the same calls and end in exactly the same plan. Imports nothing from the app at module
level, so the same helper runs against older sources."""
import asyncio
import json

SCREENPLAY = '''TITEL: Der letzte Keks
# 1 | Großraumbüro | Lena hält den letzten Keks hoch, Markus schaut entsetzt
LENA [triumphierend]: Der letzte Keks gehört mir, ich hab ihn zuerst gesehen!
LENA [spöttisch]: Du hattest heute schon drei, Markus, ich hab mitgezählt.
MARKUS [empört]: Das waren Reiswaffeln! Die zählen überhaupt nicht als Kekse!
MARKUS [flehend]: Bitte, Lena, ich hatte heute noch gar nichts Süßes.
AKTION: Lena hält den Keks hoch über ihren Kopf, Markus springt danach.
# 2 | Teeküche | Die Keksdose steht offen, daneben Krümel
LENA [überrascht]: Moment mal. Warum ist die Dose plötzlich ganz leer?
MARKUS [verwirrt]: Keine Ahnung. Ich war die ganze Zeit hier bei dir!
LENA [wütend]: Dann war es die Praktikantin. Sie hat Krümel am Pullover!
AKTION: Markus und Lena starren gleichzeitig zur Tür der Teeküche.
'''


def answer(name, data):
    names = [p['name'] for p in data.get('participants', [])] if name == 'SeriesHeader' else []
    if name == 'SourceCast': return {'characters': []}
    if name == 'SeriesHeader':
        cast = [{'name': n, 'appearance': f'{n}, friendly figure with a clear silhouette', 'original': '', 'personality': 'lebhaft und direkt',
                 'voice': 'warm', 'voice_preset': 'woman' if i % 2 == 0 else 'man', 'voice_description': 'klar und lebendig'}
                for i, n in enumerate(names or ['Lena', 'Markus'])]
        return {'title': 'Planertitel', 'synopsis': 'Eine kurze Geschichte über einen Streit.', 'style': 'Warm clay look, soft studio light.',
                'visual': 'clay', 'mood': 'playful', 'cast': cast}
    if name == 'Outline':
        return {'title': 'Der letzte Keks', 'plot': 'Lena und Markus streiten um den letzten Keks.', 'ending': 'Die Praktikantin hat ihn.',
                'pickup': '', 'cliffhanger': ''}
    if name == 'StorySpine':
        return {'logline': 'Zwei Kollegen streiten um den letzten Keks.', 'viewer_question': 'Wer bekommt ihn?', 'hook': 'Lena hält den Keks hoch.',
                'goal': 'Den Keks bekommen', 'stakes': 'Der Nachmittag', 'escalations': ['Markus bettelt', 'Die Dose ist leer'],
                'twist': 'Die Praktikantin', 'payoff': 'Krümel am Pullover', 'final_moment': 'Beide starren zur Tür', 'running_gag': ''}
    if name == 'ShotVisuals':
        return {'shots': [{'shot': s['shot'], 'still': f'{s["visible"][0]} in {s["place"]}, expressive face' if s['visible'] else f'Wide view of {s["place"]}',
                           'motion': 'gestures clearly with both hands', 'camera': 'medium shot', 'ambience': 'room'} for s in data['shots']]}
    if name == 'SocialPost': return {'caption': 'Wer bekommt den letzten Keks?', 'hashtags': ['keks', 'büro', 'comedy']}
    raise AssertionError('Unerwartete Planerfrage: ' + name)


class FakePlanner:
    """Stands in for Factory.llm and Factory.write. write=False: any call to write fails the test."""
    def __init__(self, factory, write=True):
        self.calls = []; self.allow_write = write
        factory.llm = self.llm; factory.write = self.write

    async def llm(self, schema, instruction, data):
        self.calls.append(['llm', schema.__name__, instruction, data])
        return answer(schema.__name__, data)

    async def write(self, instruction, data, label='Drehbuch', check=None, attempts=3):
        self.calls.append(['write', label, instruction, data])
        if not self.allow_write: raise AssertionError(f'Die KI sollte keinen Text schreiben ({label}).')
        return SCREENPLAY


def plan(f, client, body, write=True):
    """Create the project through the API, then plan it as the worker does. Returns (project, planner)."""
    response = client.post('/api/factory', json=body)
    assert response.status_code == 200, response.text
    rid = response.json()['id']
    d = f.get(rid); d['preflight'] = {'checks': []}; f.save(d)
    planner = FakePlanner(f, write)
    asyncio.run(f.plan(f.get(rid)))
    return f.get(rid), planner


def record(f, client, body):
    """Everything the planner saw and everything planning produced, as plain JSON."""
    d, planner = plan(f, client, body)
    keep = {k: d.get(k) for k in ('idea', 'title', 'plan', 'episodes', 'screenplays', 'spines', 'state', 'source')}
    return json.loads(json.dumps({'calls': planner.calls, 'project': keep}, ensure_ascii=False, sort_keys=True))
