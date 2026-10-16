"""The app's stylesheet must be balanced: an unclosed @media block silently limits every later
rule to one screen width (0.18: notification sheet and volume sliders were unstyled on the PC)."""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / 'cay_studio_app' / 'web'


def test_every_stylesheet_block_is_closed():
    for css in sorted(WEB.rglob('*.css')):
        text = re.sub(r'/\*.*?\*/', '', css.read_text(encoding='utf-8'), flags=re.S)
        text = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', '""', text)
        depth = 0
        for number, line in enumerate(text.split('\n'), 1):
            depth += line.count('{') - line.count('}')
            assert depth >= 0, f'{css.name}:{number}: closing brace without block'
        assert depth == 0, f'{css.name}: {depth} block(s) not closed'
