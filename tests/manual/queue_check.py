"""Queue order shown to Cay = worker order. Maintenance mode keeps the worker idle.
Run: python tests/manual/queue_check.py <empty dir>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

s = Studio(sys.argv[1], {'CAY_STUDIO_START_MAINTENANCE': '1'}); r = Report()
try:
    for i, (rid, state) in enumerate([('1' * 32, 'rendering'), ('2' * 32, 'planning'), ('3' * 32, 'voicing'), ('4' * 32, 'voice_review')]):
        s.project(rid, state, {'title': f'Film {i + 1}'}, paused=0)
        s.db.execute('UPDATE factory_runs SET created=? WHERE id=?', (f'2026-10-13T10:0{i}', rid)); s.db.commit()
    _, data = s.call('/api/factory')
    q = {x['id'][0]: x['queue'] for x in data['runs']}
    r.check(f'Warteschlange in Erstellreihenfolge {q}', q == {'1': 0, '2': 1, '3': 2, '4': None})
    _, speed = s.call('/api/factory/speed'); r.check('Messwert-Schnittstelle antwortet', isinstance(speed, dict))
    code, t = s.call('/api/factory/turbo'); r.check(f'Turbo-Status abrufbar ({t.get("state")})', code == 200 and t.get('state') == 'missing')
finally:
    s.close()
r.done()
