"""Shared inputs for the 0.18 cutting tests and the 0.17 reference (tests/fixtures/v17_reference.json).

The reference holds what the 0.17 code (commit 201ef32) made from exactly these inputs:
screenplay cut, assembled scenes, checks, sound layout 17, motion text and image faces.
Projects planned or voiced before 0.18 must keep producing exactly that.
"""
import copy

CAST = ['SpongeBob', 'Mr. Krabs', 'Patrick', 'Plankton']

# Cay's 0.17 film "Der Einbruch im Krusty-Versteck 2", reconstructed from its subtitles:
# 13 lines, speaker order SB K SB K Pa Pl K Pl SB K Pl K Pl, four silent action shots.
CAY_PINGPONG = '''TITEL: Der Einbruch im Krusty-Versteck 2
# 1 | Düstere Höhle mit Holztisch | SpongeBob zahlt Mr. Krabs Schutzgeld
SPONGEBOB [flehend]: Herr Krabs, ich hab nur noch diese paar Münzen, bitte!
MR. KRABS [drohend]: Das ist MEIN Schutzgeld, Bub! Und es fehlt noch die Hälfte!
AKTION: Mr. Krabs packt SpongeBob am Kragen und hebt ihn hoch.
SPONGEBOB [ängstlich]: Au! Ich zahl ja – aber bitte nicht so brutal, Herr Krabs!
MR. KRABS [wütend]: Brutal? Ich bin fair! Ich nehme nur, was mir zusteht.
# 2 | Nebliges Dorf auf einem Hügel | Patrick schaut durch ein Fernglas
PATRICK [überrascht]: Hey … ist das SpongeBob da unten? Oh nein, nee nee nee …
# 3 | Höhleneingang mit Lieferwagen | Plankton fährt mit einem Lieferwagen vor
AKTION: Plankton steigt aus dem Lieferwagen und schleicht in die Höhle.
PLANKTON [spöttisch]: Abend, Jungs. Ich bin doch zum richtigen Termin hier, oder?
MR. KRABS [schreiend]: PLANKTON?! Wie kommst du hierher? Das ist meine Beute!
PLANKTON [triumphierend]: Deine Beute? Ab heute ist das hier MEIN Geschäft.
SPONGEBOB [wütend]: Was machst du da?! Das war doch UNSER Geld!
MR. KRABS [wütend]: Und DU quatschst hier noch dazwischen?! Halt den Mund!
AKTION: Plankton wirft die Münzen in hohem Bogen in seinen Lieferwagen.
PLANKTON [spöttisch]: Euer Geld? Nee, Kleiner. Ich hab etwas viel Besseres vor.
MR. KRABS [schreiend]: Was meinst du?! Ich will mein Geld ZURÜCK, sofort!
PLANKTON [drohend]: In drei Sekunden wünsch ich euch beiden viel Erfolg.
AKTION: SpongeBob und Mr. Krabs starren sich verdutzt an.
'''

# The same story the way the 0.18 rules ask for it: speech blocks of two or three lines.
CAY_BLOCKS = '''TITEL: Der Einbruch im Krusty-Versteck 2
# 1 | Düstere Höhle mit Holztisch | SpongeBob zahlt Mr. Krabs Schutzgeld
SPONGEBOB [flehend]: Herr Krabs, ich hab nur noch diese paar Münzen.
SPONGEBOB [flehend]: Bitte, mehr hab ich diese Woche wirklich nicht, ehrlich!
MR. KRABS [drohend]: Das ist MEIN Schutzgeld, Bub! Und es fehlt noch die Hälfte!
MR. KRABS [wütend]: Ich nehme nur, was mir zusteht. Das ist doch fair.
AKTION: Mr. Krabs packt SpongeBob am Kragen und hebt ihn hoch.
SPONGEBOB [ängstlich]: Au! Ich zahl ja, aber bitte nicht so brutal!
SPONGEBOB [flehend]: Morgen bring ich den Rest, versprochen, Herr Krabs.
# 2 | Höhleneingang mit Lieferwagen | Plankton lehnt grinsend an seinem Lieferwagen
PLANKTON [spöttisch]: Abend, Jungs. Ich bin doch zum richtigen Termin hier, oder?
PLANKTON [triumphierend]: Ab heute ist das hier nämlich MEIN Geschäft.
MR. KRABS [schreiend]: PLANKTON?! Wie kommst du hierher? Das ist meine Beute!
MR. KRABS [wütend]: Raus aus meiner Höhle, du winziger Wurm!
SPONGEBOB [wütend]: Genau! Das war doch UNSER Geld!
AKTION: Plankton wirft die Münzen in hohem Bogen in seinen Lieferwagen.
PLANKTON [spöttisch]: Euer Geld? Nee, Kleiner. Ich hab etwas viel Besseres vor.
PLANKTON [drohend]: In drei Sekunden wünsch ich euch beiden viel Erfolg.
'''

OMA_CAST = ['Oma', 'Tim', 'Opa']
OMA = '''TITEL: Der verschwundene Kuchen
# 1 | Küche | Oma steht vor einem leeren Teller, Krümel auf dem Boden
OMA [wütend]: Wer hat meinen Kuchen gegessen? Ich zähl bis drei!
OMA [drohend]: Und wer jetzt lügt, kriegt eine Woche lang keinen Nachtisch.
TIM [ängstlich]: Ich war's nicht, ehrlich! Ich war die ganze Zeit im Bad.
TIM [flehend]: Frag doch Opa, der hat mich gesehen, ganz bestimmt!
OMA [spöttisch]: Im Bad. Mit Sahne an der Nase?
AKTION: Tim wischt sich hastig die Nase und versteckt die Hände hinter dem Rücken.
# 2 | Garten mit Hängematte | Opa schläft in der Hängematte, ein Teller auf dem Bauch
OMA [überrascht]: Opa! Und was liegt da auf deinem Bauch?
OPA [verwirrt]: Hm? Ach, das … das ist nur ein Kissen, Liebling.
OPA [fröhlich]: Ein sehr leckeres Kissen übrigens, mit Kirschen drauf.
OPA [triumphierend]: Und Tim hat mir das letzte Stück gebracht, der kleine Held!
TIM [panisch]: Opa! Das solltest du doch nicht verraten!
TIM [flehend]: Oma, es tut mir leid, ich back dir einen neuen!
OMA [fröhlich]: Gut. Dann backt ihr zwei heute zusammen. Zwei Kuchen.
'''

# One speaker with many long lines: the merge limit decides the cut.
LONG_TALK = '''TITEL: Die Rede
# 1 | Bühne | Plankton hält eine Rede
PLANKTON [triumphierend]: Meine Damen und Herren, heute ist der Tag, an dem sich alles in Bikini Bottom ändert!
PLANKTON [drohend]: Wer mir nicht folgt, der wird es bereuen, das verspreche ich euch hier und jetzt.
PLANKTON [spöttisch]: Ha! Seht euch nur eure ängstlichen Gesichter an.
PLANKTON [fröhlich]: Und jetzt alle: Applaus für den neuen Herrscher!
SPONGEBOB [verwirrt]: Ähm, Plankton? Du stehst auf der falschen Bühne.
AKTION: Plankton fällt vom Rednerpult.
'''

TEXTS = {'cay_pingpong': (CAY_PINGPONG, CAST), 'cay_blocks': (CAY_BLOCKS, CAST), 'oma': (OMA, OMA_CAST), 'long_talk': (LONG_TALK, CAST)}

SPEECH_RATE = 2.6   # words per second, measured in Cay's 0.17 film


def visuals_for(cut):
    """Planner answer for every second shot; stills name an off-screen figure on purpose."""
    shots = []
    for i, shot in enumerate(cut):
        if i % 2: continue
        who = shot['visible'][0] if shot['visible'] else 'The place'
        shots.append({'shot': i + 1, 'still': f'{who} in the cave, Mr. Krabs looming behind, warm lamp light',
                      'motion': f'{who} points at Patrick and steps back', 'camera': 'medium shot', 'ambience': 'room'})
    return {'shots': shots}


def timed_lines(episode, rate=SPEECH_RATE):
    """Lines as factory_quality makes them, with a speaking time of words/rate seconds."""
    lines = []
    for si, scene in enumerate(episode['scenes']):
        for ti, line in enumerate(scene.get('dialogues') or []):
            words = len(line['text'].split())
            lines.append({'episode': 0, 'scene': si, 'turn': ti, 'speaker': line['speaker'], 'text': line['text'],
                          'emotion': line['emotion'], 'pause_after': line.get('pause_after', .15),
                          'duration': round(words / rate + .2, 3)})
    return lines


def layout_cases():
    """Hand-made episodes for the sound layout: rich and plain, with and without silent shots,
    a talking shot over 15 s, a film that is too short and one that is long enough."""
    def scene(seconds=4): return {'seconds': seconds}
    def line(si, duration, turn=0, pause=.18): return {'episode': 0, 'scene': si, 'turn': turn, 'duration': duration, 'pause_after': pause, 'speaker': 'x'}
    cases = []
    durations = [(0.98, 1.04), (2.4, 1.56), (0.91, 1.59), (1.7, 0.94), (1.16,), (0.88, 2.23), (0.98, 1.4), (1.3, 1.2), (1.5, 1.1), (1.3, 1.2)]
    lines = [line(si, d, t) for si, g in enumerate(durations) for t, d in enumerate(g)]
    cases.append({'episode': {'scenes': [scene() for _ in durations] + [scene(), scene()], 'dialogue_mode': 'rich', 'minimum_seconds': 60}, 'lines': lines, 'minimum': 60})
    cases.append({'episode': {'scenes': [scene() for _ in durations], 'dialogue_mode': 'rich', 'minimum_seconds': 60}, 'lines': copy.deepcopy(lines), 'minimum': 60})
    cases.append({'episode': {'scenes': [scene(5), scene(3), scene(6)], 'minimum_seconds': 20}, 'lines': [line(0, 2.0), line(0, 1.5, 1), line(2, 3.1)], 'minimum': 20})
    cases.append({'episode': {'scenes': [scene(16), scene(3)], 'dialogue_mode': 'rich', 'minimum_seconds': 15},
                  'lines': [line(0, 4.2, t, .3) for t in range(4)], 'minimum': 15})
    cases.append({'episode': {'scenes': [scene(), scene(), scene()], 'dialogue_mode': 'rich', 'minimum_seconds': 6},
                  'lines': [line(0, 1.35, 0, .3), line(0, 1.35, 1, .3), line(1, 3.0)], 'minimum': 6})
    cases.append({'episode': {'scenes': [scene(4), scene(4)], 'minimum_seconds': 15}, 'lines': [], 'minimum': 15})
    return cases


MOTION_SCENES = [
    {'cast': ['SpongeBob'], 'kind': 'line'},
    {'cast': ['SpongeBob', 'Mr. Krabs'], 'kind': 'action'},
    {'cast': [], 'kind': 'action'},
    {'cast': ['Plankton'], 'kind': 'scene'},
    {'cast': ['Mr. Krabs'], 'kind': 'line'},
]
MOTION_LINES = [[{'speaker': 'SpongeBob', 'offset': .08, 'duration': 2.1}], [], [], [], [{'speaker': 'Mr. Krabs', 'offset': .08, 'duration': 3.0}, {'speaker': 'Mr. Krabs', 'offset': 3.3, 'duration': 1.2}]]
