"""Autopilot with the real dashboard worker. Run: python tests/manual/autopilot_check.py <empty dir>"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

studio = Studio(sys.argv[1]); r = Report()
try:
    scene = lambda: {'title': 'Keks', 'cast': ['Lena'], 'dialogues': [], 'round': 0, 'selected': None,
                     'variants': [{'id': 'a' * 32, 'key': 'image:0:0:0:0'}, {'id': 'b' * 32, 'key': 'image:0:0:0:1'}]}
    studio.project('1' * 32, 'image_review', {'episodes': [{'title': 'K', 'scenes': [scene(), scene()]}]}, {'autopilot': True}, paused=0)
    studio.project('2' * 32, 'image_review', {'episodes': [{'title': 'K', 'scenes': [scene()]}]}, {'autopilot': False}, paused=0)
    studio.project('3' * 32, 'sample_review', {'sample': {'key': 'k1'}}, {'autopilot': True}, paused=1)
    time.sleep(6)
    _, a = studio.call('/api/factory/' + '1' * 32); _, m = studio.call('/api/factory/' + '2' * 32)
    r.check('Autopilot: Bildauswahl ohne Klick übernommen', a['state'] != 'image_review' and all(s['selected'] == 'a' * 32 for s in a['episodes'][0]['scenes']))
    r.check('Ohne Autopilot: wartet weiter auf Cay', m['state'] == 'image_review' and m['episodes'][0]['scenes'][0]['selected'] is None)
    _, s = studio.call('/api/factory/' + '3' * 32)
    r.check('Pausiertes Projekt wird nicht angefasst', s['state'] == 'sample_review')
    code, s = studio.call('/api/factory/' + '3' * 32 + '/resume', {})
    time.sleep(4); _, s = studio.call('/api/factory/' + '3' * 32)
    r.check('Nach Fortsetzen: Probe automatisch übernommen', s['state'] != 'sample_review' and s.get('sample_approval') == 'k1')
    code, m = studio.call('/api/factory/' + '2' * 32 + '/autopilot', {'enabled': True})
    time.sleep(4); _, m = studio.call('/api/factory/' + '2' * 32)
    r.check('Autopilot nachträglich einschaltbar', code == 200 and m['state'] != 'image_review')
finally:
    studio.close()
r.done()
