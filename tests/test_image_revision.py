"""'Neue Bilder' must really look new: Cay asked five times and got the same picture. New rounds vary
camera and pose; the newest wish leads the prompt instead of piling up at the end."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

import cast_design  # noqa: E402

BASE = 'One coherent vertical 9:16 film frame. Scene: Patrick stands on the beach.'


def test_round_zero_is_the_plan_as_written():
    assert cast_design.revision_prompt(BASE, '', 0, 0, 18) == BASE


def test_every_new_round_and_variant_takes_another_camera_and_pose():
    prompts = {cast_design.revision_prompt(BASE, '', r, v, 18) for r in range(1, 4) for v in range(2)}
    assert len(prompts) == 6 and all('Fresh take' in p for p in prompts)


def test_the_newest_wish_leads_the_prompt():
    p = cast_design.revision_prompt(BASE, 'Patrick sitzt auf einem Stein.', 1, 0, 18)
    assert p.startswith('Most important, requested by the director: Patrick sitzt auf einem Stein. ')
    legacy = cast_design.revision_prompt(BASE, 'old note', 0, 0, 0)               # older projects keep the old place
    assert legacy == BASE + ' Specific correction: old note'
