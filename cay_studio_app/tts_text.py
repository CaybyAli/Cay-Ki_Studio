"""0.19 spoken text (complaint C1): what Qwen3-TTS or Chatterbox read, apart from what was written.

Cay: "DIR" was spelled D-I-R. The line went to the voice model exactly as written, and both models
read a word in capitals like an initialism. In his 0.17 film 6 of 13 AI lines had such words
(MEIN, UNSER, DU, ZURÜCK, PLANKTON?!). Now, for projects created with sound_policy 19 only, the
speech job carries 'speech_text' and the figure names as 'vocabulary', and the two speech adapters
(factory_speech.py, factory_tts.py) read speakable(text) instead of the plain text:

- a word written in capitals for emphasis is read as a word: 'DIR' -> 'dir', 'KOFFER' -> 'Koffer',
  'SPONGEBOB' -> 'SpongeBob'. Its casing comes from a figure's name or the same word elsewhere in
  the line in mixed case, else capitalised after an article or with a noun ending, else lower
  case; capitalised at the start of a sentence. Never from other lines: a line's spoken text and
  cache signature depend on that line and the names only, so 'Text ändern' on one line never
  gives another line a new take (with the project's words, 'KOFFER' in an untouched line turned
  into 'koffer' once the edit removed the last 'Koffer');
- real initialisms stay: a list (USA, FBI, CIA, DNA, KI, OK, CEO, VIP, GPS, WLAN …) and every word
  in capitals without a vowel (PC, TV, DJ, LKW, PKW, SMS, BMW); interjections without a vowel
  ('PSST', 'HMM', 'GRRR') and Roman numerals after a name ('Ludwig XIV') are no initialisms;
- emoji, zero-width characters and *emphasis* marks go.
No word is added, removed or moved. The subtitles, the stored line ('text', 'text_de') and the
screenplay keep the writer's text. Old jobs carry no flag: same text, same cache signature, same
audio. Standard library only: this runs in both speech environments."""
import re
import unicodedata
from speech_quality import clean_text

POLICY = 19
# Initialisms a German speaker spells although they contain a vowel: kept as written. Words in
# capitals without a vowel are spelled anyway and need no entry.
ACRONYMS = {'OK', 'KI', 'USA', 'FBI', 'CIA', 'CEO', 'VIP', 'EU', 'ABC', 'IQ', 'ID', 'AG', 'ICE', 'EKG', 'ARD', 'BKA', 'LSD', 'DNA',
            'HIV', 'AI', 'IT', 'UV', 'EM', 'WM', 'USB', 'UK', 'NRW', 'ADHS', 'SUV', 'GPS', 'ADAC', 'DFB', 'WLAN', 'LAN', 'PDF', 'HD',
            'FAQ', 'AKW', 'AOK', 'OMG', 'LOL', 'ASAP', 'DIY', 'ATM', 'AKA', 'HQ', 'ETA', 'XXL', 'XL', 'VR', 'BH', 'ÖPNV', 'SOS', 'GEZ',
            'IOS', 'OP', 'US', 'EC', 'GEMA', 'DLRG'}
# Short forms read as one word: written like a name ('Nasa', 'Ufo'), never spelled.
SPOKEN = {'NASA', 'NATO', 'FIFA', 'UEFA', 'IKEA', 'ALDI', 'EDEKA', 'UFO', 'YOLO', 'EURO', 'BAFÖG', 'UNICEF', 'AIDS', 'TÜV', 'UNO',
          'ESA', 'IBAN', 'PIN', 'APP', 'LIDL', 'REWE'}
VOWELS = set('AEIOUÄÖÜY')
INTERJECTION = re.compile(r'^(?:P+S+T*|S+C+H+|H+M+|M+H+M*|P+F+|B+R+|G+R+|T+S+(?:T+S+)?|Z+|S+T+|K+R+)$')
ROMAN = re.compile(r'^(?=[MDCLXVI]{2,}$)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$')
# A word in capitals, apostrophes inside ("WAR'S"); never next to a digit ('MP3') or a lower-case letter.
WORD = re.compile(r"(?<![\w'’])([A-ZÄÖÜẞ][A-ZÄÖÜẞß]*(?:['’][A-ZÄÖÜẞß]+)?)(?![\w'’])")
LETTERS = re.compile(r"[^\W\d_]+")
DROP = {'So', 'Sk', 'Cs', 'Co', 'Cn'}                      # emoji, symbols, surrogates, private use, unassigned
DETERMINERS = {'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'einer', 'eines', 'mein', 'meine', 'meinen',
               'meinem', 'meiner', 'meines', 'dein', 'deine', 'deinen', 'deinem', 'deiner', 'sein', 'seine', 'seinen', 'seinem', 'seiner',
               'ihr', 'ihre', 'ihren', 'ihrem', 'ihrer', 'unser', 'unsere', 'unseren', 'unserem', 'euer', 'eure', 'euren', 'kein', 'keine',
               'keinen', 'keinem', 'keiner', 'diese', 'dieser', 'diesen', 'diesem', 'dieses', 'jede', 'jeder', 'jeden', 'jedem', 'jedes',
               'zum', 'zur', 'im', 'am', 'vom', 'beim', 'ins', 'ans'}
NOUN_END = re.compile(r'(?:ung|heit|keit|schaft|tion|tät|nis|chen|lein|ling|ismus|ment|eur)$')
SENTENCE_END = '.!?…:–—'


def _upper(word):
    letters = word.replace('ß', '').replace("'", '').replace('’', '')
    return len(word.replace("'", '').replace('’', '')) >= 2 and letters.isupper()


def initialism(word, before=''):
    """True for a word in capitals that is spoken letter by letter (or kept as written)."""
    plain = word.replace("'", '').replace('’', '')
    if plain in ACRONYMS: return True
    if ROMAN.match(plain): return bool(re.search(r'[A-ZÄÖÜ][a-zäöüß]+\s*$', before))     # 'Ludwig XIV', 'Teil II'
    if set(plain.replace('ß', 'SS')) & VOWELS: return False
    return not (INTERJECTION.match(plain) or re.search(r'(.)\1\1', plain))


def vocabulary(texts, names=()):
    """Casing of the project's own mixed-case words: 'koffer' -> 'Koffer'. A word seen only at the
    start of a sentence says nothing about its casing; figure names always count."""
    seen = {}
    for name in names:
        for w in LETTERS.findall(str(name)):
            if not _upper(w) and len(w) >= 2: seen[w.lower()] = w
    for text in texts:
        text = str(text or '')
        for m in LETTERS.finditer(text):
            w = m.group(0); before = text[:m.start()].rstrip(' "„“»«\'‚‘(')
            if _upper(w) or len(w) < 2 or not before or before[-1] in SENTENCE_END: continue
            seen.setdefault(w.lower(), w)
    return seen


def speakable(text, vocab=None):
    """The text for the voice model (see the module text). Without any change it is clean_text(text)."""
    vocab = vocab or {}
    text = unicodedata.normalize('NFC', str(text or '')).replace('​', '').replace('‍', '').replace('️', '')
    text = ''.join(' ' if unicodedata.category(c) in DROP else c for c in text)
    text = re.sub(r'(?<!\w)[*_]+(?=\w)|(?<=\w)[*_]+(?!\w)', '', text)
    out, last = [], 0
    for m in WORD.finditer(text):
        word = m.group(1); before = text[:m.start()]
        if not _upper(word) or initialism(word, before): continue
        low = word.lower().replace('ẞ', 'ß')
        head = before.rstrip(' "„“»«\'‚‘(')
        prior = (LETTERS.findall(head)[-1:] or [''])[0].lower()
        if low in vocab: plain = vocab[low]
        elif word in SPOKEN: plain = low[:1].upper() + low[1:]
        elif prior in DETERMINERS or NOUN_END.search(low): plain = low[:1].upper() + low[1:]
        else: plain = low
        if not head or head[-1] in SENTENCE_END: plain = plain[:1].upper() + plain[1:]
        out.append(text[last:m.start()] + plain); last = m.end()
    return clean_text(''.join(out) + text[last:])


def shouted(text):
    """Share of the words written in capitals for emphasis (initialisms excluded), 0..1."""
    words = [w for w in LETTERS.findall(str(text or '')) if len(w) >= 2]
    return round(sum(_upper(w) and not initialism(w) for w in words) / max(1, len(words)), 2)


# 0.19 voices (r019 B5e): a line of Cay's own script without a delivery in brackets was always spoken 'ruhig': one
# take, no level accent, the calm reference. own_script (policy 19) now asks delivery() instead. Only marks that say one
# thing decide; the words themselves never change and a written delivery wins. A plain '!' or '?' says nothing: threats,
# pleas, mockery and fear end in the same marks (review r019: of 35 lines that got 'begeistert', 'verwirrt' and the like
# from them, 3 matched the delivery the writer gave the same line). Such a line stays 'ruhig', as in 0.18.
INTERROBANG = re.compile(r'\?\s*!|!\s*\?')
HESITANT = re.compile(r'(?:…|\.\.\.)\s*$|(?:…|\.\.\.).*(?:…|\.\.\.)')


def delivery(text):
    """One of screenplay.EMOTIONS for a line written without one: mostly capitals or '!!' shouting; '?!' surprised
    ('Was?!'), shouting when a word in capitals or another '!' comes with it ('Was machst du da?! Das war UNSER Geld!');
    a trailing or repeated '…' hesitant (ängstlich); anything else, a plain '!' or '?' too, 'ruhig'."""
    text = unicodedata.normalize('NFC', str(text or '')).strip(); loud = shouted(text)
    if loud >= .6 or '!!' in text.replace(' ', ''): return 'schreiend'
    if INTERROBANG.search(text): return 'schreiend' if loud or text.count('!') > 1 else 'überrascht'
    if HESITANT.search(text): return 'ängstlich'
    return 'ruhig'


def job_fields(d, lines, cast):
    """Speech job fields for a project pinned with sound_policy 19, else {} (the job stays as before)."""
    try: pinned = int(d.get('sound_policy', 0) or 0) >= POLICY
    except (TypeError, ValueError): pinned = False
    if not pinned: return {}
    return {'speech_text': POLICY, 'vocabulary': vocabulary([], [p['name'] for p in cast])}


def spoken(line, job):
    """What the adapter hands to the model for one line of `job`: from that line and the job's names alone."""
    if int(job.get('speech_text', 0) or 0) >= POLICY: return speakable(line['text'], {**vocabulary([line['text']]), **(job.get('vocabulary') or {})})
    return clean_text(line['text'])


def signature_fields(line, job):
    """Extra cache signature fields: only when the model reads other text than before."""
    text = spoken(line, job)
    return {'spoken': text} if text != clean_text(line['text']) else {}
