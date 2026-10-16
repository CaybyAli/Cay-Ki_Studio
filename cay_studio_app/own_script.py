"""Mein Drehbuch (0.18): Cay's own script, filmed word for word.

Cay: "Dass ich selber ein komplettes Skript einfügen kann … ohne dass die KI viel ändert. Dass sie
das Skript liest und dann weiß, was geschehen soll." Markdown or plain text (.md, .txt, pasted);
no PDF: reading it needs a new package and loses the line structure.

The studio's screenplay format (screenplay.FORMAT) is already human-writable. read() also accepts
what a person naturally writes: '# Titel', '## Folge 1: Titel', '### Szene 2 – Küche – Oma steht vor
dem Teller' or 'Szene 2: Küche', 'OMA (wütend): Text', 'Oma [wütend]: Text', 'Oma: (wütend) Text',
a name alone in capitals above its text, 'AKTION: …', 'Aktion: …', '[Aktion: …]', a line in
parentheses, 'FIGUR: Frau Müller – Aussehen und Wesen' and a '## Figuren' list. It turns that into
the internal format deterministically, without any model. Every spoken word stays as written: only
surrounding whitespace, quotes and Markdown emphasis go; a stage direction in parentheses or
brackets becomes the mood (one of screenplay.EMOTIONS, default 'ruhig') and is never spoken. Every
problem carries its line number; blocking ones stop the film before anything is planned.

Planning (factory.plan with idea.story == 'script'): the cast is exactly the script's figures, the
episodes are its '## Folge' parts, screenplay.write_episode keeps the normalized text as the final
screenplay (no draft, no Script Doctor, no invented AKTION), and the planner only writes the image
and motion text of the shots.
"""
import difflib
import math
import re
import screenplay
from factory_cast import name_key
from factory_models import MAX_CAST, Outline
from factory_timing import HEAD, TAIL, REACTION_TAIL, REACTION_MIN, ACTION_BASE, ESTABLISH_BASE
from story_source import HEADING, manifest

MIN_SECONDS, MAX_SECONDS = 15, 90
MAX_SPOKEN = 240            # screenplay.parse keeps 240 characters of a spoken line
MAX_ACTION = 400            # … and 400 of an AKTION line
PDF_MESSAGE = ('PDF kann das Studio nicht zuverlässig lesen. Öffne das PDF, kopiere den Text und füge ihn hier ein, '
               'oder speichere es als .txt.')

# Delivery words people write in parentheses, mapped to the nearest of screenplay.EMOTIONS.
MOODS = {
    'fröhlich': ('fröhlich', 'froh', 'lach', 'lächel', 'glücklich', 'heiter', 'vergnügt', 'gut gelaunt', 'kicher', 'freu', 'grins', 'erleichtert',
                 'verliebt', 'schwärm', 'happy', 'laugh'),
    'begeistert': ('begeister', 'aufgeregt', 'euphor', 'enthusias', 'hingerissen', 'jubel', 'excited'),
    'wütend': ('wütend', 'wut', 'sauer', 'böse', 'zorn', 'aufgebracht', 'empört', 'verärger', 'ärger', 'grimmig', 'angry'),
    'schreiend': ('schrei', 'brüll', 'ruft', 'rufend', 'laut', 'kreisch', 'schrill', 'shout', 'yell', 'scream'),
    'ängstlich': ('ängstlich', 'angst', 'nervös', 'unsicher', 'zöger', 'zaghaft', 'verängstigt', 'besorgt', 'zitter', 'stotter',
                  'eingeschüchtert', 'kleinlaut', 'afraid', 'scared', 'nervous'),
    'panisch': ('panisch', 'panik', 'hektisch', 'entsetzt', 'außer sich', 'verzweifelt', 'panic'),
    'traurig': ('traurig', 'wein', 'schluchz', 'betrübt', 'niedergeschlagen', 'enttäuscht', 'deprimiert', 'bedrückt', 'melanchol', 'müde',
                'erschöpft', 'sad', 'cry'),
    'flüsternd': ('flüster', 'leise', 'raun', 'geheimnisvoll', 'wisper', 'tuschel', 'whisper'),
    'drohend': ('droh', 'bedrohlich', 'finster', 'gefährlich', 'warnend', 'threat'),
    'spöttisch': ('spött', 'spott', 'ironisch', 'sarkast', 'frech', 'höhnisch', 'herablassend', 'zynisch', 'neck', 'schnippisch', 'verschmitzt', 'mock'),
    'überrascht': ('überrasch', 'erstaunt', 'verblüfft', 'erschrocken', 'schockiert', 'perplex', 'ungläubig', 'staun', 'neugierig',
                   'surpris', 'shock'),
    'triumphierend': ('triumph', 'stolz', 'siegessicher', 'selbstgefällig', 'überlegen', 'siegreich', 'proud'),
    'flehend': ('fleh', 'bittend', 'bettel', 'inständig', 'kläglich', 'plead'),
    'genervt': ('genervt', 'gereizt', 'augenroll', 'entnervt', 'ungeduldig', 'gelangweilt', 'mürrisch', 'grummel', 'seufz', 'trotzig', 'annoyed'),
    'verwirrt': ('verwirrt', 'ratlos', 'verständnislos', 'irritiert', 'durcheinander', 'verdutzt', 'fragend', 'skeptisch', 'misstrauisch', 'confus'),
    'ruhig': ('ruhig', 'sachlich', 'neutral', 'normal', 'gelassen', 'entspannt', 'nachdenklich', 'sanft', 'ernst', 'calm'),
}


def emotion_for(raw):
    """(emotion, known): the nearest of screenplay.EMOTIONS, 'ruhig' when nothing fits."""
    text = ' '.join(str(raw or '').casefold().split())
    if not text: return 'ruhig', True
    if text in screenplay.EMOTIONS: return text, True
    for candidate in (text, text.replace('ae', 'ä').replace('oe', 'ö').replace('ue', 'ü')):
        hits = [(candidate.find(stem), -len(stem), mood) for mood, stems in MOODS.items() for stem in stems if stem in candidate]
        if hits: return min(hits)[2], True
    close = difflib.get_close_matches(text, screenplay.EMOTIONS, n=1, cutoff=.75)
    return (close[0], True) if close else ('ruhig', False)


# Labels that are never a figure's name, and where their line goes.
ACTION_LABELS = {'aktion', 'action', 'handlung'}
VISUAL = {'kamera', 'licht', 'bild', 'einstellung', 'beschreibung', 'regie', 'zeit'}       # into the scene description
SOUND = {'musik', 'ton', 'sound', 'geräusch', 'geräusche', 'schnitt', 'off', 'untertitel'}   # the studio mixes itself
NOTE_LABELS = {'hinweis', 'hinweise', 'notiz', 'notizen', 'anmerkung', 'tipp', 'achtung', 'wichtig', 'info', 'beispiel', 'zum beispiel', 'text'}
LOGLINE_LABELS = {'logline', 'inhalt', 'zusammenfassung', 'idee'}
KEYWORDS = ACTION_LABELS | VISUAL | SOUND | NOTE_LABELS | LOGLINE_LABELS | {
    'titel', 'title', 'figur', 'figuren', 'szene', 'scene', 'ort', 'folge', 'episode', 'innen', 'aussen', 'außen', 'ende'}
FIGURE_SECTIONS = {'figuren', 'besetzung', 'personen', 'rollen', 'cast', 'charaktere', 'figurenliste', 'die figuren', 'mitwirkende'}
NOTE_SECTIONS = {'hinweise', 'hinweis', 'notizen', 'notiz', 'anmerkungen', 'anmerkung', 'kommentar', 'kommentare', 'regieanweisungen',
                 'info', 'infos', 'format', 'so funktioniert es', 'erklärung', 'anleitung'}
NEUTRAL_SECTIONS = {'drehbuch', 'skript', 'script', 'handlung', 'story', 'geschichte'}
NARRATORS = {'erzähler', 'erzählerin', 'sprecher', 'sprecherin', 'stimme', 'off-stimme', 'erzählstimme', 'narrator'}
# Capitalised sentence starters: 'Um 8 Uhr: …' or 'Das Problem: …' is prose, unless the name speaks twice or is a FIGUR.
STARTERS = {'um', 'am', 'im', 'in', 'als', 'wenn', 'dann', 'da', 'und', 'aber', 'doch', 'nach', 'vor', 'bei', 'mit', 'zum', 'zur', 'auf', 'es',
            'er', 'sie', 'wir', 'ich', 'du', 'ihr', 'das', 'der', 'die', 'den', 'dem', 'ein', 'eine', 'einer', 'plötzlich', 'später', 'danach',
            'jetzt', 'heute', 'morgen', 'gestern', 'hier', 'dort', 'so', 'also', 'nur', 'noch', 'schon', 'wie', 'was', 'wer', 'wo', 'warum',
            'merke', 'endlich', 'kurz', 'währenddessen', 'inzwischen', 'unterdessen', 'zuerst', 'schließlich', 'alle'}
PARTICLES = {'von', 'van', 'de', 'der', 'die', 'das', 'den', 'dem', 'la', 'le', 'of', 'the', 'und', 'zu', 'vom', 'zum', 'zur', 'al', 'el', 'di', 'da', 'du'}
TRANSITION = re.compile(r'(?i)^(?:ende|the end|fin|schluss|abblende|aufblende|schwarzbild|schnitt|cut to|fade in|fade out|blende|vorhang)\W*$')
LABEL = re.compile(r'^(?P<name>[^\W\d_][^:\[\]()#|"„“»«]{0,59}?)\s*(?:[\[(](?P<mood>[^\[\]()]{1,60})[\])])?\s*:\s*(?P<text>.*)$')
CUE = re.compile(r"^(?P<name>[^\W\d_][^\W_]*(?:[ .'’-]+[^\W_]+){0,3})\s*(?:[\[(](?P<mood>[^\[\]()]{1,60})[\])])?$")
# 'Szene 2 – Küche – …', 'Szene 2: Küche', 'Szene: Küche' (as a heading also 'Szene' alone); never 'Szenenwechsel'.
SCENE = re.compile(r'(?i)^(?:szene|scene|sz\.)(?![^\W\d_])\s*(?:(?P<number>\d+)\s*[:.\-–—|]?|[:\-–—|])\s*(?P<rest>.*)$')
SCENE_HEADING = re.compile(r'(?i)^(?:szene|scene|sz\.)(?![^\W\d_])\s*(?P<number>\d+)?\s*[:.\-–—|]?\s*(?P<rest>.*)$')
SLUG = re.compile(r'^(?:INNEN/AUSSEN|INNEN|AUSSEN|AUßEN|INT|EXT)\b\.?\s*[-–—/.:]?\s*(?P<rest>.+)$')
BEAT = re.compile(r'^\d+\s*\|')
WRAPPED = re.compile(r'^(?:\((?P<a>[^()]*)\)|\[(?P<b>[^\[\]]*)\]|\*(?!\s)(?P<c>[^*]+?)(?<!\s)\*|_(?!\s)(?P<d>[^_]+?)(?<!\s)_)$')
DIRECTION = re.compile(r'\(([^()]*)\)|\[([^\[\]]*)\]')
QUOTES = (('"', '"'), ('„', '“'), ('„', '”'), ('“', '”'), ('”', '”'), ('»', '«'), ('«', '»'), ('‚', '‘'), ("'", "'"), ('›', '‹'))
SEPARATOR = re.compile(r'\s+[–—-]\s+|\s*\|\s*')


def _clean(raw):
    """One row without Markdown noise: bold, code, quote markers, list bullets."""
    row = re.sub(r'\*\*|__|`', '', raw).strip()
    row = re.sub(r'^(?:>\s*)+', '', row).strip()
    if not WRAPPED.match(row): row = re.sub(r'^(?:[-*+•–]\s+)', '', row).strip()
    return row


def _display(name):
    """'FRAU MÜLLER' -> 'Frau Müller', 'MR. KRABS' -> 'Mr. Krabs'; mixed case stays as written."""
    name = ' '.join(name.split()).strip(' *_')
    if name != name.upper() or not any(c.isalpha() for c in name): return name
    return re.sub(r'[^\W\d_]+', lambda m: m.group(0)[:1] + m.group(0)[1:].lower(), name)


def _is_name(name, counts, known):
    key = name_key(name)
    if key in known: return True
    words = name.split()
    if not 1 <= len(words) <= 4 or len(name) > 40 or key in KEYWORDS: return False
    if not words[0][:1].isupper() or words[0].casefold().rstrip('.') in KEYWORDS: return False
    if any(not (w[:1].isupper() or w.isdigit() or (i and w.casefold() in PARTICLES)) for i, w in enumerate(words)): return False
    return name == name.upper() or words[0].casefold() not in STARTERS or counts.get(key, 0) >= 2


def _speech(text):
    """(spoken, directions): parentheses and brackets are never spoken, quotes and emphasis go.
    The final strips mirror screenplay.parse, so the stored line is exactly what it reads back."""
    directions, spoken = [], text
    while DIRECTION.search(spoken):
        directions += [(m.group(1) if m.group(1) is not None else m.group(2)).strip() for m in DIRECTION.finditer(spoken)]
        spoken = DIRECTION.sub(' ', spoken)
    for mark in ('*', '_'):
        spoken = re.sub(r'(?<![\w%s])\%s(?=\S)([^%s]+?)(?<=\S)\%s(?![\w%s])' % ((mark,) * 5), r'\1', spoken)
    spoken = ' '.join(spoken.split())
    if directions: spoken = re.sub(r'\s+([,.!?;:…])', r'\1', spoken)
    for a, b in QUOTES:
        inner = spoken[len(a):-len(b)] if len(spoken) >= 2 else ''
        if len(spoken) >= 2 and spoken.startswith(a) and spoken.endswith(b) and a not in inner and b not in inner:
            spoken = inner.strip(); break
    spoken = spoken.strip().strip('*').strip().strip('"„“').strip()
    return spoken, [x for x in directions if x]


def _pieces(text, limit):
    """Split a too long text at sentence ends (else at a comma, else at a space); no word changes."""
    out, rest = [], text
    while len(rest) > limit:
        window = rest[:limit + 1]
        cut = (max((m.end() for m in re.finditer(r'[.!?…]+["“”»«]?\s', window)), default=0)
               or max((m.end() for m in re.finditer(r'[,;:–—]\s', window)), default=0) or window.rfind(' ') + 1 or limit)
        out.append(rest[:cut].strip()); rest = rest[cut:].strip()
    return out + ([rest] if rest else [])


def _figure_line(text):
    """'Frau Müller – 60, streng' / 'Frau Müller: …' / 'Frau Müller (60, streng)' / 'Frau Müller' -> (name, description)."""
    text = text.strip()
    m = re.match(r'^(?P<name>[^()\[\]:–—|]{1,60}?)\s*\((?P<desc>[^()]*)\)\s*[:.]?\s*(?P<more>.*)$', text)
    if m and not SEPARATOR.search(m.group('name')):
        return m.group('name').strip(' *_-'), ' '.join(x.strip() for x in (m.group('desc'), m.group('more')) if x.strip())
    parts = SEPARATOR.split(text, 1)
    if len(parts) == 1 and ':' in text: parts = text.split(':', 1)
    if len(parts) == 1 and ',' in text and len(text.split(',', 1)[0].split()) <= 3: parts = text.split(',', 1)
    return parts[0].strip(' *_-'), (parts[1].strip() if len(parts) > 1 else '')


def _scene_parts(rest):
    """'Küche – Oma steht vor dem Teller' -> ('Küche', 'Oma steht vor dem Teller'); 'Küche: …' too."""
    rest = rest.strip(' :.-–—|')
    parts = [p.strip() for p in SEPARATOR.split(rest, 1)]
    if len(parts) == 1 and ':' in rest: parts = [p.strip() for p in rest.split(':', 1)]
    return parts[0], (parts[1] if len(parts) > 1 else '')


class _Reader:
    """One pass over the rows; scenes and items keep their line numbers for the problems."""
    def __init__(self, rows):
        self.rows = rows; self.title = ''; self.figures = {}; self.episodes = []; self.problems = []; self.preface = []
        self.section = None; self.cue = None; self.folgen = any(HEADING.match(r) for r in rows); self.counts = {}
        for raw in rows:
            m = LABEL.match(_clean(raw))
            if m: self.counts[name_key(m.group('name'))] = self.counts.get(name_key(m.group('name')), 0) + 1

    def problem(self, number, text, blocking=False):
        self.problems.append({'line': number, 'text': (f'Zeile {number}: ' if number else '') + text, 'blocking': blocking})

    def ep(self):
        """The current episode; a film without 'Folge' headings is one episode. None before 'Folge 1'."""
        if self.episodes: return self.episodes[-1]
        if self.folgen: return None
        return self.episode()

    def episode(self, number=None, title='', line=None):
        self.episodes.append({'number': number or len(self.episodes) + 1, 'title': title, 'line': line, 'scenes': [], 'logline': []})
        return self.episodes[-1]

    def scene(self, line=None, place='', what='', explicit=True):
        self.section = None
        ep = self.ep()
        if ep is None:
            self.problem(line, 'Die Szene steht vor „Folge 1“ und gehört zu keiner Folge. Schreib „## Folge 1“ davor oder verschiebe sie.', True)
            return {'place': '', 'what': [], 'items': [], 'explicit': explicit}
        ep['scenes'].append({'place': place, 'what': [what] if what else [], 'line': line, 'items': [], 'explicit': explicit})
        return ep['scenes'][-1]

    def current(self, number, kind):
        """The scene that takes a spoken or silent line, or None (before 'Folge 1' in a series)."""
        ep = self.ep()
        if ep is None:
            self.problem(number, f'{kind} steht vor „Folge 1“ und gehört zu keiner Folge. Schreib „## Folge 1“ davor oder verschiebe den Text.', True)
            return None
        return ep['scenes'][-1] if ep['scenes'] else self.scene(explicit=False)

    def describe(self, number, text, scene_only=False):
        """Prose: the description of a scene that has no line yet (or of the episode), else a visible action."""
        ep = self.ep()
        if ep is None: self.preface.append(text); return
        scene = ep['scenes'][-1] if ep['scenes'] else None
        if scene is None: ep['logline'].append(text); return
        if not scene['items'] or scene_only: scene['what'].append(text); return
        self.action(number, text)

    def action(self, number, text):
        text = ' '.join(text.split()).strip('*').strip()
        scene = self.current(number, 'Die Handlung') if text else None
        if scene is None: return
        pieces = _pieces(text, MAX_ACTION)
        if len(pieces) > 1: self.problem(number, f'Sehr lange Handlung, als {len(pieces)} stumme Einstellungen gezeigt.')
        scene['items'] += [{'kind': 'action', 'text': p, 'line': number} for p in pieces]

    def say(self, number, raw_name, mood, text):
        scene = self.current(number, 'Der Satz')
        if scene is None: return
        spoken, directions = _speech(text)
        name = ' '.join(raw_name.split()).strip(' *_')
        if not spoken:
            if directions: self.action(number, f'{_display(name)} {directions[0]}'); return
            self.problem(number, f'„{name}:“ ohne Text, übersprungen.'); return
        wish = mood if mood is not None else (directions[0] if directions else '')
        emotion, known = emotion_for(wish)
        if not known: self.problem(number, f'Sprechhaltung „{wish}“ kennt das Studio nicht, gesprochen wird „ruhig“.')
        pieces = _pieces(spoken, MAX_SPOKEN)
        if len(pieces) > 1: self.problem(number, f'Sehr langer Satz, in {len(pieces)} Teile geteilt. Die Wörter bleiben gleich.')
        scene['items'] += [{'kind': 'line', 'name': name, 'emotion': emotion, 'text': p, 'line': number} for p in pieces]

    def figure(self, number, text, listed=False):
        name, description = _figure_line(text)
        if listed and not _is_name(name, {}, self.figures): return          # prose in a '## Figuren' list
        if not name or len(name) > 60 or name_key(name) in KEYWORDS:
            self.problem(number, 'FIGUR-Zeile ohne Namen, übersprungen. So geht es: „FIGUR: Oma – 70 Jahre, Schürze, streng“.'); return
        key = name_key(name); old = self.figures.get(key)
        if old: old['description'] = ' '.join(x for x in (old['description'], description) if x)[:1500]; return
        self.figures[key] = {'name': _display(name), 'description': description[:1500], 'line': number, 'declared': True}

    def flush_cue(self):
        if self.cue:
            number, name, mood, text = self.cue; self.cue = None
            if text.strip(): self.say(number, name, mood, text)
            else: self.problem(number, f'„{name}“ ohne Text, übersprungen.')

    def heading(self, number, level, content):
        content = content.strip().strip('*_ ').strip()
        key = name_key(content.rstrip(':'))
        self.section = None
        if BEAT.match(content):                                                    # the internal '# 1 | Ort | was passiert'
            place, _, what = [x.strip() for x in content.split('|', 1)[1].partition('|')]
            self.scene(number, place, what); return
        m = SCENE_HEADING.match(content)
        if m: place, what = _scene_parts(m.group('rest')); self.scene(number, place, what); return
        m = SLUG.match(content)
        if m: place, what = _scene_parts(m.group('rest')); self.scene(number, _display(place), what); return
        if key in FIGURE_SECTIONS: self.section = 'figures'; return
        if key in NOTE_SECTIONS: self.section = 'notes'; return
        if key in NEUTRAL_SECTIONS: return
        if not self.title and not self.episodes and level <= 2:
            self.title = re.sub(r'(?i)^titel\s*:\s*', '', content)[:100]; return
        if level >= 3:
            place, what = _scene_parts(content); self.scene(number, place, what); return
        self.problem(number, f'Überschrift „{content[:60]}“ ist keine Folge und keine Szene. Für eine neue Szene schreib „### Szene – {content[:30]}“.')

    def read(self):
        rows = self.rows; i = 0
        while i < len(rows):
            raw = rows[i]; number = i + 1; i += 1
            if raw.strip().startswith('```'): continue
            row = _clean(raw)
            if not row:
                self.flush_cue(); continue
            folge = HEADING.match(raw)
            if folge:
                self.flush_cue(); self.section = None
                title = re.sub(r'^[\s:.\-–—|*_]+', '', raw[folge.end(1):]).strip().strip('*_ #').strip()
                self.episode(int(folge.group(1)), title[:100], number); continue
            if row.startswith('#'):
                self.flush_cue(); level = len(row) - len(row.lstrip('#'))
                self.heading(number, level, row.lstrip('#')); continue
            if self.section == 'notes': continue
            label = LABEL.match(row); word = name_key(label.group('name')) if label else ''
            named = bool(label) and word not in KEYWORDS and _is_name(label.group('name'), self.counts, self.figures)
            if self.cue:
                if not (label and (word in KEYWORDS or named)) and not SCENE.match(row) and not SLUG.match(row) and not TRANSITION.match(row):
                    number0, name, mood, text = self.cue
                    wrapped = WRAPPED.match(row)
                    if wrapped and not text and mood is None and (wrapped.group('a') is not None or wrapped.group('b') is not None):
                        self.cue = (number0, name, (wrapped.group('a') or wrapped.group('b') or '').strip(), text)
                    else: self.cue = (number0, name, mood, (text + ' ' + row).strip())
                    continue
                self.flush_cue()
            if word in ('titel', 'title'):
                value = label.group('text').strip()[:100]
                if self.folgen and self.episodes: self.episodes[-1]['title'] = value
                else: self.title = value
                continue
            if word in ('figur', 'figuren'):
                self.figure(number, label.group('text')); continue
            scene, slug = SCENE.match(row), SLUG.match(row)
            if scene or slug:
                place, what = _scene_parts((scene or slug).group('rest')); self.scene(number, _display(place) if slug else place, what); continue
            if self.section == 'figures':
                self.figure(number, row, listed=True); continue
            if word == 'ort':
                ep = self.ep(); last = ep['scenes'][-1] if ep and ep['scenes'] else None
                if last and not last['items'] and not last['place']: last['place'] = label.group('text').strip()
                else: self.scene(number, label.group('text').strip())
                continue
            if TRANSITION.match(row): continue
            if word in ACTION_LABELS:
                self.action(number, label.group('text')); continue
            wrapped = WRAPPED.match(row)
            if wrapped:
                inner = next(g for g in wrapped.groups() if g is not None).strip()
                self.action(number, re.sub(r'(?i)^(?:aktion|action|handlung)\s*:\s*', '', inner)); continue
            if word in VISUAL:
                self.describe(number, label.group('text').strip(), scene_only=True); continue
            if word in LOGLINE_LABELS:
                ep = self.ep()
                (ep['logline'] if ep else self.preface).append(label.group('text').strip()); continue
            if word in SOUND:
                self.problem(number, f'{label.group("name").strip().capitalize()}-Angaben setzt das Studio selbst, die Zeile wird übersprungen.'); continue
            if word in NOTE_LABELS: continue
            if named:
                if label.group('text').strip(): self.say(number, label.group('name'), label.group('mood'), label.group('text'))
                else: self.cue = (number, ' '.join(label.group('name').split()), label.group('mood'), '')
                continue
            cue = CUE.match(row)
            following = _clean(rows[i]) if i < len(rows) else ''
            if (cue and cue.group('name') == cue.group('name').upper() and sum(c.isalpha() for c in cue.group('name')) >= 2
                    and name_key(cue.group('name')) not in KEYWORDS and following and not following.startswith('#') and not LABEL.match(following)):
                self.cue = (number, cue.group('name').strip(), cue.group('mood'), ''); continue
            self.describe(number, row)
        self.flush_cue()
        return self


def _seconds(cut):
    """Natural length of the cut as the 0.18 sound layout builds it (factory_timing), before the
    minimum length adds anything: speech at 2.6 words per second, silent shots at their base."""
    total = 0.
    for shot in cut:
        speech = screenplay.spoken_seconds(shot['lines']) if shot['lines'] else 0
        total += {'line': HEAD + speech + TAIL, 'reaction': max(REACTION_MIN, HEAD + speech + REACTION_TAIL),
                  'establish': ESTABLISH_BASE}.get(shot['kind'], ACTION_BASE)
    return total


# screenplay.check speaks to the planner ("nötig", "umschreiben"); for Cay the same findings are advice.
ADVICE = ((r'^Zu wenig Sprecherwechsel: (\d+), nötig mindestens (\d+)\..*$', r'Wenig Sprecherwechsel: \1, empfohlen sind mindestens \2.'),
          (r'^Zu wenig AKTION-Zeilen: (\d+), nötig mindestens (\d+)\.$',
           r'Wenig AKTION-Zeilen: \1, empfohlen sind mindestens \2. Eine stumme Handlung bringt Bewegung in den Film.'),
          (r'^Zu lange Zeilen \(mehr als (\d+) Wörter\) aufteilen: ', r'Sätze mit mehr als \1 Wörtern wirken geteilt lebendiger: '),
          (r'^Telegrammstil umschreiben in natürliche Sätze: ', 'Sehr knappe Sätze im Telegrammstil: '),
          (r'^(\d+) Zeilen haben höchstens zwei Wörter\..*$', r'\1 Sätze haben höchstens zwei Wörter. Viele sehr kurze Sätze wirken abgehackt.'),
          (r'^Mindestens zwei Figuren müssen miteinander sprechen\.$', 'Hier spricht nur eine Figur.'))


def advice(title, beats, lines, cast):
    """screenplay.check as advisory notes for Cay's own script, never a rewrite. Left out: the word
    budget and the upper limits of turns and AKTION lines (the planner's budget; Cay's script sets its
    own length), and the shot limit, which is a blocking problem of its own."""
    seconds = max(MIN_SECONDS, round(_seconds(screenplay.shots(title, beats, lines, cast))))
    speakers = list(dict.fromkeys(l['speaker'] for l in lines if l['kind'] == 'line')) or cast
    notes = [n for n in screenplay.check(title, beats, lines, [], speakers, seconds)
             if not n.startswith(('Zu wenig Dialog', 'Zu viel Dialog', 'Zu viele Einstellungen', 'Zu viele AKTION', 'Zu viele Sprecherwechsel'))]
    for pattern, wording in ADVICE: notes = [re.sub(pattern, wording, n) for n in notes]
    return notes


def read(text):
    """Read Cay's script. Returns title, figures, episodes (each with its normalized screenplay text
    in the internal format), problems (with line numbers; blocking ones stop the film), the length
    per episode and the minimum length the film is planned with."""
    text = str(text or '').lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    r = _Reader(text.split('\n')).read()
    for error in manifest(text)['errors']: r.problem(None, error, True)
    # Figures: FIGUR lines first, then every speaker in order of appearance. A short form of a FIGUR
    # name ('KRABS' for 'Mr. Krabs') is that figure; an unknown speaker is never guessed.
    declared = [f['name'] for f in r.figures.values()]; spellings = {}
    for ep in r.episodes:
        for scene in ep['scenes']:
            for item in scene['items']:
                if item['kind'] == 'line': spellings.setdefault(name_key(item['name']), []).append(item)
    for key, items in spellings.items():
        if key in r.figures: continue
        alias = screenplay._resolve(items[0]['name'], declared) if declared else None
        if alias: r.figures[key] = r.figures[name_key(alias)]; continue
        written = next((x['name'] for x in items if x['name'] != x['name'].upper()), items[0]['name'])
        r.figures[key] = {'name': _display(written), 'description': '', 'line': items[0]['line'], 'declared': False}
    figures = list({id(f): f for f in r.figures.values()}.values()); names = [f['name'] for f in figures]
    if len(names) > MAX_CAST: r.problem(None, f'Im Drehbuch stehen {len(names)} Figuren, höchstens {MAX_CAST} sind möglich.', True)
    for a in figures:
        for b in figures:
            if a is not b and not a['declared'] and len(name_key(a['name'])) >= 3 and name_key(a['name']) in name_key(b['name']).replace('.', ' ').split():
                r.problem(a['line'], f'„{a["name"]}“ und „{b["name"]}“ sind zwei Figuren. Ist es dieselbe, schreib den Namen überall gleich '
                                     f'oder leg „FIGUR: {b["name"]}“ an.')
    for f in figures:
        if name_key(f['name']) in NARRATORS:
            r.problem(f['line'], f'„{f["name"]}“ ist im Film eine sichtbare Figur, die spricht. Eine Stimme ohne Bild gibt es nicht.')
    episodes = []; series = len(r.episodes) > 1 or r.folgen
    for ep in r.episodes:
        label = f'Folge {ep["number"]}' if series else 'Dein Film'
        title = ep['title'] or ('' if series else r.title)
        out = [f'TITEL: {title}'] if title else []; expected = []; beats = 0; place = ''; logline = list(ep['logline'])
        for scene in ep['scenes']:
            if not scene['items']:
                if not scene['explicit'] or not scene['what']: logline += scene['what']; continue
                r.problem(scene['line'], 'Szene ohne Satz und ohne AKTION, ihre Beschreibung wird als stumme Handlung gezeigt.')
                scene['items'] = [{'kind': 'action', 'text': p, 'line': scene['line']} for p in _pieces(' '.join(scene['what']), MAX_ACTION)]
                scene['what'] = []
            beats += 1; place = (scene['place'] or place).replace('|', '/')[:250]
            what = ' '.join(' '.join(scene['what']).replace('|', '/').split())[:800]
            out.append(f'# {beats} | {place} | {what}'.rstrip(' |'))
            for item in scene['items']:
                if item['kind'] == 'action':
                    out.append(f'AKTION: {item["text"]}'); expected.append(('action', '', item['text'], '', item['line']))
                else:
                    who = r.figures[name_key(item['name'])]['name']
                    out.append(f'{who} [{item["emotion"]}]: {item["text"]}'); expected.append(('line', who, item['text'], item['emotion'], item['line']))
        normalized = '\n'.join(out)
        title2, beat_list, lines, problems = screenplay.parse(normalized, names)
        # Safety net: the stored screenplay reads back exactly as written, or the film does not start.
        got = [(l['kind'], l['speaker'], l['text'], l['emotion']) for l in lines]
        wrong = next((e for e, g in zip(expected, got + [None] * len(expected)) if e[:4] != g), None)
        if problems or wrong or len(got) != len(expected):
            r.problem(wrong[4] if wrong else ep['line'], 'Diese Zeile liest das Studio anders, als sie geschrieben ist. Bitte umformulieren.', True)
        spoken = [l for l in lines if l['kind'] == 'line']
        cut = screenplay.shots(title2, beat_list, lines, names); seconds = round(_seconds(cut))
        if not spoken: r.problem(ep['line'], f'{label}: kein gesprochener Satz. Schreib Sätze so: „OMA (wütend): Wer hat meinen Kuchen gegessen?“', True)
        elif seconds < MIN_SECONDS:
            r.problem(ep['line'], f'{label} dauert nach dem Drehbuch nur etwa {seconds} s. Ein Film braucht mindestens {MIN_SECONDS} s: '
                                  'schreib ein paar Sätze oder eine AKTION-Zeile dazu.', True)
        elif seconds > MAX_SECONDS:
            r.problem(ep['line'], f'{label} dauert nach dem Drehbuch etwa {seconds} s, höchstens {MAX_SECONDS} s gehen. Kürze das Drehbuch '
                                  + ('oder teile die Folge auf.' if series else 'oder teile es mit „## Folge 1“, „## Folge 2“ in mehrere Folgen.'), True)
        if len(cut) > screenplay.MAX_SHOTS:
            r.problem(ep['line'], f'{label} ergibt {len(cut)} Einstellungen, höchstens {screenplay.MAX_SHOTS}. Weniger AKTION-Zeilen '
                                  'oder mehr Sätze derselben Figur hintereinander.', True)
        if spoken and not any(b['place'] and b['place'] != 'Ort' for b in beat_list):
            r.problem(ep['line'], ('Kein Ort angegeben' if not series else f'{label}: kein Ort angegeben') + '. Schreib zum Beispiel '
                                  '„### Szene 1 – Küche – Oma steht am Tisch“, dann weiß das Studio, wo es spielt.')
        if spoken and not problems:
            for note in advice(title2, beat_list, lines, names): r.problem(None, (f'{label}: ' if series else 'Hinweis: ') + note)
        about = [' '.join(x.split()) for x in r.preface + logline + [b['what'] for b in beat_list] if x.strip()]
        plot = ' '.join(x if x[-1] in '.!?…' else x + '.' for x in about) or ' '.join(l['text'] for l in lines[:4])
        episodes.append({'number': ep['number'], 'title': title, 'text': normalized, 'scenes': len(beat_list), 'lines': len(spoken),
                         'words': sum(screenplay.words(l['text']) for l in spoken), 'actions': sum(l['kind'] == 'action' for l in lines),
                         'shots': len(cut), 'seconds': seconds, 'speakers': list(dict.fromkeys(l['speaker'] for l in spoken)),
                         'plot': plot[:1200], 'ending': (lines[-1]['text'] if lines else '')[:400]})
    if not r.episodes: r.problem(None, 'Im Drehbuch steht kein gesprochener Satz. Schreib Sätze so: „OMA (wütend): Wer hat meinen Kuchen gegessen?“', True)
    for f in figures:
        f['lines'] = sum(1 for ep in r.episodes for s in ep['scenes'] for x in s['items'] if x['kind'] == 'line' and r.figures[name_key(x['name'])] is f)
    problems = sorted(r.problems, key=lambda p: (not p['blocking'], p['line'] or 0))
    shortest = min((e['seconds'] for e in episodes), default=60)
    return {'title': r.title, 'figures': [{k: f[k] for k in ('name', 'description', 'lines', 'declared')} for f in figures], 'episodes': episodes,
            'problems': problems, 'ok': not any(p['blocking'] for p in problems), 'series': series,
            'words': sum(e['words'] for e in episodes), 'lines': sum(e['lines'] for e in episodes), 'scenes': sum(e['scenes'] for e in episodes),
            'seconds': sum(e['seconds'] for e in episodes),
            # Planned with a little less than the estimate: the minimum length must not make the voices wait.
            'duration': max(MIN_SECONDS, min(MAX_SECONDS, math.floor(shortest * .9))),
            'preview': '\n\n'.join((f'## Folge {e["number"]}\n' if series else '') + e['text'] for e in episodes)}


def prepare(idea):
    """Create: an idea with story 'script' takes episodes, length, cast and title from the script.
    Any other idea keeps its exact previous document (no 'story' key). Raises ValueError (German)."""
    if idea.get('story') != 'script':
        idea.pop('story', None); return None
    script = read(idea['idea'])
    blocking = [p['text'] for p in script['problems'] if p['blocking']]
    if blocking: raise ValueError(blocking[0] + (f' Dazu {len(blocking) - 1} weitere Probleme im Drehbuch.' if len(blocking) > 1 else ''))
    names = {name_key(f['name']): f['name'] for f in script['figures']}
    for p in idea['participants']:
        if name_key(p['name']) not in names:
            raise ValueError(f'„{p["name"]}“ kommt im Drehbuch nicht vor. Gib der Figur einen Satz oder eine FIGUR-Zeile, oder lass sie weg.')
        p['name'] = names[name_key(p['name'])]
    idea.update(episodes=len(script['episodes']), duration=script['duration'], characters='provided')
    if not idea['title'].strip() and script['title']: idea['title'] = script['title'][:100]
    return {k: v for k, v in script.items() if k != 'preview'}


def participants(script, given):
    """The planning cast: exactly the script's figures, with Cay's picture, voice or library profile
    by name. The FIGUR text is the figure's description."""
    own = {name_key(p['name']): p for p in given}; out = []
    for f in script['figures']:
        p = dict(own.get(name_key(f['name']), {}))
        out.append({**p, 'name': f['name'], 'image': p.get('image'), 'voice': p.get('voice'),
                    'traits': (f['description'] or p.get('traits') or 'Figur aus dem Drehbuch. Aussehen und Wesen passend zu ihren Sätzen.')[:1500]})
    return out


HEADER = ('Du bist Szenenbildner und Casting-Leiter für Kurzfilme nach einem fertigen Drehbuch. Das Drehbuch in idea wird Wort für Wort verfilmt; '
          'du schreibst keine Handlung und keine Dialoge. Lies es genau und bestimme title, eine kurze synopsis, style, visual und mood passend dazu. '
          'Die Besetzung steht fest: genau die Figuren aus participants, Namen exakt übernehmen, keine weiteren. '
          'traits stammt aus dem Drehbuch und ist verbindlich: appearance beschreibt genau dieses Aussehen auf Englisch für das Bildmodell, '
          'personality übernimmt das Wesen daraus. Nur was das Drehbuch nicht sagt, ergänzt du passend zu den Sätzen und Handlungen der Figur. '
          'Jede Figur bekommt voice_preset passend zu Alter und Rolle und eine eigene voice_description zu Klang und Sprechweise. '
          'Ist eine Figur eine bekannte Figur aus Serien, Filmen oder Spielen, nennt original sie mit ihrer Serie auf Englisch und appearance beschreibt '
          'ihr Originaldesign genau; bei erfundenen Figuren bleibt original leer. Bei Lebensmittel-Figuren feste Kopfmaterialien, Silhouette und Kleidung. '
          'Beispiele (Look-Vorlagen) zeigen nur den gewünschten Bildstil. Deutsch; appearance und style dürfen Englisch für das Bildmodell sein.')


def header(result, script):
    """The planner's header with the script's own words where it has them: its title, and each
    FIGUR description as the figure's personality (the FIGUR text wins)."""
    result = {**result, 'cast': [dict(p) for p in result['cast']]}
    if len(script['title'].strip()) >= 2: result['title'] = script['title'].strip()[:100]
    described = {name_key(f['name']): f['description'] for f in script['figures'] if len(f['description'].strip()) >= 3}
    for person in result['cast']:
        if name_key(person['name']) in described: person['personality'] = described[name_key(person['name'])][:400]
    return result


def outlines(script):
    """One outline per episode from the script itself, no model; the titles are the script's."""
    out = []
    for ep in script['episodes']:
        title = (ep['title'] or script['title'] or f'Folge {ep["number"]}').strip()
        title = title if len(title) >= 2 else f'Folge {ep["number"]}'
        plot = ep['plot'] if len(ep['plot']) >= 10 else f'{title}: {ep["plot"]}'.strip(' :')
        out.append(Outline.model_validate({'title': title[:100], 'plot': plot.ljust(10, '.')[:1200], 'ending': (ep['ending'] or title).ljust(3, '.')[:400],
                                           'pickup': '', 'cliffhanger': ''}).model_dump())
    return out
