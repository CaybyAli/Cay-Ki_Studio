"""A fake tailscale.exe for tests: a small script that answers like the Windows CLI.

Its state lives in state.json next to it (tests change it between calls), every call is logged there.
  backend     'Running' | 'NeedsLogin' | 'Stopped' | 'NeedsMachineAuth' | 'down' (service not running)
  dns         Self.DNSName with the trailing dot, e.g. 'cay-pc.tail1234.ts.net.'
  serve       the serve config ('serve status --json'); 'serve --bg' and 'off' change it
  serve_mode  'ok' | 'needs_enable' (prints the admin link and waits) | 'old' (no --bg flag) | 'fail'
  off_mode    'ok' | 'ignore' (exits 0 but keeps the config)
"""
import json
import sys
from pathlib import Path

SCRIPT = r'''
import json, sys, time
from pathlib import Path
STATE = Path(__file__).with_name('state.json')
state = json.loads(STATE.read_text())
args = sys.argv[1:]
state.setdefault('calls', []).append(args)
def save(): STATE.write_text(json.dumps(state))
save()
def site(): return state['dns'].rstrip('.') + ':443'
if args[:1] == ['version']:
    print(state.get('version', '1.88.2')); sys.exit(0)
if state.get('backend') == 'down':
    print('failed to connect to local Tailscale service; is Tailscale running?', file=sys.stderr); sys.exit(1)
if args == ['status', '--json']:
    print(json.dumps({'Version': state.get('version', '1.88.2') + '-t1234', 'BackendState': state.get('backend', 'Running'),
                      'Self': {'DNSName': state['dns'] if state.get('backend', 'Running') == 'Running' else '', 'HostName': 'CAY-PC', 'Online': state.get('online', True)},
                      'CurrentTailnet': {'Name': 'cay@example.com', 'MagicDNSSuffix': 'tail1234.ts.net', 'MagicDNSEnabled': state.get('magicdns', True)}}))
    sys.exit(0)
if args == ['serve', 'status', '--json']:
    print(json.dumps(state.get('serve') or {})); sys.exit(0)
if args[:2] == ['serve', '--bg']:
    mode = state.get('serve_mode', 'ok')
    if mode == 'old':
        print('flag provided but not defined: -bg', file=sys.stderr); sys.exit(1)
    if mode == 'needs_enable':
        print('Serve is not enabled on your tailnet.\nTo enable, visit:\n\n         https://login.tailscale.com/f/serve?node=nFAKE123\n', flush=True)
        time.sleep(30); sys.exit(1)
    if mode == 'fail':
        print('error: Access is denied.', file=sys.stderr); sys.exit(1)
    state['serve'] = {'TCP': {'443': {'HTTPS': True}}, 'Web': {site(): {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:' + args[2]}}}}}
    save()
    print('Available within your tailnet:\n\nhttps://' + state['dns'].rstrip('.') + '/\n|-- / proxy http://127.0.0.1:' + args[2] +
          '\n\nServe started and running in the background.\nTo disable the proxy, run: tailscale serve --https=443 off')
    sys.exit(0)
if args == ['serve', '--https=443', 'off'] or args == ['serve', 'reset']:
    if state.get('off_mode', 'ok') == 'ok': state['serve'] = {}
    save(); sys.exit(0)
print('unknown command: ' + ' '.join(args), file=sys.stderr); sys.exit(2)
'''


class FakeTailscale:
    def __init__(self, folder, **state):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.exe = self.folder / 'tailscale.exe'
        self.exe.write_text('#!' + sys.executable + '\n' + SCRIPT); self.exe.chmod(0o755)
        self.write({'backend': 'Running', 'dns': 'cay-pc.tail1234.ts.net.', 'serve': {}, 'serve_mode': 'ok', 'calls': [], **state})

    @property
    def state_file(self): return self.folder / 'state.json'

    def read(self): return json.loads(self.state_file.read_text())

    def write(self, state): self.state_file.write_text(json.dumps(state))

    def set(self, **changes): self.write({**self.read(), **changes})

    def calls(self): return self.read()['calls']
