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


# ---------- 0.19 design pass: the studio app (web/app2) ----------
APP = WEB / 'app2'
WORD = re.compile(r'[A-Za-z_$][\w$]*|\d[\w.]*')
REGEX_AFTER = set('(,=:[!&|?{};+-*%<>~^') | {'', 'return', 'typeof', 'case', 'in', 'of', 'new', 'delete', 'void', 'throw', 'else', 'do', '=>'}


def js_plain_strings(src):
    """Every '…' and "…" literal of a script as (line, text): comments, regex literals and the text of `…` templates
    are skipped, code inside ${…} is read like any other code."""
    found, i, n, stack, last = [], 0, len(src), [], ''

    def template(i):                                  # i: just after ` or after the } closing a ${…}
        while i < n:
            if src[i] == '\\': i += 2; continue
            if src[i] == '`': return i + 1, True
            if src.startswith('${', i): stack.append(0); return i + 2, False
            i += 1
        return i, True

    while i < n:
        c = src[i]
        if c.isspace(): i += 1; continue
        if src.startswith('//', i): j = src.find('\n', i); i = n if j < 0 else j; continue
        if src.startswith('/*', i): i = src.index('*/', i) + 2; continue
        if c in '\'"':
            j = i + 1
            while src[j] != c: j += 2 if src[j] == '\\' else 1
            found.append((src.count('\n', 0, i) + 1, src[i + 1:j])); i, last = j + 1, 'str'; continue
        if c == '`': i, _ = template(i + 1); last = 'str'; continue
        if c == '/' and last in REGEX_AFTER:
            j, klass = i + 1, False
            while src[j] != '/' or klass:
                if src[j] == '\\': j += 1
                elif src[j] == '[': klass = True
                elif src[j] == ']': klass = False
                j += 1
            i, last = j + 1, 'regex'
            while i < n and src[i].isalpha(): i += 1
            continue
        if c == '{' and stack: stack[-1] += 1
        if c == '}' and stack:
            if stack[-1] == 0: stack.pop(); i, _ = template(i + 1); last = 'str'; continue
            stack[-1] -= 1
        m = WORD.match(src, i)
        if m: i, last = m.end(), m.group(); continue
        if src.startswith('=>', i): i, last = i + 2, '=>'; continue
        i, last = i + 1, c
    return found


def test_a_placeholder_is_never_written_into_a_plain_string():
    """'…${TRASH}…' is printed as it stands: the trash page showed „${TRASH} Papierkorb leeren“ (0.19 design pass)."""
    strings = js_plain_strings((APP / 'app.js').read_text(encoding='utf-8'))
    assert len(strings) > 500 and any(text == 'Rückgängig' for _, text in strings)   # the reader really reads the app
    assert [(line, text[:60]) for line, text in strings if '${' in text] == []


def css_rules(path):
    """(selector, declarations) of every innermost block, comments removed."""
    text = re.sub(r'/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)
    return [(' '.join(s.split()), body) for s, body in re.findall(r'([^{}]+)\{([^{}]*)\}', text)]


def tokens(body):
    return dict((k.strip(), v.strip()) for k, v in re.findall(r'(--[\w-]+)\s*:\s*([^;]+)', body))


def test_focus_ring_keeps_the_shape_of_what_has_focus():
    """A radius in the global focus rule turned every pill button into a box while it had focus."""
    rules = [body for sel, body in css_rules(APP / 'app.css') if sel == ':focus-visible']
    assert rules and all('outline' in body and 'border-radius' not in body for body in rules)


def test_reduced_motion_also_stops_hover_zoom():
    text = re.sub(r'/\*.*?\*/', '', (APP / 'app.css').read_text(encoding='utf-8'), flags=re.S)
    block = text.split('@media (prefers-reduced-motion: reduce)', 1)[1]
    block = block[:block.index('\n}')]
    assert 'animation: none' in block and 'transition: none' in block and 'transform: none' in block and '.tile-link:hover .frame' in block


def test_dark_mode_is_the_same_by_system_setting_and_by_the_moon_button():
    rules = css_rules(APP / 'app.css')
    light = tokens(next(body for sel, body in rules if sel == ':root'))
    by_system = tokens(next(body for sel, body in rules if sel == ':root:not([data-theme="light"])'))
    by_button = tokens(next(body for sel, body in rules if sel == ':root[data-theme="dark"]'))
    assert by_system == by_button and set(by_system) <= set(light)
    for colour in ('--canvas', '--surface', '--ink', '--placeholder', '--toast-bg', '--toast-action'):
        assert colour in by_system, colour


def test_every_token_the_stylesheet_uses_is_defined():
    text = (APP / 'app.css').read_text(encoding='utf-8')
    light = tokens(next(body for sel, body in css_rules(APP / 'app.css') if sel == ':root'))
    assert sorted(set(re.findall(r'var\((--[\w-]+)', text)) - set(light)) == []
