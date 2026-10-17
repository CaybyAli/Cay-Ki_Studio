"""Unterwegs-Zugriff: the guard accepts localhost and exactly the configured Tailscale host (both
Host variants Serve may send), a remote request can neither switch it on nor off, honest German
messages for every Tailscale state, the studio link in notifications only while it is on, and the
address goes to Telegram only on Cay's click. Tailscale itself is a fake CLI (tailscale_fake.py)."""
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))
sys.path.insert(0, str(Path(__file__).parent))

import remote_access  # noqa: E402
from remote_access import Remote, split_host  # noqa: E402
from tailscale_fake import FakeTailscale  # noqa: E402

HOST = 'cay-pc.tail1234.ts.net'
REMOTE = {'host': HOST, 'origin': 'https://' + HOST}                                   # Serve keeps the Host
REWRITTEN = {'host': '127.0.0.1:8787', 'origin': 'https://' + HOST, 'x-forwarded-for': '100.101.102.103',
             'x-forwarded-proto': 'https'}                                              # Serve rewrites it
TOKEN = '7712345678:AAHk3xQ9vYfZpL2mN8rT5wB1cD4eF6gH7iJ'


@pytest.fixture
def studio(tmp_path, monkeypatch):
    runtime = tmp_path / 'studio'; (runtime / 'config').mkdir(parents=True); (tmp_path / 'ablage').mkdir()
    (runtime / 'config/ablage.json').write_text(json.dumps({'wsl_root': str(tmp_path / 'ablage'), 'windows_root': 'D:\\Cay_Studio',
                                                            'local_services': {'comfyui': 'http://127.0.0.1:9', 'ollama': 'http://127.0.0.1:9'}}))
    monkeypatch.setenv('CAY_STUDIO_RUNTIME', str(runtime)); monkeypatch.delenv('CAY_STUDIO_PORT', raising=False)
    fake = FakeTailscale(tmp_path / 'tailscale'); monkeypatch.setenv('CAY_TAILSCALE', str(fake.exe))
    sys.modules.pop('server', None)
    import server
    from fastapi.testclient import TestClient
    server.init_db(); server.notifier.init()
    client = TestClient(server.app, base_url='http://127.0.0.1')
    token = {'X-Cay-Token': server.CSRF}
    return server, client, fake, token


def enable(client, token):
    answer = client.post('/api/remote/enable', headers=token)
    assert answer.status_code == 200, answer.text
    return answer.json()


def code(client, path='/api/health', method='GET', **headers):
    return client.request(method, path, headers=headers).status_code


def test_guard_accepts_localhost_and_only_the_configured_host(studio):
    server, client, fake, token = studio
    for host in ('127.0.0.1', '127.0.0.1:8787', 'localhost:8787', '[::1]:8787'):
        assert code(client, host=host) == 200, host
    assert code(client, host=HOST) == 403 and code(client, host='evil.example') == 403          # off: no remote host at all
    state = enable(client, token)
    assert state['enabled'] and state['url'] == 'https://' + HOST and state['here'] == 'pc' and not state['problem']
    assert ['serve', '--bg', '8787'] in fake.calls() and not any('funnel' in ' '.join(c) for c in fake.calls())
    stored = json.loads((server.RUNTIME / 'config/unterwegs.json').read_text())
    assert stored['enabled'] and stored['host'] == HOST
    for host in (HOST, HOST + ':443', HOST.upper(), '127.0.0.1:8787', 'localhost'):
        assert code(client, host=host) == 200, host
    for host in ('other.tail1234.ts.net', HOST + '.evil.example', HOST + ':8787', 'x' + HOST, 'tail1234.ts.net', 'ts.net', 'evil.example', ''):
        assert code(client, host=host) == 403, host
    answer = client.get('/api/health', headers={'host': 'evil.example'})
    assert answer.json() == {'detail': 'Nur lokaler Zugriff erlaubt.'}


def test_remote_writes_need_the_hosts_origin_and_the_token_with_both_host_variants(studio):
    server, client, fake, token = studio
    assert client.put('/api/notify', json={'address': 'Cay'}, headers={**REMOTE, **token}).status_code == 403   # off
    enable(client, token)
    for variant in (REMOTE, REWRITTEN):
        answer = client.put('/api/notify', json={'address': 'Sir Cay'}, headers={**variant, **token})
        assert answer.status_code == 200 and answer.json()['studio'] == 'https://' + HOST, variant
        assert client.put('/api/notify', json={'address': 'Sir Cay'}, headers=variant).status_code == 403           # no token
        for origin in ('https://evil.example', 'http://' + HOST, 'https://' + HOST + '.evil.example', 'null'):
            answer = client.put('/api/notify', json={'address': 'Sir Cay'}, headers={**variant, **token, 'origin': origin})
            assert answer.status_code == 403 and answer.json()['detail'] == 'Unerlaubte Herkunft.', origin
    assert client.get('/api/bootstrap', headers=REMOTE).json()['csrf'] == server.CSRF                             # the phone gets its session
    assert client.post('/api/remote/disable', headers=token).status_code == 200
    answer = client.put('/api/notify', json={'address': 'Sir Cay'}, headers={**REWRITTEN, **token})
    assert answer.status_code == 403 and answer.json()['detail'] == 'Unerlaubte Herkunft.'


def test_a_remote_request_can_neither_switch_it_off_nor_change_it(studio):
    server, client, fake, token = studio
    enable(client, token); calls = len(fake.calls())
    variants = [REMOTE, REWRITTEN, {'host': '127.0.0.1:8787', 'x-forwarded-for': '100.101.102.103'},
                {'host': 'localhost:8787', 'tailscale-user-login': 'cay@example.com'}, {'host': '127.0.0.1:8787', 'forwarded': 'for=100.1.2.3;proto=https'}]
    for variant in variants:
        for path in ('/api/remote/disable', '/api/remote/enable'):
            answer = client.post(path, headers={**variant, **token})
            assert answer.status_code == 403 and 'nur am PC selbst' in answer.json()['detail'] and 'http://127.0.0.1:8787' in answer.json()['detail'], (path, variant)
        assert client.post('/api/system/maintenance', json={'enabled': True}, headers={**variant, **token}).status_code == 403
        assert client.get('/api/remote?quick=true', headers=variant).json()['here'] == 'remote'
    assert server.remote.host() == HOST and len(fake.calls()) == calls and fake.read()['serve']                    # nothing touched
    assert client.get('/api/remote?quick=true', headers=token).json()['here'] == 'pc'
    off = client.post('/api/remote/disable', headers={**token, 'origin': 'http://127.0.0.1:8787'})
    assert off.status_code == 200 and not off.json()['enabled'] and off.json()['note'] is None
    assert ['serve', '--https=443', 'off'] in fake.calls() and fake.read()['serve'] == {}
    assert code(client, host=HOST) == 403 and not json.loads((server.RUNTIME / 'config/unterwegs.json').read_text())['enabled']


def test_funnel_is_never_used_and_never_accepted(studio):
    server, client, fake, token = studio
    fake.set(serve={'AllowFunnel': {HOST + ':443': True}, 'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8787'}}}}})
    answer = client.post('/api/remote/enable', headers=token)
    assert answer.status_code == 409 and 'Funnel' in answer.json()['detail'] and server.remote.host() is None
    fake.set(serve={}); enable(client, token)
    assert code(client, host=HOST, **{'tailscale-funnel-request': '?1'}) == 403
    assert code(client, host='127.0.0.1:8787', **{'tailscale-funnel-request': '?1'}) == 403
    source = (ROOT / 'cay_studio_app/remote_access.py').read_text() + (ROOT / 'cay_studio_app/server.py').read_text()
    assert not re.search(r"run\(\[[^\]]*'funnel'", source) and '0.0.0.0' not in source          # never `tailscale funnel ...`
    assert "uvicorn.run(app, host='127.0.0.1'" in (ROOT / 'cay_studio_app/server.py').read_text()


@pytest.mark.parametrize('state, words', [
    ({'backend': 'NeedsLogin'}, 'nicht angemeldet'), ({'backend': 'Stopped'}, 'ausgeschaltet'),
    ({'backend': 'NeedsMachineAuth'}, 'Freigabe'), ({'backend': 'down'}, 'läuft auf dem PC gerade nicht'),
    ({'magicdns': False}, 'MagicDNS aus'),
    ({'serve_mode': 'old'}, 'zu alt'), ({'serve_mode': 'fail'}, 'Access is denied'),
    ({'serve': {'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:3000'}}}}}}, 'schon etwas anderes'),
])
def test_honest_messages_when_it_cannot_work(studio, state, words):
    server, client, fake, token = studio
    fake.set(**state)
    answer = client.post('/api/remote/enable', headers=token)
    assert answer.status_code == 409 and words in answer.json()['detail'], answer.text
    assert server.remote.host() is None and not (server.RUNTIME / 'config/unterwegs.json').exists()
    status = client.get('/api/remote').json()
    assert not status['enabled'] and status['failure']['text'] == answer.json()['detail']
    if 'backend' in state or 'magicdns' in state:
        assert any(words in c['detail'] for c in status['checks'] if not c['ready'])


def test_tailscale_missing_says_where_to_get_it(studio, monkeypatch, tmp_path):
    server, client, fake, token = studio
    monkeypatch.setenv('CAY_TAILSCALE', str(tmp_path / 'nicht_da' / 'tailscale.exe'))
    status = client.get('/api/remote').json()
    assert status['tailscale']['state'] == 'missing' and status['checks'] == [
        {'name': 'Tailscale auf dem PC', 'ready': False, 'detail': remote_access.MISSING}]
    assert 'tailscale.com/download/windows' in remote_access.MISSING and 'PC aus' in status['pc_off']
    answer = client.post('/api/remote/enable', headers=token)
    assert answer.status_code == 409 and answer.json()['detail'] == remote_access.MISSING


def test_serve_needs_a_one_time_ok_in_tailscale_the_link_is_shown(studio):
    server, client, fake, token = studio
    fake.set(serve_mode='needs_enable')
    started = time.monotonic(); answer = client.post('/api/remote/enable', headers=token)
    assert answer.status_code == 409 and answer.json()['detail'] == remote_access.NEEDS_ENABLE
    assert time.monotonic() - started < 15                                   # the waiting CLI is stopped once the link is there
    assert client.get('/api/remote').json()['failure'] == {'text': remote_access.NEEDS_ENABLE, 'link': 'https://login.tailscale.com/f/serve?node=nFAKE123'}
    fake.set(serve_mode='ok'); state = enable(client, token)
    assert state['enabled'] and state['failure'] is None


def test_status_while_on_names_what_is_wrong(studio):
    server, client, fake, token = studio
    enable(client, token)
    status = client.get('/api/remote').json()
    assert status['problem'] is None and [c['name'] for c in status['checks']] == ['Tailscale auf dem PC', 'Angemeldet', 'Adresse']
    assert all(c['ready'] for c in status['checks']) and 'Version 1.88.2' in status['checks'][0]['detail'] and '„cay-pc“' in status['checks'][1]['detail']
    fake.set(serve={}); assert client.get('/api/remote').json()['problem'] == remote_access.SERVE_OFF
    fake.set(dns='neuer-pc.tail1234.ts.net.', serve={})
    status = client.get('/api/remote').json()
    assert 'neuer-pc.tail1234.ts.net' in status['problem'] and status['host'] == HOST
    assert code(client, host='neuer-pc.tail1234.ts.net') == 403                # only the stored name, until Cay sets it up again
    fake.set(backend='down'); assert 'läuft auf dem PC gerade nicht' in client.get('/api/remote').json()['problem']


def test_switching_off_works_even_when_tailscale_does_not_cooperate(studio, monkeypatch, tmp_path):
    server, client, fake, token = studio
    enable(client, token); fake.set(off_mode='ignore')
    answer = client.post('/api/remote/disable', headers=token)
    assert answer.status_code == 200 and answer.json()['note'] == remote_access.OFF_STUCK and ['serve', 'reset'] in fake.calls()
    assert code(client, host=HOST) == 403
    fake.set(off_mode='ok', serve={}); enable(client, token)
    monkeypatch.setenv('CAY_TAILSCALE', str(tmp_path / 'weg.exe'))
    answer = client.post('/api/remote/disable', headers=token)
    assert answer.status_code == 200 and answer.json()['note'] == remote_access.OFF_UNREACHABLE and server.remote.host() is None


def test_studio_start_puts_a_lost_forwarding_back(studio):
    server, client, fake, token = studio
    enable(client, token); fake.set(serve={})
    server.remote.ensure()
    assert fake.read()['serve']['Web'][HOST + ':443']['Handlers']['/']['Proxy'] == 'http://127.0.0.1:8787'
    assert [c for c in fake.calls() if c[:2] == ['serve', '--bg']] == [['serve', '--bg', '8787']] * 2


def test_a_damaged_settings_file_never_widens_access(tmp_path):
    (tmp_path / 'config').mkdir()
    g = {'RUNTIME': tmp_path, 'PORT': 8787}
    for content in ({'enabled': True, 'host': '*.ts.net'}, {'enabled': True, 'host': 'evil.example'}, {'enabled': True, 'host': 'ts.net'},
                    {'enabled': False, 'host': HOST}, {'enabled': True}, ['x'], 'kaputt'):
        (tmp_path / 'config/unterwegs.json').write_text(content if isinstance(content, str) else json.dumps(content))
        remote = Remote(g)
        assert remote.host() is None and not remote.accepts_host(HOST) and not remote.accepts_origin('https://' + HOST), content
    (tmp_path / 'config/unterwegs.json').write_text(json.dumps({'enabled': True, 'host': HOST + '.'}))
    assert Remote(g).host() == HOST
    assert split_host('[::1]:8787') == ('[::1]', '8787') and split_host('Cay-PC.tail1234.ts.net:443') == (HOST, '443')


def test_the_studio_link_in_notifications_only_while_it_is_on(tmp_path):
    from test_notify import studio as notify_studio, connect_telegram, run
    g, n, factory, _ = notify_studio(tmp_path)
    g['remote'] = remote = Remote(g)
    connect_telegram(n); n.change(lambda d: d['ntfy'].update(topic='cay-studio-' + 'a' * 24))
    seen = []

    def answer(request):
        seen.append(request); return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})
    n.transport = httpx.MockTransport(answer)
    data = n.load(); payload = {'run_id': 'p1', 'lines': ['„Der Keks-Krieg“ ist fertig.']}
    assert n.text(data, payload)[-1] == 'Am PC öffnen: http://127.0.0.1:8787/#p=p1' and n.public()['studio'] is None
    remote.store({'enabled': True, 'host': HOST, 'since': 'x'})
    lines = n.text(data, payload)
    assert lines[-1] == f'Im Studio öffnen: https://{HOST}/#p=p1' and not any('Am PC öffnen' in x for x in lines) and n.public()['studio'] == 'https://' + HOST
    assert n.text({**data, 'link': False}, payload) == payload['lines']                                     # Cay's "Link mitsenden" still counts
    n.record(run(state='blocked', error='Tonspur zu kurz'), 'blocked')
    asyncio.run(n.send_due())
    telegram = [json.loads(r.content) for r in seen if r.url.host == 'api.telegram.org']
    ntfy = [parse_qs(urlsplit(str(r.url)).query) for r in seen if r.url.host == 'ntfy.sh']
    assert telegram and telegram[0]['text'].endswith(f'Im Studio öffnen: https://{HOST}/#p=p1')
    assert ntfy and ntfy[0]['click'] == [f'https://{HOST}/#p=p1']
    feed = n.feed(0)['events'][0]
    assert feed['link'] == f'https://{HOST}/#p=p1' and feed['body'].endswith(f'Im Studio öffnen: https://{HOST}/#p=p1')
    remote.store({'enabled': False, 'host': None, 'since': None}); seen.clear()
    n.record(run(rid='p2', state='blocked', error='Bild fehlt'), 'blocked'); asyncio.run(n.send_due())
    assert 'Am PC öffnen: http://127.0.0.1:8787/#p=p2' in json.loads(seen[0].content)['text'] and 'ts.net' not in str(seen[0].content)
    assert all('click' not in parse_qs(urlsplit(str(r.url)).query) for r in seen if r.url.host == 'ntfy.sh')
    assert all(e['link'] is None and 'ts.net' not in e['body'] for e in n.feed(0)['events'])


def test_the_address_goes_to_telegram_only_on_the_click(studio):
    server, client, fake, token = studio
    seen = []

    def answer(request):
        seen.append(request); return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})
    server.notifier.transport = httpx.MockTransport(answer)
    assert client.post('/api/remote/telegram', headers=token).status_code == 409                      # off: no address yet
    enable(client, token)
    status = client.get('/api/remote').json()
    assert not status['telegram'] and client.post('/api/remote/telegram', headers=token).status_code == 409   # Telegram not connected
    server.notifier.change(lambda d: d['telegram'].update(token=TOKEN, chat={'id': 424242, 'name': 'Cay'}, bot={'id': 1, 'name': 'Bot', 'username': 'cay_bot'}))
    assert client.get('/api/remote').json()['telegram'] and not seen                                   # connected: still nothing sent by itself
    answer = client.post('/api/remote/telegram', headers={**REMOTE, **token})                          # also from the phone
    assert answer.status_code == 200 and len(seen) == 1
    sent = json.loads(seen[0].content)
    assert sent['chat_id'] == 424242 and f'https://{HOST}' in sent['text'] and 'Lesezeichen' in sent['text'] and sent['disable_web_page_preview']
    assert TOKEN not in client.get('/api/remote').text and TOKEN not in json.dumps(server.notifier.public())
    assert re.search('Studio-Adresse gesendet', json.dumps(server.notifier.public(), ensure_ascii=False))
