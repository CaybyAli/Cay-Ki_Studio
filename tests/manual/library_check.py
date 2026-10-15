"""Figure library end to end against the real dashboard (no GPU, no models).

Run: python tests/manual/library_check.py <empty dir>
Covers: save a figure from a project (design sheet + designed voice with its recipe),
create one by hand, edit, delete/restore, use counts, and giving a running project's figure
the image and/or voice of a library figure in every allowed and forbidden state.
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); work.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db


def png(path, color='0xffd23f'):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c={color}:s=512x768', '-frames:v', '1', str(path)], check=True)
    return path


def wav(path, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency=180:duration={seconds}', '-ar', '24000', '-ac', '1', str(path)], check=True)
    return path


def upload(kind, path):
    import urllib.request
    req = urllib.request.Request(f'{studio.url}/api/factory/assets?kind={kind}&name={path.name}', data=path.read_bytes(),
                                 headers={'X-Cay-Token': studio.token}, method='POST')
    with studio.opener.open(req, timeout=20) as resp: return json.load(resp)['id']


CAST = [{'name': 'Patrick', 'appearance': 'pink starfish, green shorts', 'personality': 'dreamy', 'voice_preset': 'man'},
        {'name': 'SpongeBob', 'appearance': 'yellow sponge', 'personality': 'eager', 'voice_preset': 'young_man'}]


def scene(who, line):
    return {'title': 'x', 'action': 'Patrick winkt.', 'location': 'Strand', 'camera': 'Halbnah', 'cast': [who],
            'dialogues': [{'speaker': who, 'text': line, 'emotion': 'fröhlich', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': None, 'render_seconds': 4, 'seconds': 4, 'variants': []}


try:
    folder = studio.root / '01_Projekte/Studio'
    sheet = png(folder / ('a' * 32) / '02_Bilder/patrick_design.png')
    voice = wav(folder / ('a' * 32) / '03_Stimmen/Profile/abc.wav')
    voice.with_suffix('.json').write_text(json.dumps({'description': 'An adult man, resonant voice. German cartoon dubbing voice actor.', 'seed': 4242, 'quality': {}}))
    episodes = [{'title': 'x', 'scenes': [scene('Patrick', 'Hallo SpongeBob!'), scene('SpongeBob', 'Hallo Patrick!'), scene('Patrick', 'Wo ist mein Stein?')]}]
    # Source project: designed Patrick (design sheet + designed voice)
    studio.project('a' * 32, 'voice_review', {'plan': {'cast': CAST, 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
                   'cast_refs': {'Patrick': str(sheet)}, 'voice_profiles': {'Patrick': {'file': str(voice), 'sha256': 'x', 'source': 'designed', 'voice_text': 'Na endlich!'}}},
                   {'look': 'clay'})

    code, fig = studio.call('/api/library/from-project', {'project': 'a' * 32, 'name': 'Patrick', 'label': 'Patrick Knete'})
    r.check('Aus Projekt speichern: Bild, Stimme und Stimmrezept übernommen', code == 200 and fig['image'] and fig['voice'] and fig['image_mode'] == 'exact'
            and fig['voice_design'] == {'instruction': 'An adult man, resonant voice. German cartoon dubbing voice actor.', 'seed': 4242}
            and fig['look'] == 'clay' and fig['label'] == 'Patrick Knete' and fig['voice_text'] == 'Na endlich!')
    image_file = db.execute('SELECT path FROM factory_assets WHERE id=?', (fig['image'],)).fetchone()[0]
    r.check('Bibliothek hat eigene Kopien (Projekt darf seine Dateien löschen)', Path(image_file) != sheet and Path(image_file).read_bytes() == sheet.read_bytes())
    code, _ = studio.call('/api/library/from-project', {'project': 'a' * 32, 'name': 'SpongeBob', 'label': 'SB'})
    r.check('Figur ohne Bild und Stimme wird abgelehnt', code == 409)

    own_image = upload('image', png(work / 'mr_krabs.png', '0xd03030')); own_voice = upload('voice', wav(work / 'krabs.wav', 4))
    code, krabs = studio.call('/api/library', {'name': 'Mr. Krabs', 'label': 'Krabs Cartoon', 'look': 'cartoon', 'traits': 'red crab',
                                               'image': own_image, 'image_mode': 'neutral', 'voice': own_voice, 'voice_text': 'Geld, Geld, Geld!'})
    r.check('Von Hand anlegen', code == 200 and krabs['image_mode'] == 'neutral' and krabs['voice_design'] is None)
    code, _ = studio.call('/api/library', {'name': 'Leer', 'label': 'Leer'})
    r.check('Ohne Bild und Stimme abgelehnt', code == 400)
    code, _ = studio.call('/api/library', {'name': 'X', 'label': 'X', 'image': 'f' * 32})
    r.check('Unbekannte Datei abgelehnt', code == 400)
    code, edited = studio.call(f'/api/library/{krabs["id"]}', {**{k: krabs[k] for k in ('name', 'look', 'traits', 'image', 'image_mode', 'voice', 'voice_text')}, 'label': 'Krabs Cartoon 2'}, 'PUT')
    r.check('Bearbeiten', code == 200 and edited['label'] == 'Krabs Cartoon 2')

    # Target project in figure review: give Patrick the library profile
    studio.project('b' * 32, 'cast_review', {'plan': {'cast': [dict(c) for c in CAST], 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
                   'cast_refs': {'Patrick': str(sheet), 'SpongeBob': str(sheet)}}, {'look': 'clay', 'cast_check': True})
    code, d = studio.call(f'/api/factory/{"b" * 32}/cast/profile', {'name': 'Patrick', 'library_id': fig['id']})
    p = next(x for x in d['idea']['participants'] if x['name'] == 'Patrick')
    r.check('Profil im Projekt: Bild und Stimme gesetzt, Design neu, Zustand Bilder', code == 200 and p['image'] == fig['image'] and p['voice'] == fig['voice']
            and p['image_mode'] == 'exact' and p['library_id'] == fig['id'] and p['voice_design']['seed'] == 4242
            and 'Patrick' not in d.get('cast_refs', {}) and d['state'] == 'pictures' and '2 Sätze' in d['phase'])
    code, lib = studio.call('/api/library')
    r.check('Bibliothek zählt die Verwendung', code == 200 and next(f for f in lib['figures'] if f['id'] == fig['id'])['uses'] == 1)

    studio.project('c' * 32, 'voice_review', {'plan': {'cast': [dict(c) for c in CAST], 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
                   'cast_refs': {'Patrick': str(sheet)}, 'voice_approval': 'x'}, {'look': 'clay'})
    code, _ = studio.call(f'/api/factory/{"c" * 32}/cast/profile', {'name': 'Patrick', 'library_id': fig['id'], 'image': True, 'voice': False})
    r.check('Bild in der Hörvorschau verweigert', code == 409)
    code, d = studio.call(f'/api/factory/{"c" * 32}/cast/profile', {'name': 'Patrick', 'library_id': fig['id'], 'image': False, 'voice': True})
    r.check('Nur Stimme in der Hörvorschau: wird neu eingesprochen, Freigabe entfernt', code == 200 and d['state'] == 'voicing' and not d.get('voice_approval')
            and 'Patrick' in d.get('cast_refs', {}))
    studio.project('d' * 32, 'rendering', {'plan': {'cast': [dict(c) for c in CAST], 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes}, {'look': 'clay'})
    code, _ = studio.call(f'/api/factory/{"d" * 32}/cast/profile', {'name': 'Patrick', 'library_id': fig['id'], 'image': False, 'voice': True})
    r.check('Während der Animation verweigert', code == 409)
    code, _ = studio.call(f'/api/factory/{"b" * 32}/cast/profile', {'name': 'Plankton', 'library_id': fig['id']})
    r.check('Unbekannte Figur abgelehnt', code == 404)

    code, _ = studio.call(f'/api/library/{krabs["id"]}', method='DELETE')
    code2, lib = studio.call('/api/library')
    r.check('Löschen blendet aus, Dateien bleiben', code == 200 and all(f['id'] != krabs['id'] for f in lib['figures'])
            and Path(db.execute('SELECT path FROM factory_assets WHERE id=?', (own_image,)).fetchone()[0]).is_file())
    code, back = studio.call(f'/api/library/{krabs["id"]}/restore', {})
    r.check('Wiederherstellen', code == 200 and not back.get('deleted'))
finally:
    studio.close()
r.done()
