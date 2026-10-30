"""Cay after 0.19.1 ('Villa der süßen Lügen'): "Folgende: Valentina lächelt überlegen. Lara steckt ihr Handy weg." became a
speaking figure (a man in a suit read the direction aloud). With a FIGUR list a label outside it never speaks; and Cay
can mark any detected name as "keine Figur" in the script check (idea field not_figures)."""
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))
import own_script  # noqa: E402

LIST = """# Villa
## Figuren
FIGUR: MIRA – Erdbeere, rosa Kleid.
FIGUR: VALENTINA – Kirsche, rotes Kleid.
## Folge 1: Start
### Szene 1 – Pool
MIRA (fröhlich): Dann enttäusch mich bloß nicht.
FOLGENDE: Extreme Nahaufnahme von Valentinas hinterhältigem Grinsen.
Folgende: Valentina lächelt überlegen. Mira steckt ihr Handy weg.
VALENTINA (ruhig): Ich schaue nur.
"""
NO_LIST = """# Villa
## Folge 1: Start
### Szene 1 – Pool
MIRA: Dann enttäusch mich bloß nicht.
FOLGENDE: Valentina lächelt überlegen.
VALENTINA: Ich schaue nur.
FOLGENDE: Mira steckt ihr Handy weg.
MIRA: Ich will mehr Sätze, damit die Folge lang genug wird, sonst ist sie zu kurz für einen echten Film.
VALENTINA: Dann rede doch weiter, ich höre dir gern zu, auch wenn du nur Unsinn erzählst.
"""


def names(r): return [f['name'] for f in r['figures']]


def test_a_label_outside_the_figure_list_never_speaks():
    r = own_script.read(LIST)
    assert names(r) == ['Mira', 'Valentina'] and r['lines'] == 2
    assert 'AKTION: Valentina lächelt überlegen. Mira steckt ihr Handy weg.' in r['preview']
    assert any('„Folgende:“ steht nicht in deiner Figurenliste' in p['text'] and not p['blocking'] for p in r['problems'])


def test_cay_can_mark_a_detected_name_as_no_figure():
    assert 'Folgende' in names(own_script.read(NO_LIST))                    # no list: the reader cannot know
    r = own_script.read(NO_LIST, own_script.POLICY, ['Folgende'])
    assert names(r) == ['Mira', 'Valentina'] and r['lines'] == 4 and 'AKTION: Valentina lächelt überlegen.' in r['preview']
    idea = {'story': 'script', 'idea': NO_LIST, 'participants': [], 'title': '', 'not_figures': ['FOLGENDE']}
    assert [f['name'] for f in own_script.prepare(idea)['figures']] == ['Mira', 'Valentina']


def test_old_reading_rules_unchanged():
    assert 'Folgende' in names(own_script.read(LIST, 0))


def test_an_undeclared_speaker_still_speaks():
    r = own_script.read(LIST.replace("VALENTINA (ruhig): Ich schaue nur.", "POLIZIST: Hände hoch, ich sehe euch!"))
    assert 'Polizist' in names(r) and r['lines'] == 2
