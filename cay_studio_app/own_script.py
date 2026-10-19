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
import unicodedata
import screenplay
from factory_cast import name_key
from factory_models import MAX_CAST, Outline
from factory_timing import HEAD, TAIL, REACTION_TAIL, REACTION_MIN, ACTION_BASE, ESTABLISH_BASE, FPS
from story_source import HEADING, manifest
import shot_design

# 0.19 (r019 diagnosis, area 'Drehbuch und Dialog'): read() reads with POLICY by default, the rules for every
# project created from 0.19 on (pinned with sound/shot/render policy 19). policy=0 reads exactly as 0.18, for an
# older project that has to read its script again (factory.plan). What 0.19 adds, all without a model:
# - the spellings of chat assistants (r019: 25 of 46 typical variants lost, invented or misfiled a line): camera,
#   sound and outline labels are no figures, a speaker behind 'Dialog:' or 'Hook:' speaks, *stage directions*
#   at the edge of a line are never spoken, a line broken under its speaker goes on, tables, pipe rows,
#   'NAME – Text', numbered and bracketed scene headings, time windows;
# - (off), (V.O.), (O.S.), (Telefon) and 'Stimme (X)': the line is heard from off-screen over the listener
#   (the 0.18 reaction shot), the figure is not shown speaking; a narrator without a figure stays visible (reported);
# - an AKTION paragraph that only sets the scene (place, light, clothing, who stands where) is the picture of the
#   next line or AKTION of its scene ('BILD:' in the internal format) instead of a silent shot; from its first
#   real event on it stays a silent shot, as long as the picture area renders it (shot_design.ACTION_FRAMES);
# - time windows ('00:00 bis 00:15') leave place and description and are only a length hint; a hint before
#   anything is rendered when an episode has little speech or a long silent start, with numbers;
# - a reading report: how many rows were spoken, shown, used as picture or not filmed, and which rows the
#   studio did not understand.
# Cay's words never change: lines are split, joined or moved only as whole words, never rewritten.
POLICY = 19

MIN_SECONDS, MAX_SECONDS = 15, 180
LONG_SECONDS = 90          # above: a hint, not a stop (Cay: keine Textlängen-Sperre); the planned minimum stays at most 90
MAX_SPOKEN = 240            # screenplay.parse keeps 240 characters of a spoken line
MAX_ACTION = 400            # … and 400 of an AKTION line
MAX_CONTEXT = 600           # 0.19: one 'BILD:' row (the picture of a line); a longer one is split, all of it stays
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
VISUAL = {'kamera', 'licht', 'bild', 'einstellung', 'beschreibung', 'regie', 'zeit', 'rückblende', 'zeitsprung'}   # into the scene description
SOUND = {'musik', 'ton', 'sound', 'geräusch', 'geräusche', 'schnitt', 'off', 'untertitel'}   # the studio mixes itself
NOTE_LABELS = {'hinweis', 'hinweise', 'notiz', 'notizen', 'anmerkung', 'tipp', 'achtung', 'wichtig', 'info', 'beispiel', 'zum beispiel', 'text',
               # what an AI chat or a planning sheet writes above a script; never filmed
               'genre', 'dauer', 'länge', 'laufzeit', 'stil', 'look', 'zielgruppe', 'format', 'plattform', 'stimmung', 'hook', 'intro',
               'outro', 'cta', 'call to action', 'caption', 'hashtags', 'hashtag', 'tags'}
# 0.19: more labels chat assistants write; never a figure (a declared FIGUR of the same name still wins).
VISUAL_19 = VISUAL | {'nahaufnahme', 'totale', 'halbtotale', 'close-up', 'closeup', 'insert', 'shot', 'take', 'kameraeinstellung', 'perspektive',
                      'szenenbeschreibung', 'szenenbild', 'bildidee', 'bildbeschreibung', 'visual', 'visuell', 'hintergrund', 'requisiten',
                      'kostüm', 'montage', 'zeitlupe', 'flashback', 'regieanweisung', 'b-roll'}
SOUND_19 = SOUND | {'sfx', 'atmo', 'audio', 'effekt', 'soundeffekt', 'soundeffekte', 'geräuschkulisse', 'soundtrack', 'score'}
NOTE_19 = NOTE_LABELS | {'situation', 'konflikt', 'twist', 'pointe', 'cliffhanger', 'payoff', 'wendung', 'wendepunkt', 'ziel', 'moral', 'fazit',
                         'beat', 'abspann', 'pause', 'tempo', 'mood', 'übergang', 'transition', 'cut', 'dialog', 'dialoge', 'einblendung',
                         'texteinblendung', 'overlay', 'on-screen-text', 'vfx'}
BLOCK_LABELS = {'dialog', 'dialoge', 'hook', 'intro', 'outro', 'cliffhanger', 'text'}   # alone above lines: nothing to film
STRUCTURE = re.compile(r'(?i)^(?:beat|akt|wendepunkt|cliffhanger|hook|intro|outro|pointe|payoff|twist|höhepunkt|auflösung|teaser|cold open)\b[^:]{0,60}$')
PRONOUNS = re.compile(r'(?i)(?<!\w)(?:ich|mich|mir|mein\w*|du|dich|dir|dein\w*|wir|uns|unser\w*|euch|euer\w*|eure\w*)(?!\w)')
TABLE_ROLES = (('speaker', r'figur|name|sprecher|wer|rolle|charakter|person'), ('text', r'text|dialog|satz|zeile|gesprochen|sprechtext'),
               ('picture', r'bild|aktion|handlung|visual|beschreibung|kamera|was passiert'), ('place', r'ort|location|schauplatz'),
               ('time', r'zeit|time|sek|timecode|dauer'))
SPEECH_VERB = r'(?P<verb>sagt|fragt|ruft|flüstert|antwortet|meint|brüllt|schreit|murmelt|erwidert|faucht|zischt)'
# Heard, not seen: the line comes from off-screen over the listener's face (0.18 reaction shot).
OFF = re.compile(r"(?i)^(?:off|im off|aus dem off|off-?stimme|stimme(?: aus dem off)?|nur (?:die )?stimme|v\.?\s?o\.?|o\.?\s?s\.?|o\.?\s?c\.?|"
                 r"voice-?over|(?:am |per |durchs |ins |übers )?telefon|(?:über )?funk|lautsprecher|(?:durch|hinter) die tür|von draußen)$")
IGNORED = re.compile(r"(?i)^(?:cont'?d|cont\.|forts\.?|fortsetzung|weiter|zu .{1,40}|an .{1,40}|zu sich(?: selbst)?)$")
LOGLINE_LABELS = {'logline', 'inhalt', 'zusammenfassung', 'idee', 'thema', 'setting'}
PLACE_LABELS = {'ort', 'schauplatz', 'szenenwechsel', 'ortswechsel'}
KEYWORDS = ACTION_LABELS | VISUAL | SOUND | NOTE_LABELS | LOGLINE_LABELS | PLACE_LABELS | {
    'titel', 'title', 'figur', 'figuren', 'szene', 'scene', 'folge', 'episode', 'innen', 'aussen', 'außen', 'ende'}
FIGURE_SECTIONS = {'figuren', 'besetzung', 'personen', 'rollen', 'cast', 'charaktere', 'figurenliste', 'die figuren', 'mitwirkende'}
NOTE_SECTIONS = {'hinweise', 'hinweis', 'notizen', 'notiz', 'anmerkungen', 'anmerkung', 'kommentar', 'kommentare', 'regieanweisungen',
                 'info', 'infos', 'format', 'so funktioniert es', 'erklärung', 'anleitung'}
NEUTRAL_SECTIONS = {'drehbuch', 'skript', 'script', 'handlung', 'story', 'geschichte'}
NARRATORS = {'erzähler', 'erzählerin', 'sprecher', 'sprecherin', 'stimme', 'off-stimme', 'erzählstimme', 'narrator'}
KEYWORDS_19 = KEYWORDS | VISUAL_19 | SOUND_19 | NOTE_19
# Capitalised sentence starters: 'Um 8 Uhr: …' or 'Plötzlich: …' is prose, unless the name speaks twice or is a FIGUR.
STARTERS = {'um', 'am', 'im', 'in', 'als', 'wenn', 'dann', 'da', 'und', 'aber', 'doch', 'nach', 'vor', 'bei', 'mit', 'zum', 'zur', 'auf', 'es',
            'er', 'sie', 'wir', 'ich', 'du', 'ihr', 'das', 'der', 'die', 'den', 'dem', 'ein', 'eine', 'einer', 'plötzlich', 'später', 'danach',
            'jetzt', 'heute', 'morgen', 'gestern', 'hier', 'dort', 'so', 'also', 'nur', 'noch', 'schon', 'wie', 'was', 'wer', 'wo', 'warum',
            'merke', 'endlich', 'kurz', 'währenddessen', 'inzwischen', 'unterdessen', 'zuerst', 'schließlich', 'alle'}
# 'Der Postbote: …', 'Die Nachbarin: …', 'Ein Kind: …' are role names when every following word is capitalised.
ARTICLES = {'der', 'die', 'das', 'ein', 'eine'}
# Several figures at once: in the film every line has exactly one speaker.
GROUPS = {'alle', 'beide', 'zusammen', 'alle zusammen', 'beide zusammen', 'alle gleichzeitig', 'alle drei', 'alle vier', 'chor', 'gruppe'}
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
RULE = re.compile(r'^\s*(?:[-*_]\s*){3,}$')                                        # a Markdown rule '---', '***', '* * *'
BULLET = re.compile(r'^\s*(?:>\s*)*(?:\*\*|__)?(?:[-*+•–]\s+|\d{1,3}[.)]\s+)')
NUMBERED = re.compile(r'^\d{1,3}[.)]\s+')
# '[0:00–0:05] Hook', '(0:05)', '0:05–0:12': the studio sets its own timing.
TIMESTAMP = re.compile(r'^(?:[\[(]\s*\d{1,2}:\d{2}(?:\s*(?:[–—-]|bis)\s*\d{1,2}:\d{2})?\s*(?:s|sek\.?|min\.?)?\s*[\])]'
                       r'|\d{1,2}:\d{2}\s*(?:[–—-]|bis)\s*\d{1,2}:\d{2}\s*(?:s|sek\.?|min\.?)?)\s*[:.\-–—|]?\s*')
TIMESTAMP_19 = re.compile(r'^(?:[\[(]\s*\d{1,3}\s*[–—-]\s*\d{1,3}\s*(?:s|sek\.?|sekunden)\s*[\])]|(?:[Ss]ek\.?|[Ss]ekunden?)\s*\d{1,3}\s*[–—-]\s*\d{1,3}(?:\s*s)?'
                          r'|[\[(]\s*\d{1,2}:\d{2}(?:\s*(?:[–—-]|bis)\s*\d{1,2}:\d{2})?\s*(?:s|sek\.?|min\.?)?\s*[\])]'
                          r'|\d{1,2}:\d{2}\s*(?:[–—-]|bis)\s*\d{1,2}:\d{2}\s*(?:s|sek\.?|min\.?)?|\d{1,2}:\d{2}(?=\s*[–—|-]\s))\s*[:.\-–—|]?\s*')
# A time window in a scene heading or description: '00:00 bis 00:15', '(0:08–0:20)', '[4–8 s]'.
WINDOW = re.compile(r'[\[(]?\s*(\d{1,2}):(\d{2})\s*(?:[–—-]|bis)\s*(\d{1,2}):(\d{2})\s*(?:s|sek\.?|min\.?|uhr)?\s*[\])]?'
                    r'|[\[(]\s*(\d{1,3})\s*[–—-]\s*(\d{1,3})\s*(?:s|sek\.?|sekunden)\s*[\])]', re.I)
# The script's own length: 'jeweils ungefähr 58 Sekunden'.
STATED = re.compile(r'(?i)\b(?:ungefähr|etwa|ca\.?|circa|rund|jeweils|je|knapp)\s+(\d{2,3})\s*(?:sekunden|sek\.?|s)\b')
# Emphasis around a name or a stage direction: '*OMA*: …', '_TIM_: …', '*OMA:* …', 'OMA *(schreit)*: …'.
EMPHASIS_NAME = re.compile(r'^([*_])([^*_]{1,60}?)\1(?=\s*[:(\[])')
EMPHASIS_LABEL = re.compile(r'^([*_])([^*_]{1,60}?:)\1')
EMPHASIS_DIRECTION = re.compile(r'([*_])\s*([(\[][^()\[\]]{0,60}[)\]])\s*\1')
MAX_NESTING = 4             # brackets nested deeper than this are not a stage direction


def _lead(row):
    """Without leading emoji and symbols ('🎥 Szene 1: Küche' -> 'Szene 1: Küche')."""
    start = 0
    while start < len(row) and (row[start].isspace() or unicodedata.category(row[start]) in ('So', 'Sk', 'Cf', 'Mn')): start += 1
    return row[start:]


def _clean(raw):
    """One row without Markdown noise: bold, code, quote markers, list bullets, leading emoji and the
    emphasis around a speaker's name or stage direction."""
    row = re.sub(r'\*\*|__|`', '', raw).strip()
    row = _lead(re.sub(r'^(?:>\s*)+', '', row).strip())
    if not WRAPPED.match(row): row = _lead(re.sub(r'^(?:[-*+•–]\s+)', '', row).strip())
    unwrap = lambda x: EMPHASIS_LABEL.sub(r'\2', EMPHASIS_NAME.sub(r'\2', EMPHASIS_DIRECTION.sub(r'\2', x)))
    m = NUMBERED.match(row)                                                # '1. TIM: …' in a numbered list
    return unwrap(row[m.end():] if m and LABEL.match(unwrap(row[m.end():])) else row)


def _display(name):
    """'FRAU MÜLLER' -> 'Frau Müller', 'MR. KRABS' -> 'Mr. Krabs'; mixed case stays as written."""
    name = ' '.join(name.split()).strip(' *_')
    if name != name.upper() or not any(c.isalpha() for c in name): return name
    return re.sub(r'[^\W\d_]+', lambda m: m.group(0)[:1] + m.group(0)[1:].lower(), name)


def _caps(name):
    return name == name.upper() and sum(c.isalpha() for c in name) >= 2


def _group(name):
    """'Alle', 'Beide', 'Tim & Opa', 'Oma und Tim', 'Tim, Opa': several speakers at once."""
    return name_key(name) in GROUPS or bool(re.search(r'\s(?:&|\+|/|und|and)\s|[,&/+]', name, re.I))


def _keyword(name, keywords=KEYWORDS):
    """The label word of 'MUSIK:', 'Outro / CTA:' or 'Ort der Handlung:'; '' for a name."""
    key = name_key(name)
    if key in keywords: return key
    first = re.split(r'\s*/\s*|\s+', key)[0].rstrip('.')
    return first if first in keywords and first != 'off' and key not in NARRATORS else ''


def _is_name(name, counts, known, spoken=True, keywords=KEYWORDS):
    key = name_key(name)
    if key in known: return True
    if _group(name): return False                                         # one line, one speaker
    words = name.split()
    if not 1 <= len(words) <= 4 or len(name) > 40 or key in keywords: return False
    if not words[0][:1].isupper() or words[0].casefold().rstrip('.') in keywords: return False
    if any(not (w[:1].isupper() or w.isdigit() or (i and w.casefold() in PARTICLES)) for i, w in enumerate(words)): return False
    if name == name.upper() or counts.get(key, 0) >= 2: return True
    if words[0].casefold() in ARTICLES and len(words) >= 2: return spoken and all(w[:1].isupper() for w in words[1:])
    return words[0].casefold() not in STARTERS


def _cue(row, following, keywords=KEYWORDS):
    """A name alone in capitals above its text ('MAX', 'MAX (flüsternd)'), or None."""
    cue = CUE.match(row)
    if (cue and _caps(cue.group('name')) and name_key(cue.group('name')) not in keywords and not TRANSITION.match(row)
            and following and not following.startswith('#') and not LABEL.match(following)): return cue
    return None


def _unquote(text):
    """screenplay.parse strips quote marks at both edges of a line; their partner inside the line goes
    with them, so no lone mark stays in the subtitles: '„Wer?“ Ich zähl bis drei!' -> 'Wer? Ich zähl
    bis drei!', 'Er sagte „Nein“' -> 'Er sagte Nein'. No word changes."""
    closers = {'„': '“”', '“': '”“', '"': '"'}
    if len(text) > 1 and text[0] in closers:
        close = min((p for p in (text.find(c, 1) for c in closers[text[0]]) if p > 0), default=-1)
        if close > 0: text = text[1:close] + text[close + 1:]
    openers = {'“': '„“', '"': '"'}
    if len(text) > 1 and text[-1] in openers:
        start = max(text.rfind(c, 0, len(text) - 1) for c in openers[text[-1]])
        if start >= 0: text = text[:start] + text[start + 1:-1]
    return ' '.join(text.split())


def _speech(text, v19=False):
    """(spoken, directions): parentheses and brackets are never spoken, quotes and emphasis go.
    The final strips mirror screenplay.parse, so the stored line is exactly what it reads back.
    v19: '*kratzt sich am Kopf*' at the edge of a line (two lower-case words or a mood) is a direction too."""
    directions, spoken = [], EMPHASIS_DIRECTION.sub(r'\2', text)
    for m in reversed(list(re.finditer(r'([*_])(?!\s)([^*_]{2,60}?)(?<!\s)\1', spoken)) if v19 else []):
        seg = m.group(2).strip(); before = spoken[:m.start()].rstrip(); after = spoken[m.end():].strip()
        edge = not before or before[-1] in '.!?…:,' or not after or after[:1] in '.!?…,'
        mood, known = emotion_for(seg)
        if edge and seg[:1].islower() and (len(seg.split()) >= 2 or (known and mood != 'ruhig')):
            directions.insert(0, seg); spoken = spoken[:m.start()] + ' ' + spoken[m.end():]
    for _ in range(MAX_NESTING):
        if not DIRECTION.search(spoken): break
        directions += [(m.group(1) if m.group(1) is not None else m.group(2)).strip() for m in DIRECTION.finditer(spoken)]
        spoken = DIRECTION.sub(' ', spoken)
    spoken = re.sub(r'(?<!\S)[*_]+(?!\S)', ' ', spoken)            # emphasis left alone by a removed direction
    for mark in ('*', '_'):
        spoken = re.sub(r'(?<![\w%s])\%s(?=\S)([^%s]+?)(?<=\S)\%s(?![\w%s])' % ((mark,) * 5), r'\1', spoken)
    spoken = ' '.join(spoken.split())
    if directions: spoken = re.sub(r'\s+([,.!?;:…])', r'\1', spoken)
    for a, b in QUOTES:
        inner = spoken[len(a):-len(b)] if len(spoken) >= 2 else ''
        if len(spoken) >= 2 and spoken.startswith(a) and spoken.endswith(b) and a not in inner and b not in inner:
            spoken = inner.strip(); break
    spoken = _unquote(spoken.strip().strip('*').strip())
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


def _figure_line(text, comma=True):
    """'Frau Müller – 60, streng' / 'Frau Müller: …' / 'Frau Müller (60, streng)' / 'Frau Müller' -> (name, description)."""
    text = text.strip()
    m = re.match(r'^(?P<name>[^()\[\]:–—|]{1,60}?)\s*\((?P<desc>[^()]*)\)\s*[:.]?\s*(?P<more>.*)$', text)
    if m and not SEPARATOR.search(m.group('name')):
        return m.group('name').strip(' *_-'), ' '.join(x.strip() for x in (m.group('desc'), m.group('more')) if x.strip())
    parts = SEPARATOR.split(text, 1)
    if len(parts) == 1 and ':' in text: parts = text.split(':', 1)
    if comma and len(parts) == 1 and ',' in text and len(text.split(',', 1)[0].split()) <= 3: parts = text.split(',', 1)
    return parts[0].strip(' *_-'), (parts[1].strip() if len(parts) > 1 else '')


def _scene_parts(rest, v19=False):
    """'Küche – Oma steht vor dem Teller' -> ('Küche', 'Oma steht vor dem Teller'); 'Küche: …' too.
    v19: time windows ('– 00:00 bis 00:15') leave place and description (_window keeps them as a hint)."""
    if v19: rest = _window(rest)[0]
    rest = rest.strip(' :.-–—|')
    parts = [p.strip() for p in SEPARATOR.split(rest, 1)]
    if len(parts) == 1 and ':' in rest: parts = [p.strip() for p in rest.split(':', 1)]
    return parts[0], (parts[1] if len(parts) > 1 else '')


def _unstamp(row, pattern=TIMESTAMP):
    """(row, time mark): '[0:00–0:05] Hook' -> ('Hook', '[0:00–0:05]'); the studio sets its own timing."""
    m = pattern.match(row)
    return (row[m.end():].strip(), m.group(0).strip(' :.-–—|')) if m else (row, '')


def _short(text, limit=60):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + ' …'


def _names(text):
    """'Oma Hilde, Tim (9)' -> ['Oma Hilde', 'Tim (9)'] when every part is a name; else None."""
    parts = [p.strip() for p in re.split(r'[,;](?![^()]*\))', text) if p.strip()]
    if len(parts) < 2: return None
    return parts if all(_is_name(_figure_line(p, comma=False)[0], {}, {}) for p in parts) else None


def _continues(prev, row, names):
    """0.19: a row right under a spoken line (no blank line) that is the rest of it: the sentence was broken,
    or it speaks in the first or second person, or asks or exclaims. 'Mr. Krabs schiebt …' is an action."""
    spoken = _speech(row, True)[0]
    if not spoken: return False
    person = bool(PRONOUNS.search(spoken))
    if any(name_key(row).startswith(name_key(n) + ' ') for n in names if n): return person
    if prev and prev.rstrip()[-1:] not in '.!?…"“”»«': return True
    return person or spoken.rstrip('"“”»«').endswith(('?', '!'))


def _heading_row(row):
    """0.19: '[SZENE 1 – AUSSEN – HAFEN]' and '2. INT. KRUSTY KRAB – TAG' as a scene heading."""
    r = row.strip()
    m = re.match(r'^\[(.+)\]$', r)
    if m: r = m.group(1).strip()
    return re.sub(r'^\d{1,3}[.)]\s+(?=(?:INNEN/AUSSEN|INNEN|AUSSEN|AUßEN|INT|EXT)\b)', '', r)


def _scene_rest(rest):
    m = SLUG.match(rest.strip(' :.-–—|'))
    return m.group('rest') if m else rest


def _window(text):
    """0.19: (text without its time windows, (start, end) in seconds or None)."""
    found = None
    for m in WINDOW.finditer(text):
        g = m.groups()
        span = (int(g[0]) * 60 + int(g[1]), int(g[2]) * 60 + int(g[3])) if g[0] is not None else (int(g[4]), int(g[5]))
        if span[1] > span[0]: found = (min(span[0], found[0]), max(span[1], found[1])) if found else span
    if found is None and not WINDOW.search(text): return text, None
    rest = re.sub(r'\s*(?:[-–—|]\s*){2,}', ' – ', WINDOW.sub(' ', text))
    return ' '.join(rest.split()).strip(' :.-–—|'), found


def _spelling(name, text):
    """0.19: a name written in capitals ('SPONGEBOB') takes the script's own mixed-case spelling ('SpongeBob')
    when the text has one; the picture text and the image model know the figure by it."""
    display = _display(name)
    if name != name.upper(): return display
    seen = {}
    for m in re.finditer(r'(?<![\w.])' + re.escape(display) + r'(?![\w])', text, re.I):
        w = m.group(0)
        if w != w.upper() and w != w.lower() and w != display: seen[w] = seen.get(w, 0) + 1
    return max(seen, key=lambda w: (seen[w], w)) if seen else display


# 0.19: an AKTION paragraph that only sets the scene is the picture of the next line instead of a silent shot.
# A sentence is an event when it holds a verb of doing, moving, looking or reacting (or one this list does not
# know: an unknown verb in -t counts as an event, so in doubt the paragraph stays a silent shot as in 0.18).
STATE_VERBS = {'ist', 'sind', 'war', 'waren', 'steht', 'stehen', 'stand', 'standen', 'sitzt', 'sitzen', 'saß', 'liegt', 'liegen', 'lag', 'lagen',
               'hängt', 'hängen', 'hing', 'trägt', 'tragen', 'trug', 'wirkt', 'wirken', 'scheint', 'scheinen', 'leuchtet', 'leuchten', 'glänzt',
               'glänzen', 'glitzert', 'schimmert', 'brennt', 'brennen', 'wartet', 'warten', 'bleibt', 'bleiben', 'blieb', 'hat', 'haben', 'hatte',
               'hält', 'halten', 'hielt', 'bewacht', 'bewachen', 'lehnt', 'lehnen', 'kniet', 'knien', 'ruht', 'ruhen', 'fehlt', 'fehlen',
               'befindet', 'befinden', 'löst', 'spiegelt', 'spiegeln', 'berührt', 'berühren', 'schwebt', 'schweben', 'herrscht', 'umgibt'}
EVENT_STEMS = ('öffn', 'schließ', 'schloss', 'nimm', 'nehm', 'nahm', 'leg', 'stell', 'steck', 'zieh', 'zog', 'schieb', 'schob', 'wirf', 'werf',
               'warf', 'greif', 'griff', 'pack', 'heb', 'hob', 'senk', 'dreh', 'reiß', 'riss', 'schläg', 'schlag', 'schlug', 'stöß', 'stoß',
               'drück', 'klapp', 'verstau', 'versteck', 'wisch', 'geh', 'ging', 'komm', 'kam', 'lauf', 'läuf', 'lief', 'renn', 'rann', 'spring',
               'sprang', 'tritt', 'trat', 'tret', 'stolper', 'sink', 'sank', 'fall', 'fäll', 'fiel', 'zuck', 'zitter', 'nick', 'schüttel', 'lach',
               'wein', 'seufz', 'atm', 'schluck', 'erschr', 'grins', 'klingel', 'knall', 'krach', 'explod', 'schieß', 'schoss', 'knarr', 'klopf',
               'piep', 'flieh', 'floh', 'kriech', 'kletter', 'beug', 'richt', 'folg', 'verlass', 'verläss', 'verließ', 'betret', 'betritt',
               'erschein', 'verschwind', 'beginn', 'begann', 'versuch', 'prüf', 'hilf', 'half', 'helf', 'fang', 'fäng', 'umarm', 'küss', 'versteh',
               'antwort', 'schweig', 'flüster', 'ruf', 'schrei', 'brüll', 'zeig', 'wend', 'weich', 'lass', 'läss', 'stopp', 'setz', 'steig', 'stieg',
               'schleich', 'tanz', 'flieg', 'flog', 'wirbel', 'rutsch', 'stürz', 'stürm', 'eil', 'hüpf', 'tauch', 'schwimm', 'kipp', 'bricht',
               'brech', 'zerbr', 'reich', 'gib', 'gab', 'trink', 'isst', 'ess', 'aß', 'wach', 'schreib', 'tipp', 'wähl', 'blitz', 'zisch', 'lösch',
               'zünd', 'schalt', 'sieh', 'sah', 'seh', 'schau', 'blick', 'betracht', 'beobacht', 'muster', 'bemerk', 'entdeck', 'starr', 'zähl',
               'wink', 'deut', 'nähert', 'verbeug', 'streck', 'kratz', 'tipp', 'klatsch', 'schnapp', 'stiehl', 'stahl', 'hol', 'bring', 'brach')
EVENT_NOUNS = {'schuss', 'schüsse', 'knall', 'explosion', 'schrei', 'einschlag', 'schwarzbild', 'abblende', 'blackout', 'blitz'}
NON_VERBS = {'nicht', 'nichts', 'jetzt', 'direkt', 'erst', 'zuerst', 'zuletzt', 'selbst', 'sonst', 'bereits', 'seit', 'leicht', 'gut', 'mit',
             'weit', 'breit', 'laut', 'kaputt', 'dicht', 'recht', 'schlecht', 'echt', 'acht', 'samt', 'fast', 'meist', 'zumindest', 'bunt', 'sanft',
             'zart', 'nackt', 'stolz', 'dort', 'fort', 'sofort', 'bekannt', 'oft', 'bestimmt', 'zunächst', 'ernst', 'höchst', 'nachts', 'heut',
             'halt', 'satt', 'matt', 'glatt', 'flott', 'strikt', 'exakt', 'perfekt', 'komplett', 'leise', 'gerade', 'mittlerweile', 'insgesamt'}
AUX = {'ist', 'sind', 'war', 'waren', 'hat', 'haben', 'hatte', 'hatten', 'wird', 'werden', 'wurde', 'wurden'}
PREFIXED = re.compile(r'^(?:ge|be|ver|er|zer|ent|über|unter|auf|ab|an|aus|ein|zu|zurück|mit|vor|nach|weg|los)\w*(?:t|en)$')
LIGHT = re.compile(r'(?i)licht|lampe|sonne|mond|schein|glanz|schatten|nebel|dampf|rauch|staub|regen|schnee|funke|strahl|kerze|uhr')
LIGHT_VERBS = {'fällt', 'fallen', 'kommt', 'kommen', 'dringt', 'dringen', 'scheint', 'flackert', 'flackern', 'wandert', 'wandern', 'fängt',
               'tanzt', 'tanzen', 'zieht', 'ziehen', 'steigt', 'steigen', 'tickt'}
RISE = {'auf', 'ab', 'an', 'um', 'zurück', 'weg', 'hoch', 'heraus', 'herein', 'hinaus', 'los', 'hin und her'}


def _sentences(text):
    """Sentences of an AKTION text (no word changes; 'Mr. Krabs' and 'z. B.' are no sentence end)."""
    guarded = re.sub(r'\b(?:Mr|Mrs|Ms|Dr|St|Prof|Hr|Fr|Nr|bzw|ca|vgl|z\. ?B|u\. ?a|d\. ?h)\.', lambda m: m.group(0).replace('.', '\0'), text)
    return [p.replace('\0', '.') for p in re.split(r'(?<=[.!?…])\s+|(?<=[.!?…]["“”»«])\s+', guarded) if p.strip()]


def _kind(sentence):
    """'event', 'state' (place, light, clothing, posture) or '' (no verb: 'Ruhiger Beginn.', 'Nacht.')."""
    words = re.findall(r"[^\W\d_][\w'’-]*", sentence)
    lower = [w for w in words if w[:1].islower()]
    if any(w.lower() in EVENT_NOUNS for w in words if w[:1].isupper()): return 'event'
    light = any(LIGHT.search(w) for w in words if w[:1].isupper())
    aux = any(w in AUX for w in lower); state = False; tail = lower[-1] if lower else ''
    for w in lower:
        if w in NON_VERBS: continue
        if light and w in LIGHT_VERBS: state = True; continue
        if w in STATE_VERBS:
            if w in ('steht', 'stehen', 'sitzt', 'sitzen', 'liegt', 'liegen', 'bleibt', 'bleiben') and tail in RISE: return 'event'    # 'steht auf'
            state = True; continue
        if w.startswith(EVENT_STEMS): return 'event'
        if w.endswith('t') and len(w) > 3 and not w.startswith('ge') and not (aux and PREFIXED.match(w)): return 'event'
    return 'state' if state else ''


def _setting(text):
    """(scene setting, rest): the leading sentences of an AKTION text that only set the scene, and the text from
    its first event on. Nothing moves unless one of the leading sentences really describes a state."""
    parts = _sentences(text); kinds = [_kind(p) for p in parts]
    lead = next((i for i, k in enumerate(kinds) if k == 'event'), len(parts))
    if 'state' not in kinds[:lead]: return '', text
    return ' '.join(parts[:lead]), ' '.join(parts[lead:])


class _Reader:
    """One pass over the rows; scenes and items keep their line numbers for the problems.
    policy 19 (POLICY) reads with the 0.19 rules (module text), policy 0 exactly as 0.18."""
    def __init__(self, rows, policy=POLICY):
        self.rows = rows; self.title = ''; self.figures = {}; self.episodes = []; self.problems = []; self.preface = []
        self.section = None; self.cue = None; self.folgen = any(HEADING.match(r) for r in rows); self.counts = {}; self.stamped = False; self.notes = None
        self.v19 = policy >= POLICY; self.kw = KEYWORDS_19 if self.v19 else KEYWORDS
        self.last = None; self.table = None; self.spoken = set(); self.used = {}; self.text = '\n'.join(rows)
        self.clean = [_unstamp(_clean(r), TIMESTAMP_19 if self.v19 else TIMESTAMP) for r in rows]
        for row, _ in self.clean:
            m = LABEL.match(row)
            if m: self.counts[name_key(m.group('name'))] = self.counts.get(name_key(m.group('name')), 0) + 1
        # Pasted from Word or Google Docs, a script has no blank lines: a cue follows the previous text
        # directly, and each row is one paragraph, so a cue's text is the one row below it.
        self.dense = any(self.text_row(n - 1) and _cue(self.clean[n][0], self.clean[n + 1][0] if n + 1 < len(rows) else '', self.kw) for n in range(1, len(rows)))

    def text_row(self, n):
        """Row n (0-based) is spoken text or prose, not a heading, rule, scene, place or label."""
        row = self.clean[n][0]; label = LABEL.match(row)
        return bool(row) and not row.startswith('#') and not RULE.match(self.rows[n]) and not SCENE.match(row) and not SLUG.match(row) \
            and not (label and _keyword(label.group('name'), self.kw))

    def mark(self, number, kind):
        """Reading report (0.19): what became of each row (the first verdict counts)."""
        if number and number not in self.used: self.used[number] = kind

    def problem(self, number, text, blocking=False, last=None):
        where = f'Zeile {number}–{last}: ' if number and last and last != number else f'Zeile {number}: ' if number else ''
        self.problems.append({'line': number, 'text': where + text, 'blocking': blocking})

    def ep(self):
        """The current episode; a film without 'Folge' headings is one episode. None before 'Folge 1'."""
        if self.episodes: return self.episodes[-1]
        if self.folgen: return None
        return self.episode()

    def episode(self, number=None, title='', line=None):
        self.episodes.append({'number': number or len(self.episodes) + 1, 'title': title, 'line': line, 'scenes': [], 'logline': []})
        return self.episodes[-1]

    def open(self, kind, number, name):
        self.close(); self.section = kind
        ep = self.episodes[-1] if self.episodes else None
        self.notes = {'line': number, 'name': name, 'rows': [], 'inside': bool(ep and ep['scenes'])}

    def close(self, speaker=False):
        """End a '## Figuren' or '## Hinweise' section. Skipped text inside a scene, or text that a
        spoken line interrupts, is reported: the studio never drops words without saying so."""
        if self.section == 'notes' and self.notes['rows'] and (self.notes['inside'] or speaker):
            self.problem(self.notes['line'], f'Abschnitt „{_short(self.notes["name"], 40)}“ wird nicht verfilmt.'
                         + (' Danach geht das Drehbuch weiter.' if speaker else ''), last=self.notes['rows'][-1])
        self.section = None

    def scene(self, line=None, place='', what='', explicit=True):
        self.close(); self.mark(line, 'structure')
        ep = self.ep()
        if ep is None:
            self.problem(line, 'Die Szene steht vor „Folge 1“ und gehört zu keiner Folge. Schreib „## Folge 1“ davor oder verschiebe sie.', True)
            return {'place': '', 'what': [], 'items': [], 'explicit': explicit}
        window = None
        if self.v19:
            # '00:00 bis 00:15' is a length hint of the script, never part of the place or the picture.
            place, a = _window(place); what, b = _window(what); window = a or b
        ep['scenes'].append({'place': place, 'what': [what] if what else [], 'line': line, 'items': [], 'explicit': explicit, **({'window': window} if window else {})})
        return ep['scenes'][-1]

    def current(self, number, kind):
        """The scene that takes a spoken or silent line, or None (before 'Folge 1' in a series)."""
        ep = self.ep()
        if ep is None:
            self.problem(number, f'{kind} steht vor „Folge 1“ und gehört zu keiner Folge. Schreib „## Folge 1“ davor oder verschiebe den Text.', True)
            return None
        return ep['scenes'][-1] if ep['scenes'] else self.scene(explicit=False)

    def describe(self, number, text, scene_only=False, staged=False):
        """Prose: the description of a scene that has no line yet (or of the episode), else a visible action.
        Returns where it went."""
        ep = self.ep()
        if ep is None: self.preface.append(text); self.mark(number, 'picture'); return 'film'
        scene = ep['scenes'][-1] if ep['scenes'] else None
        if scene is None: ep['logline'].append(text); self.mark(number, 'picture'); return 'film'
        if not scene['items'] or scene_only: scene['what'].append(text); self.mark(number, 'picture'); return 'scene'
        self.action(number, text, staged); return 'action'

    def action(self, number, text, staged=False):
        """A silent action. 0.19: an AKTION row (staged) stays whole here; read() takes its scene setting
        apart from its events before it is cut into shots."""
        text = ' '.join(text.split()).strip('*').strip()
        scene = self.current(number, 'Die Handlung') if text else None
        if scene is None: return
        self.mark(number, 'action')
        if self.v19 and staged: scene['items'].append({'kind': 'action', 'text': text, 'line': number, 'staged': True}); return
        pieces = _pieces(text, MAX_ACTION)
        if len(pieces) > 1: self.problem(number, f'Sehr lange Handlung, als {len(pieces)} stumme Einstellungen gezeigt.')
        scene['items'] += [{'kind': 'action', 'text': p, 'line': number} for p in pieces]

    def voice_of(self, name, mood):
        """0.19: 'Stimme (Plankton)' or 'Erzähler (Sandy)' is the voice of a figure of the script, heard from off-screen."""
        if name_key(name) not in NARRATORS or not mood or not mood.strip(): return None
        target = ' '.join(mood.split()); key = name_key(target)
        declared = [f['name'] for f in self.figures.values()]
        if key in self.figures or self.counts.get(key, 0) or key in self.spoken or (declared and screenplay._resolve(target, declared)): return target
        return None

    def say(self, number, raw_name, mood, text):
        scene = self.current(number, 'Der Satz')
        if scene is None: return
        spoken, directions = _speech(text, self.v19)
        name = ' '.join(raw_name.split()).strip(' *_'); off = False
        if self.v19:
            voice = self.voice_of(name, mood)
            if voice: name, mood, off = voice, None, True
        if not spoken:
            if directions: self.action(number, f'{_display(name)} {directions[0]}'); return
            self.problem(number, f'„{name}:“ ohne Text, übersprungen.'); return
        self.spoken.add(name_key(name)); self.mark(number, 'spoken')
        if self.v19:
            # Every part of the parentheses counts: '(off, wütend)'. (V.O.), (Telefon) mean off-screen, (CONT'D), (zu Sandy) nothing.
            parts = [p.strip() for x in ([mood] if mood is not None else []) + directions for p in re.split(r'\s*[,;/]\s*', x) if p.strip()]
            off = off or any(OFF.match(p) for p in parts)
            moods = [p for p in parts if not OFF.match(p)]
            wish = next((p for p in moods if emotion_for(p)[1]), None)
            if wish is None: wish = next((p for p in moods if not IGNORED.match(p)), '')
        else: wish = mood if mood is not None else (directions[0] if directions else '')
        emotion, known = emotion_for(wish)
        if not known: self.problem(number, f'Sprechhaltung „{wish}“ kennt das Studio nicht, gesprochen wird „ruhig“.')
        pieces = _pieces(spoken, MAX_SPOKEN)
        if len(pieces) > 1: self.problem(number, f'Sehr langer Satz, in {len(pieces)} Teile geteilt. Die Wörter bleiben gleich.')
        scene['items'] += [{'kind': 'line', 'name': name, 'emotion': emotion, 'text': p, 'line': number, **({'off': True} if off else {})} for p in pieces]

    def figure(self, number, text, listed=False):
        name, description = _figure_line(text)
        if listed and not _is_name(name, {}, self.figures, keywords=self.kw): self.mark(number, 'note'); return     # prose in a '## Figuren' list
        if not name or len(name) > 60 or name_key(name) in self.kw:
            self.problem(number, 'FIGUR-Zeile ohne Namen, übersprungen. So geht es: „FIGUR: Oma – 70 Jahre, Schürze, streng“.'); return
        self.mark(number, 'figure')
        key = name_key(name); old = self.figures.get(key)
        if old: old['description'] = ' '.join(x for x in (old['description'], description) if x)[:1500]; return
        self.figures[key] = {'name': _spelling(name, self.text) if self.v19 else _display(name), 'description': description[:1500], 'line': number, 'declared': True}

    def flush_cue(self):
        if self.cue:
            c = self.cue; self.cue = None
            if not c['text'].strip(): self.problem(c['line'], f'„{c["name"]}“ ohne Text, übersprungen.'); return
            if len(c['rows']) > 1:
                self.problem(c['rows'][0], f'{_display(c["name"])} spricht diese Zeilen in einem Stück. Ist ein Teil davon eine Handlung, '
                                           'setz eine Leerzeile oder „AKTION:“ davor.', last=c['rows'][-1])
            for n in c['rows']: self.mark(n, 'spoken')
            self.say(c['line'], c['name'], c['mood'], c['text'])

    def speaker(self, label, named, cue):
        """A row that is clearly someone speaking: it ends a '## Hinweise' section."""
        if cue: return True
        if not named: return False
        name = label.group('name')
        return _caps(name) or label.group('mood') is not None or name_key(name) in self.figures or self.counts.get(name_key(name), 0) >= 2

    def unspoken(self, number, row, label, where):
        """A row that looks like someone speaking but is not spoken: never without a visible hint."""
        place = {'action': 'als stumme Handlung gezeigt', 'scene': 'beschreibt nur die Szene', 'film': 'beschreibt nur den Film'}[where]
        verb = 'wird nicht gesprochen, sondern ' + place if where == 'action' else 'wird nicht gesprochen, sie ' + place
        name = ' '.join(label.group('name').split()) if label else ''
        if label and _group(name):
            first = re.split(r'\s*(?:&|\+|/|,|\bund\b|\band\b)\s*', name)[0]
            example = first.upper() if first and name_key(first) not in GROUPS else 'NAME'
            self.problem(number, f'„{_short(row)}“ {verb}. Im Film sagt jeden Satz genau eine Figur: schreib einen Namen davor, '
                                 f'zum Beispiel „{example}: …“.')
        elif label:
            self.problem(number, f'„{_short(row)}“ {verb}. Soll „{name}“ eine Figur sein, die das sagt, schreib den Namen in Großbuchstaben: '
                                 f'„{name.upper()}: …“.')
        else:
            self.problem(number, f'„{_short(row)}“ {verb}. Was in Anführungszeichen steht, spricht nur eine Figur, deren Name davor steht: '
                                 '„OMA: …“.')

    # --- 0.19 only ---------------------------------------------------------------------------------

    def known(self):
        return list(self.figures) + [k for k, n in self.counts.items() if n] + list(self.spoken)

    def speaks(self, inner):
        n = inner.group('name')
        return (not _keyword(n, self.kw) and _is_name(n, self.counts, self.figures, keywords=self.kw)
                and (_caps(n) or name_key(n) in self.figures or inner.group('mood') is not None or self.counts.get(name_key(n), 0) >= 2))

    def table_row(self, number, row):
        """'| Zeit | Bild | Dialog |' tables: the header names the columns, each row is a line and its picture."""
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c): self.mark(number, 'structure'); return True
        roles = [next((role for role, pat in TABLE_ROLES if re.search(r'(?i)\b(?:' + pat + r')', c)), None) for c in cells]
        if self.table is None or (sum(r is not None for r in roles) >= 2 and not any(LABEL.match(c) for c in cells)):
            if sum(r is not None for r in roles) >= 2: self.table = roles; self.mark(number, 'structure'); return True
            return False
        row_of = {role: c for role, c in zip(self.table, cells) if role}
        text, who = row_of.get('text', ''), row_of.get('speaker', '')
        inner = LABEL.match(text) if text else None
        place = row_of.get('place', '')
        ep = self.ep()
        if place and (not ep or not ep['scenes'] or ep['scenes'][-1]['place'] != place): self.scene(number, place)
        picture = row_of.get('picture', '')
        if inner and self.speaks(inner): who, text, mood = inner.group('name'), inner.group('text'), inner.group('mood')
        else: mood = None
        if who and text:
            if picture: self.describe(number, picture, scene_only=True)
            self.used.pop(number, None); self.say(number, who, mood, text)
        elif picture: self.used.pop(number, None); self.action(number, picture, True)
        else: self.mark(number, 'structure')
        return True

    def pipe_row(self, number, row):
        """'0:00–0:04 | Hafen | SANDY: …': place, picture and the line in one row."""
        cells = [c.strip() for c in row.split('|') if c.strip()]
        inner = LABEL.match(cells[-1]) if len(cells) >= 2 else None
        if not (inner and inner.group('text').strip() and self.speaks(inner)): return False
        place = cells[0] if len(cells[0].split()) <= 4 else ''
        ep = self.ep()
        if place and (not ep or not ep['scenes'] or ep['scenes'][-1]['place'] != place): self.scene(number, place)
        for extra in cells[1 if place else 0:-1]: self.describe(number, extra, scene_only=True)
        self.used.pop(number, None); self.say(number, inner.group('name'), inner.group('mood'), inner.group('text')); return True

    # -----------------------------------------------------------------------------------------------

    def heading(self, number, level, content):
        content = _lead(content.strip().strip('*_ ').strip()).strip('*_ ')
        key = name_key(content.rstrip(':'))
        self.close(); self.mark(number, 'structure')
        if BEAT.match(content):                                                    # the internal '# 1 | Ort | was passiert'
            place, _, what = [x.strip() for x in content.split('|', 1)[1].partition('|')]
            self.scene(number, place, what); return
        m = SCENE_HEADING.match(content)
        if m: place, what = _scene_parts(m.group('rest'), self.v19); self.scene(number, place, what); return
        m = SLUG.match(content)
        if m: place, what = _scene_parts(m.group('rest'), self.v19); self.scene(number, _display(place), what); return
        if key in FIGURE_SECTIONS: self.open('figures', number, content); return
        if key in NOTE_SECTIONS: self.open('notes', number, content.rstrip(':')); return
        if key in NEUTRAL_SECTIONS: return
        if self.v19 and key in BLOCK_LABELS: return
        if not self.title and not self.episodes and level <= 2:
            self.title = re.sub(r'(?i)^titel\s*:\s*', '', content)[:100]; return
        if level >= 3:
            place, what = _scene_parts(content, self.v19); self.scene(number, place, what); return
        self.problem(number, f'Überschrift „{content[:60]}“ ist keine Folge und keine Szene. Für eine neue Szene schreib „### Szene – {content[:30]}“.')

    def read(self):
        rows = self.rows; i = 0; v19 = self.v19
        while i < len(rows):
            raw = rows[i]; number = i + 1; i += 1; after = None
            if raw.strip().startswith('```'): continue
            row, stamp = self.clean[number - 1]
            if stamp:
                if not self.stamped: self.stamped = True; self.problem(number, f'Zeitangaben wie „{stamp}“ setzt das Studio selbst, sie werden übersprungen.')
                if not row or name_key(row.strip(' :.-–—|*_')) in self.kw: self.mark(number, 'structure'); continue
            if not row or RULE.match(raw):
                self.flush_cue(); continue
            folge = HEADING.match(raw)
            if folge:
                self.flush_cue(); self.close(); self.mark(number, 'structure')
                title = re.sub(r'^[\s:.\-–—|*_]+', '', raw[folge.end(1):]).strip().strip('*_ #').strip()
                self.episode(int(folge.group(1)), title[:100], number); continue
            if row.startswith('#'):
                self.flush_cue(); level = len(row) - len(row.lstrip('#'))
                self.heading(number, level, row.lstrip('#')); continue
            following = self.clean[i][0] if i < len(rows) else ''
            label = LABEL.match(row); name = label.group('name') if label else ''
            # 0.19: a declared FIGUR wins over a label word of the same name.
            word = _keyword(name, self.kw) if label and not (v19 and name_key(name) in self.figures) else ''
            named = bool(label) and not word and _is_name(name, self.counts, self.figures, bool(label.group('text').strip()), self.kw)
            cue = None if label else _cue(row, following, self.kw)
            if self.section == 'notes':
                if not (self.speaker(label, named, cue) or SCENE.match(row) or SLUG.match(row)): self.notes['rows'].append(number); self.mark(number, 'note'); continue
                self.close(speaker=True)
            if self.cue:
                c = self.cue
                if not ((label and (word or named)) or (cue and c['text']) or SCENE.match(row) or SLUG.match(row) or TRANSITION.match(row)):
                    wrapped = WRAPPED.match(row)
                    if wrapped and (wrapped.group('a') is not None or wrapped.group('b') is not None):
                        if not c['text'] and c['mood'] is None: c['mood'] = (wrapped.group('a') or wrapped.group('b') or '').strip()
                        else: c['text'] = (c['text'] + ' ' + row).strip()
                        c['open'] = True; self.mark(number, 'spoken'); continue
                    if c['open'] or not self.dense or (v19 and _continues(c['text'], row, self.known())):
                        c['text'] = (c['text'] + ' ' + row).strip(); c['rows'].append(number); c['open'] = False; continue
                    after = c['name']
                self.flush_cue()
            if v19:
                if not row.startswith('|'): self.table = None
                if row.startswith('|') and row.count('|') >= 2 and self.table_row(number, row): continue
                if '|' in row and not label and self.pipe_row(number, row): self.last = number; continue
                if word and word not in ('titel', 'title', 'figur', 'figuren') and word not in PLACE_LABELS | ACTION_LABELS:
                    # 'Dialog: SANDY: „…“', 'Hook (0:00–0:03): PLANKTON: …': the label goes, the line is spoken.
                    inner_text = re.sub(r'^\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*', '', label.group('text')).strip()
                    inner = LABEL.match(_unstamp(inner_text, TIMESTAMP_19)[0])
                    if inner and inner.group('text').strip() and self.speaks(inner):
                        self.problem(number, f'„{_short(name, 30)}:“ davor wird übersprungen, der Satz von {_display(inner.group("name"))} wird gesprochen.')
                        self.say(number, inner.group('name'), inner.group('mood'), inner.group('text')); self.last = number; continue
                    if not label.group('text').strip() and word in BLOCK_LABELS: self.mark(number, 'structure'); continue
            if word in ('titel', 'title'):
                value = label.group('text').strip()[:100]; self.mark(number, 'structure')
                if self.folgen and self.episodes: self.episodes[-1]['title'] = value
                else: self.title = value
                continue
            if word in ('figur', 'figuren'):
                text = label.group('text').strip()
                if not text: self.open('figures', number, name); self.mark(number, 'structure'); continue
                for part in (_names(text) if word == 'figuren' else None) or [text]: self.figure(number, part)
                continue
            heading = _heading_row(row) if v19 else row
            scene, slug = SCENE.match(heading), SLUG.match(heading)
            if scene or slug:
                rest = (scene or slug).group('rest')
                place, what = _scene_parts(_scene_rest(rest) if v19 else rest, v19)
                self.scene(number, _display(place) if slug or (v19 and place.isupper()) else place, what); self.last = None; continue
            if v19 and STRUCTURE.match(re.sub(r'\d{1,2}:\d{2}', '', row)) and len(row.split()) <= 8 and not label:
                self.problem(number, f'Gliederung „{_short(row, 40)}“ wird nicht verfilmt.'); self.mark(number, 'skipped'); continue
            if self.section == 'figures':
                # Only list rows are figures; after a blank line, a spoken line or a long text the script goes on.
                previous = number >= 2 and (not self.clean[number - 2][0] or RULE.match(rows[number - 2]))
                said = label and (label.group('mood') is not None or len(label.group('text').split()) > 12 or label.group('text').rstrip()[-1:] in ('?', '!'))
                if BULLET.match(raw) or not (cue or said or (previous and self.figures)):
                    self.figure(number, row, listed=True); continue
                self.close()
            if word in PLACE_LABELS:
                ep = self.ep(); last = ep['scenes'][-1] if ep and ep['scenes'] else None; self.mark(number, 'structure')
                if last and not last['items'] and not last['place']: last['place'] = label.group('text').strip()
                else: self.scene(number, label.group('text').strip())
                continue
            if TRANSITION.match(row): self.mark(number, 'structure'); continue
            if word in ACTION_LABELS:
                self.action(number, label.group('text'), True); continue
            wrapped = WRAPPED.match(row)
            if wrapped:
                inner = next(g for g in wrapped.groups() if g is not None).strip()
                spoken = LABEL.match(inner) if wrapped.group('c') is not None or wrapped.group('d') is not None else None
                if spoken and not _keyword(spoken.group('name'), self.kw) and spoken.group('text').strip() and _is_name(spoken.group('name'), self.counts, self.figures, keywords=self.kw):
                    self.say(number, spoken.group('name'), spoken.group('mood'), spoken.group('text')); continue      # '*OMA: Hallo*'
                self.action(number, re.sub(r'(?i)^(?:aktion|action|handlung)\s*:\s*', '', inner), True); continue
            if word in (VISUAL_19 if v19 else VISUAL):
                self.describe(number, label.group('text').strip(), scene_only=True); continue
            if word in LOGLINE_LABELS:
                ep = self.ep(); self.mark(number, 'picture')
                (ep['logline'] if ep else self.preface).append(label.group('text').strip()); continue
            if word in (SOUND_19 if v19 else SOUND):
                self.problem(number, f'{word.capitalize()}-Angaben setzt das Studio selbst, die Zeile wird übersprungen.'); self.mark(number, 'skipped'); continue
            if word in (NOTE_19 if v19 else NOTE_LABELS):
                self.problem(number, f'„{_short(row)}“ wird nicht verfilmt.'); self.mark(number, 'skipped'); continue
            if named:
                if label.group('text').strip(): self.say(number, name, label.group('mood'), label.group('text')); self.last = number
                else: self.cue = {'line': number, 'name': ' '.join(name.split()), 'mood': label.group('mood'), 'text': '', 'rows': [], 'open': True}
                continue
            if cue:
                self.cue = {'line': number, 'name': cue.group('name').strip(), 'mood': cue.group('mood'), 'text': '', 'rows': [], 'open': True}
                continue
            if v19:
                known = self.known()
                dash = re.match(r'^(?P<name>[^\W\d_][^–—:„"]{0,40}?)\s+[–—]\s+(?P<text>.+)$', row)
                if dash and not label and _caps(dash.group('name')) and _is_name(dash.group('name'), self.counts, self.figures, keywords=self.kw):
                    self.say(number, dash.group('name'), None, dash.group('text')); self.last = number; continue        # 'SANDY – Montag …'
                prose = (re.match(r'^(?P<name>[^\W\d_][\w. ]{0,40}?)\s+' + SPEECH_VERB + r'\s*:\s*(?P<text>[„"»].+)$', row)
                         or re.match(r'^(?P<text>[„"»].+[“"«])[,]?\s+' + SPEECH_VERB + r'\s+(?P<name>[^\W\d_][\w. ]{0,40}?)\.?$', row))
                if prose and name_key(prose.group('name')) in known:
                    self.say(number, prose.group('name'), prose.group('verb'), prose.group('text').rstrip(',')); continue    # 'Sandy sagt: „…“'
                last = self.last; self.last = None
                if last == number - 1 and not label and not cue:
                    ep = self.ep(); item = ep['scenes'][-1]['items'][-1] if ep and ep['scenes'] and ep['scenes'][-1]['items'] else None
                    if item and item['kind'] == 'line' and _continues(item['text'], row, known):
                        # A sentence broken under its speaker ('SANDY: Montag, sieben Uhr.' + next row) goes on, with a hint.
                        extra = _speech(row, True)[0]
                        if len(item['text']) + 1 + len(extra) <= MAX_SPOKEN: item['text'] = item['text'] + ' ' + extra
                        else: ep['scenes'][-1]['items'].append({**item, 'text': extra, 'line': number})
                        self.problem(number, f'„{_short(row)}“ steht direkt unter dem Satz von {_display(item["name"])} und wird als Fortsetzung gesprochen. '
                                             'Ist es eine Handlung, schreib „AKTION:“ davor.')
                        self.mark(number, 'spoken'); self.last = number; continue
                    if item and item['kind'] == 'line': after = item['name']
            speechlike = bool(label and not word and label.group('text').strip() and len(name.split()) <= 4 and len(name) <= 40) \
                or bool(re.search(r'[„"»«“][^„"»«“”]*\w[^„"»«“”]*[“"«»”]', row))
            where = self.describe(number, row, staged=not speechlike)
            if label and not word and label.group('text').strip() and len(name.split()) <= 4 and len(name) <= 40: self.unspoken(number, row, label, where)
            elif re.search(r'[„"»«“][^„"»«“”]*\w[^„"»«“”]*[“"«»”]', row): self.unspoken(number, row, None, where)
            elif after and where == 'action':
                self.problem(number, f'„{_short(row)}“ ist eine stumme Handlung, kein Satz von {_display(after)}. Soll {_display(after)} das sagen, '
                                     'schreib es direkt hinter den Satz darüber.')
        self.flush_cue(); self.close()
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


def _timeline(cut):
    """0.19: (start, length, speech) of every shot as a project pinned with shot_policy 19 cuts it: silent
    shots last whole Wan clips (shot_design.silent_base), speech 2.6 words per second."""
    out = []; t = 0.; k = 0
    for shot in cut:
        speech = screenplay.spoken_seconds(shot['lines']) if shot['lines'] else 0
        if shot['kind'] == 'line': length = HEAD + speech + TAIL
        elif shot['kind'] == 'reaction': length = max(REACTION_MIN, HEAD + speech + REACTION_TAIL)
        elif shot['kind'] == 'establish': length = shot_design.ESTABLISH_FRAMES / FPS
        else: length = shot_design.ACTION_FRAMES[k % len(shot_design.ACTION_FRAMES)] / FPS; k += 1
        out.append((t, length, speech)); t += length
    return out


def pacing(cut, stated=None):
    """0.19: how much of an episode is speech, before anything is rendered. stated: the script's own length."""
    spans = _timeline(cut); total = sum(x[1] for x in spans); speech = sum(x[2] for x in spans)
    starts = [(t + HEAD, t + HEAD + s) for t, _, s in spans if s]
    first = starts[0][0] if starts else total; gaps = [first]; end = starts[0][1] if starts else total
    for a, b in starts[1:]: gaps.append(a - end); end = b
    gaps.append(total - end)
    basis = max(total, stated or 0)
    return {'seconds': round(total, 1), 'speech_seconds': round(speech, 1), 'speech_share': round(min(1., speech / basis), 2) if basis else 0,
            'first_word': round(first, 1), 'longest_silence': round(max(gaps), 1), 'silent_shots': sum(1 for s in cut if not s['lines']),
            'stated_seconds': stated}


def _stage(items, problem):
    """0.19: an AKTION that only sets the scene becomes the picture ('context') of the next line or AKTION of its
    scene; from its first event on it stays a silent shot. A scene with nothing else keeps it as a silent shot."""
    out = []
    for item in items:
        if not item.get('staged'): out.append(item); continue
        lead, rest = _setting(item['text'])
        if lead: out += [{'kind': 'context', 'text': p, 'line': item['line']} for p in _pieces(lead, MAX_CONTEXT)]
        pieces = _pieces(rest, MAX_ACTION) if rest else []
        if len(pieces) > 1: problem(item['line'], f'Sehr lange Handlung, als {len(pieces)} stumme Einstellungen gezeigt.')
        out += [{'kind': 'action', 'text': p, 'line': item['line']} for p in pieces]
    if any(x['kind'] == 'context' for x in out) and not any(x['kind'] != 'context' for x in out):
        out = [{'kind': 'action', 'text': p, 'line': x['line']} for x in items for p in _pieces(x['text'], MAX_ACTION)]
        for x in items:
            if len(_pieces(x['text'], MAX_ACTION)) > 1: problem(x['line'], f'Sehr lange Handlung, als {len(_pieces(x["text"], MAX_ACTION))} stumme Einstellungen gezeigt.')
    return out


def _stated(ep, text):
    """0.19: the episode's own length, from its scenes' time windows ('00:38 bis 00:58'), else from
    'jeweils ungefähr 58 Sekunden' anywhere in the script; None without either."""
    ends = [s['window'][1] for s in ep['scenes'] if s.get('window')]
    if ends and MIN_SECONDS <= max(ends) <= MAX_SECONDS: return max(ends)
    found = [int(m.group(1)) for m in STATED.finditer(text) if MIN_SECONDS <= int(m.group(1)) <= MAX_SECONDS]
    return found[0] if found else None


# screenplay.check speaks to the planner ("nötig", "umschreiben"); for Cay the same findings are advice.
ADVICE = ((r'^Zu wenig Sprecherwechsel: (\d+), nötig mindestens (\d+)\..*$', r'Wenig Sprecherwechsel: \1, empfohlen sind mindestens \2.'),
          (r'^Zu wenig AKTION-Zeilen: (\d+), nötig mindestens (\d+)\.$',
           r'Wenig AKTION-Zeilen: \1, empfohlen sind mindestens \2. Eine stumme Handlung bringt Bewegung in den Film.'),
          (r'^Zu lange Zeilen \(mehr als (\d+) Wörter\) aufteilen: ', r'Sätze mit mehr als \1 Wörtern: in zwei kürzere Sätze geteilt klingen sie lebendiger. '),
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


def read(text, policy=POLICY):
    """Read Cay's script. Returns title, figures, episodes (each with its normalized screenplay text
    in the internal format), problems (with line numbers; blocking ones stop the film), the length
    per episode and the minimum length the film is planned with. policy 19 (default, projects from
    0.19 on) adds per episode 'pacing' and a reading 'report'; policy 0 reads exactly as 0.18."""
    text = str(text or '').lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    r = _Reader(text.split('\n'), policy).read(); v19 = r.v19
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
        if not alias and declared and v19:
            # 'SANDY CHEEKS' for 'FIGUR: Sandy': one declared figure shares a name part of four or more letters.
            words = set(name_key(items[0]['name']).replace('.', ' ').split())
            parts = [d for d in declared if any(len(p) >= 4 and p in words for p in name_key(d).replace('.', ' ').split())]
            if len(parts) == 1:
                alias = parts[0]; r.problem(items[0]['line'], f'„{_display(items[0]["name"])}“ spricht als {alias}.')
        if alias: r.figures[key] = r.figures[name_key(alias)]; continue
        written = next((x['name'] for x in items if x['name'] != x['name'].upper()), items[0]['name'])
        r.figures[key] = {'name': _spelling(written, text) if v19 else _display(written), 'description': '', 'line': items[0]['line'], 'declared': False}
    figures = list({id(f): f for f in r.figures.values()}.values()); names = [f['name'] for f in figures]
    if len(names) > MAX_CAST: r.problem(None, f'Im Drehbuch stehen {len(names)} Figuren, höchstens {MAX_CAST} sind möglich.', True)
    for a in figures if len(names) <= MAX_CAST else ():
        for b in figures:
            if a is not b and not a['declared'] and len(name_key(a['name'])) >= 3 and name_key(a['name']) in name_key(b['name']).replace('.', ' ').split():
                r.problem(a['line'], f'„{a["name"]}“ und „{b["name"]}“ sind zwei Figuren. Ist es dieselbe, schreib den Namen überall gleich '
                                     f'oder leg „FIGUR: {b["name"]}“ an.')
    offs = {id(f) for key, items in spellings.items() for f in [r.figures[key]] if all(x.get('off') for x in items)}
    for f in figures:
        if name_key(f['name']) in NARRATORS and id(f) not in offs:
            r.problem(f['line'], f'„{f["name"]}“ ist im Film eine sichtbare Figur, die spricht. Eine Stimme ohne Bild gibt es nicht.'
                      + (' Soll jemand aus dem Off sprechen, schreib „(off)“ hinter den Namen, zum Beispiel „SANDY (off): …“.' if v19 else ''))
        elif name_key(f['name']) in NARRATORS:
            # 0.19: '(V.O.)' on a narrator: heard over the others' faces, never shown; it still needs a voice.
            r.problem(f['line'], f'„{f["name"]}“ spricht nur aus dem Off und ist im Film nie zu sehen. Für die Stimme legt das Studio trotzdem eine Figur an.')
        elif not f['declared'] and len(spellings.get(name_key(f['name']), ())) == 1 and not _caps(spellings[name_key(f['name'])][0]['name']):
            # 'Genre: Komödie', 'Das Problem: …': a label that speaks once may be no figure at all.
            r.problem(f['line'], f'„{f["name"]}“ spricht nur einmal. Ist das wirklich eine Figur? Wenn nicht, lösch die Zeile oder schreib „AKTION:“ davor.')
    episodes = []; series = len(r.episodes) > 1 or r.folgen
    for ep in r.episodes:
        label = f'Folge {ep["number"]}' if series else 'Dein Film'
        title = ep['title'] or ('' if series else r.title)
        out = [f'TITEL: {title}'] if title else []; expected = []; beats = 0; place = ''; logline = list(ep['logline']); contexts = []
        for scene in ep['scenes']:
            if not scene['items']:
                if not scene['explicit'] or not scene['what']: logline += scene['what']; continue
                r.problem(scene['line'], 'Szene ohne Satz und ohne AKTION, ihre Beschreibung wird als stumme Handlung gezeigt.')
                scene['items'] = [{'kind': 'action', 'text': p, 'line': scene['line']} for p in _pieces(' '.join(scene['what']), MAX_ACTION)]
                scene['what'] = []
            if v19: scene['items'] = _stage(scene['items'], r.problem)
            beats += 1; place = (scene['place'] or place).replace('|', '/')[:250]
            what = ' '.join(' '.join(scene['what']).replace('|', '/').split())[:800]
            out.append(f'# {beats} | {place} | {what}'.rstrip(' |'))
            for item in scene['items']:
                if item['kind'] == 'context':
                    out.append(f'BILD: {item["text"]}'); contexts.append(item['text'])
                    if not any(x['line'] == item['line'] and x['kind'] == 'action' for x in scene['items']): r.used[item['line']] = 'picture'
                elif item['kind'] == 'action':
                    out.append(f'AKTION: {item["text"]}'); expected.append(('action', '', item['text'], '', False, item['line']))
                else:
                    who = r.figures[name_key(item['name'])]['name']; off = bool(item.get('off'))
                    out.append(f'{who} [{item["emotion"]}{"|off" if off else ""}]: {item["text"]}')
                    expected.append(('line', who, item['text'], item['emotion'], off, item['line']))
        normalized = '\n'.join(out)
        title2, beat_list, lines, problems = screenplay.parse(normalized, names, **({'own': True} if v19 else {}))
        # Safety net: the stored screenplay reads back exactly as written, or the film does not start.
        got = [(l['kind'], l['speaker'], l['text'], l['emotion'], bool(l.get('off'))) for l in lines]
        wrong = next((e for e, g in zip(expected, got + [None] * len(expected)) if e[:5] != g), None)
        lost = ' '.join(contexts) != ' '.join(l['context'] for l in lines if l.get('context'))
        if problems or wrong or len(got) != len(expected) or lost:
            r.problem(wrong[5] if wrong else ep['line'], 'Diese Zeile liest das Studio anders, als sie geschrieben ist. Bitte umformulieren.', True)
        spoken = [l for l in lines if l['kind'] == 'line']
        cut = screenplay.shots(title2, beat_list, lines, names); seconds = round(_seconds(cut))
        if not spoken: r.problem(ep['line'], f'{label}: kein gesprochener Satz. Schreib Sätze so: „OMA (wütend): Wer hat meinen Kuchen gegessen?“', True)
        wordless = next((l['text'] for l in spoken if not re.search(r'[^\W_]', l['text'])), None)
        if wordless: r.problem(ep['line'], f'{label}: „{wordless[:40]}“ hat kein einziges Wort zum Sprechen. Bitte als Satz schreiben oder streichen.', True)
        elif seconds < MIN_SECONDS:
            r.problem(ep['line'], f'{label} dauert nach dem Drehbuch nur etwa {seconds} s. Ein Film braucht mindestens {MIN_SECONDS} s: '
                                  'schreib ein paar Sätze oder eine AKTION-Zeile dazu.', True)
        elif seconds > MAX_SECONDS:
            r.problem(ep['line'], f'{label} dauert nach dem Drehbuch etwa {seconds} s, höchstens {MAX_SECONDS} s gehen. Kürze das Drehbuch '
                                  + ('oder teile die Folge auf.' if series else 'oder teile es mit „## Folge 1“, „## Folge 2“ in mehrere Folgen.'), True)
        elif seconds > LONG_SECONDS:
            r.problem(ep['line'], f'{label} dauert etwa {seconds} s. Das geht, rechnet aber entsprechend länger als ein 90-s-Film.')
        if len(cut) > screenplay.OWN_MAX_SHOTS:
            r.problem(ep['line'], f'{label} ergibt {len(cut)} Einstellungen, höchstens {screenplay.OWN_MAX_SHOTS}. Weniger AKTION-Zeilen '
                                  'oder mehr Sätze derselben Figur hintereinander.', True)
        if spoken and not any(b['place'] and b['place'] != 'Ort' for b in beat_list):
            r.problem(ep['line'], ('Kein Ort angegeben' if not series else f'{label}: kein Ort angegeben') + '. Schreib zum Beispiel '
                                  '„### Szene 1 – Küche – Oma steht am Tisch“, dann weiß das Studio, wo es spielt.')
        if spoken and not problems and seconds <= MAX_SECONDS and len(cut) <= screenplay.OWN_MAX_SHOTS and len(names) <= MAX_CAST:
            for note in advice(title2, beat_list, lines, names): r.problem(None, (f'{label}: ' if series else 'Hinweis: ') + note)
        words = sum(screenplay.words(l['text']) for l in spoken)
        about = [' '.join(x.split()) for x in r.preface + logline + [b['what'] for b in beat_list] if x.strip()]
        plot = ' '.join(x if x[-1] in '.!?…' else x + '.' for x in about) or ' '.join(l['text'] for l in lines[:4])
        episodes.append({'number': ep['number'], 'title': title, 'text': normalized, 'scenes': len(beat_list), 'lines': len(spoken),
                         'words': words, 'actions': sum(l['kind'] == 'action' for l in lines),
                         'shots': len(cut), 'seconds': seconds, 'speakers': list(dict.fromkeys(l['speaker'] for l in spoken)),
                         'plot': plot[:1200], 'ending': (lines[-1]['text'] if lines else '')[:400]})
        if v19 and spoken:
            pace = episodes[-1]['pacing'] = pacing(cut, _stated(ep, text))
            for line in (l for l in lines if l.get('off')):
                shot = next((s for s in cut if any(x['text'] == line['text'] and x['speaker'] == line['speaker'] for x in s['lines'])), None)
                if shot and shot['kind'] != 'reaction':
                    r.problem(ep['line'], f'{label}: „{_short(line["text"], 40)}“ kommt nicht aus dem Off: in dieser Szene ist sonst niemand zu sehen, '
                                          f'darum spricht {line["speaker"]} im Bild.')
            r.problems += _pace_notes(label, words, pace, ep['line'])
    if not r.episodes: r.problem(None, 'Im Drehbuch steht kein gesprochener Satz. Schreib Sätze so: „OMA (wütend): Wer hat meinen Kuchen gegessen?“', True)
    said = {}
    for key, items in spellings.items(): said[id(r.figures[key])] = said.get(id(r.figures[key]), 0) + len(items)
    for f in figures: f['lines'] = said.get(id(f), 0)
    problems = sorted(r.problems, key=lambda p: (not p['blocking'], p['line'] or 0))
    shortest = min((e['seconds'] for e in episodes), default=60)
    # Planned with a little less than the estimate: the minimum length must not make the voices wait.
    duration = max(MIN_SECONDS, min(LONG_SECONDS, math.floor(shortest * .9)))
    if v19 and episodes and all('pacing' in e for e in episodes):
        # ... nor stretch the shorter silent shots of a pinned project (shot_design) back to 0.18 length.
        duration = max(MIN_SECONDS, min(duration, math.floor(min(e['pacing']['seconds'] for e in episodes))))
    result = {'title': r.title, 'figures': [{k: f[k] for k in ('name', 'description', 'lines', 'declared')} for f in figures], 'episodes': episodes,
              'problems': problems, 'ok': not any(p['blocking'] for p in problems), 'series': series,
              'words': sum(e['words'] for e in episodes), 'lines': sum(e['lines'] for e in episodes), 'scenes': sum(e['scenes'] for e in episodes),
              'seconds': sum(e['seconds'] for e in episodes), 'duration': duration,
              'preview': '\n\n'.join((f'## Folge {e["number"]}\n' if series else '') + e['text'] for e in episodes)}
    if v19: result.update(policy=POLICY, report=_report(r))
    return result


PACE_SHARE = .55        # below: little speech (r019: Cay's two series had 48–52 % without a word)
PACE_START = 3.0        # first word later than this: more than one silent shot before anyone speaks


def _pace_notes(label, words, pace, line):
    """0.19: plain advice before anything is rendered; the script is filmed as it is."""
    notes = []; basis = max(pace['seconds'], pace['stated_seconds'] or 0)
    if pace['speech_share'] < PACE_SHARE:
        silent = int(round((1 - pace['speech_share']) * 20)) * 5
        need = int(round(.65 * basis * screenplay.SPEECH_RATE / 5)) * 5
        notes.append(f'{label}: {words} gesprochene Wörter für ca. {round(basis)} s – etwa {silent} % ohne Sprache. '
                     f'Für etwa zwei Drittel Sprache wären es rund {need} Wörter. Deine Sätze bleiben, wie du sie geschrieben hast.')
    if pace['first_word'] > PACE_START:
        notes.append(f'{label}: Das erste Wort fällt erst nach etwa {round(pace["first_word"])} s. Auf TikTok entscheiden die ersten Sekunden, '
                     'ob jemand weiterschaut: lass früher jemanden sprechen.')
    return [{'line': line, 'text': n, 'blocking': False} for n in notes]


REPORT_KINDS = ('spoken', 'action', 'picture', 'figure', 'structure', 'note', 'skipped')


def _report(r):
    """0.19 reading report: every row with text is spoken, shown, used as picture, a figure, structure, a note
    that is not filmed, or skipped with a hint; 'unread' lists what the studio did not understand at all."""
    rows = [(n, row) for n, row in enumerate(r.rows, 1) if row.strip() and not RULE.match(row) and not row.strip().startswith('```')]
    counts = {k: 0 for k in REPORT_KINDS}; skipped = []; unread = []
    for n, row in rows:
        kind = r.used.get(n)
        if kind: counts[kind] += 1
        if kind == 'skipped': skipped.append({'line': n, 'text': _short(row, 80)})
        elif not kind: unread.append({'line': n, 'text': _short(row, 80)})
    return {'rows': len(rows), **counts, 'skipped_rows': skipped[:40], 'unread': unread[:40], 'unread_count': len(unread)}


def prepare(idea, policy=POLICY):
    """Create: an idea with story 'script' takes episodes, length, cast and title from the script.
    Any other idea keeps its exact previous document (no 'story' key). Raises ValueError (German).
    policy: the reading rules (POLICY for a new project, 0 for a project from before 0.19)."""
    if idea.get('story') != 'script':
        idea.pop('story', None); return None
    script = read(idea['idea'], policy)
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
