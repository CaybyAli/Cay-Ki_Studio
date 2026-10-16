"""Cay's 6-episode test has 13 figures: the cast limit is 30 everywhere (input, plan, planner schema)."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

from factory_models import Idea, SeriesPlan, MAX_CAST  # noqa: E402
from story_source import SeriesHeader  # noqa: E402


def idea(n):
    return {'request_key': 'a' * 32, 'idea': 'Eine große Serie mit vielen Figuren.', 'episodes': 6,
            'participants': [{'name': f'Figur {i}', 'traits': 'freundlich'} for i in range(n)]}


def test_thirteen_figures_are_accepted_everywhere():
    assert MAX_CAST >= 13
    assert len(Idea.model_validate(idea(13)).participants) == 13
    cast = [{'name': f'Figur {i}', 'appearance': 'a small round figure', 'personality': 'kind'} for i in range(13)]
    plan = {'title': 'Serie', 'synopsis': 'Eine lange Geschichte.', 'style': 'Bright cartoon style.', 'visual': 'cartoon', 'mood': 'playful',
            'cast': cast, 'episodes': [{'title': 'Folge', 'plot': 'Etwas passiert hier.', 'ending': 'Ende.'}]}
    assert len(SeriesPlan.model_validate(plan).cast) == 13
    assert len(SeriesHeader.model_validate({k: plan[k] for k in ('title', 'synopsis', 'style', 'visual', 'mood', 'cast')}).cast) == 13
    assert SeriesHeader.model_json_schema()['properties']['cast']['maxItems'] == MAX_CAST


def test_the_bound_still_exists():
    with pytest.raises(ValidationError):
        Idea.model_validate(idea(MAX_CAST + 1))
