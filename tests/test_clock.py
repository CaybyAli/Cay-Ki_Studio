"""Compute timer: overlapping steps count once, waits for Cay never, live only while a step runs."""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

from factory import Factory  # noqa: E402
from studio_resources import Resources  # noqa: E402

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def studio(clock):
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE performance_stages(id INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT,stage TEXT,resource TEXT,started TEXT,seconds REAL,status TEXT,detail TEXT)')
    resources = Resources.__new__(Resources); resources.running = {}; resources.tokens = 0
    resources.g = {'now': lambda: clock[0].isoformat()}
    factory = Factory.__new__(Factory); factory.g = {'resources': resources}
    factory.rows = lambda q, a=(): db.execute(q, a).fetchall()

    def note(project, end, seconds):            # rows are written when a step ends
        db.execute('INSERT INTO performance_stages(project,stage,resource,started,seconds,status,detail) VALUES(?,?,?,?,?,?,?)',
                   (project, 'x', 'GPU', end.isoformat(), seconds, 'done', '{}'))
    return factory, resources, note


def test_overlapping_steps_count_once():
    factory, _, note = studio([T0])
    note('p', T0 + timedelta(seconds=100), 100)                  # GPU 0..100
    note('p', T0 + timedelta(seconds=150), 80)                   # CPU 70..150 overlaps by 30
    note('p', T0 + timedelta(hours=3, seconds=10), 10)           # after a long wait for Cay
    assert factory.clocks()['p'] == {'seconds': 160, 'since': None}


def test_live_only_while_a_step_runs_and_never_across_a_wait():
    clock = [T0]; factory, resources, note = studio(clock)
    note('p', T0 + timedelta(seconds=400), 400)
    clock[0] = T0 + timedelta(hours=2)                           # Cay approves two hours later
    assert factory.clocks('p')['p']['since'] is None             # waiting: no live count
    token = resources.begin('p')
    since = factory.clocks('p')['p']['since']
    assert datetime.fromisoformat(since) == T0 + timedelta(hours=2)   # counts from the new step, not from 400 s
    resources.end(token)
    assert factory.clocks()['p']['since'] is None


def test_running_step_overlapping_the_last_measured_end_is_not_counted_twice():
    clock = [T0 + timedelta(seconds=50)]; factory, resources, note = studio(clock)
    resources.begin('p')                                         # CPU job starts at 50 s
    note('p', T0 + timedelta(seconds=100), 100)                  # GPU step 0..100 ends later
    assert datetime.fromisoformat(factory.clocks('p')['p']['since']) == T0 + timedelta(seconds=100)


def test_fresh_project_with_a_running_first_step():
    clock = [T0]; factory, resources, _ = studio(clock)
    resources.begin('n')
    assert factory.clocks()['n'] == {'seconds': 0, 'since': T0.isoformat()}
