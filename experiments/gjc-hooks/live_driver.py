"""Controlled installed-GJC hook experiments. Real GJC, synthetic loopback model."""
import argparse
import json
import os
import shutil
import socketserver
import subprocess
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('GJC_KEYCHRON_LAB_DIR', '/tmp/gjc-keychron-repro'))
HOOK = BASE / 'observer.ts'
GJC = shutil.which('gjc')

def prepare(name, port, scenario=None, runtime=True, hook_name='*', tools='read,bash,ask,task', sdk=True):
    case = ROOT / 'cases' / name
    workspace = case / 'workspace'
    agent = case / 'agent'
    for p in [workspace / '.gjc/hooks/pre', agent, case / 'sessions']:
        p.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOOK, workspace / '.gjc/hooks/pre' / (hook_name + '.ts'))
    (workspace / 'fixture.txt').write_text('KEYCHRON_FIXTURE_OK\n')
    (workspace / 'AGENTS.md').write_text('This is an isolated hook experiment. Use only the configured local fixture model.\n')
    model = 'lab-' + (scenario or name)
    config = json.loads((ROOT / 'provider/agent/models.yml').read_text())
    config['providers']['keychron-lab']['baseUrl'] = f'http://127.0.0.1:{port}/v1'
    (agent / 'models.yml').write_text(json.dumps(config))
    (agent / 'credential-auto-import-state.json').write_text(json.dumps({'lastImportVersion':'0.16.4','initialImportResolution':'declined'}))
    (agent / 'config.yml').write_text(json.dumps({'retry': {'enabled': False, 'maxRetries': 0}, 'notifications': {'enabled': False}, 'telemetry': {'enabled': False}, 'marketplace': {'autoUpdate': False}}))
    env = {k: os.environ[k] for k in ['HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'TERM', 'SHELL'] if k in os.environ}
    for k in ['ORCA_TERMINAL_HANDLE', 'ORCA_PANE_KEY', 'ORCA_TAB_ID', 'ORCA_WORKTREE_ID']:
        if k in os.environ:
            env[k] = os.environ[k]
    env.update({'GJC_CODING_AGENT_DIR': str(agent), 'GJC_AGENT_DIR': str(agent), 'GJC_AUTOMATION':'1', 'GJC_DISABLE_TELEMETRY': '1', 'GJC_MODEL_PRESET_REGISTRY_DISABLED': '1', 'GJC_UI_LANGUAGE': 'en', 'GJC_KEYCHRON_EVENT_LOG': str(case / 'events.jsonl'), 'GJC_KEYCHRON_RUNTIME_EVENTS': '1' if runtime else '0', 'GJC_NO_PTY': '1'})
    if not sdk:
        env['GJC_SDK_DISABLE'] = '1'
    cmd = [GJC, '--model', f'keychron-lab/{model}', '--no-title', '--no-lsp', '--no-mcp', '--no-rules', '--no-pty', '--thinking', 'off', '--session-dir', str(case / 'sessions'), '--tools', tools]
    (case / 'environment.json').write_text(json.dumps(env, indent=2))
    (case / 'command.json').write_text(json.dumps(cmd))
    return case, workspace, env, cmd

def events_at(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows

def run_case(name, port, scenario=None, runtime=True, hook_name='*', timeout=35, tools='read,bash,ask,task'):
    case, cwd, env, cmd = prepare(name, port, scenario, runtime, hook_name, tools, sdk=False)
    received = []
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                try:
                    received.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env['GJC_KEYCHRON_PORT'] = str(server.server_address[1])
    cmd += ['--print', '--mode', 'json', f'[GJC_CASE:{scenario or name}]']
    (case / 'command.json').write_text(json.dumps(cmd))
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=cwd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        code, stdout, stderr = None, exc.stdout or b'', exc.stderr or b''
    duration = round(time.monotonic()-start, 3)
    (case / 'stdout.log').write_bytes(stdout)
    (case / 'stderr.log').write_bytes(stderr)
    server.shutdown()
    server.server_close()
    (case / 'stream.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in received))
    events = events_at(case / 'events.jsonl')
    result = {'case': name, 'scenario': scenario or name, 'returncode': code, 'timedOut': timed_out, 'seconds': duration, 'hookEvents': len(events), 'streamEvents': len(received), 'types': [r['type'] for r in events], 'sessionIds': sorted({r.get('sessionId','') for r in events}), 'terminal': [r for r in events if r['type'] == 'agent_end'], 'stderrTail': stderr.decode(errors='replace')[-1800:]}
    (case / 'result.json').write_text(json.dumps(result, indent=2))
    return result

def launch(case):
    case = Path(case)
    env = json.loads((case/'environment.json').read_text())
    # Fresh Orca terminal identity belongs to this launch, not the parent agent.
    for k in ['ORCA_TERMINAL_HANDLE', 'ORCA_PANE_KEY', 'ORCA_TAB_ID', 'ORCA_WORKTREE_ID']:
        if k in os.environ:
            env[k] = os.environ[k]
    (case/'terminal-identity.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('ORCA_')}))
    cmd = json.loads((case/'command.json').read_text())
    os.chdir(case/'workspace')
    os.execve(cmd[0], cmd, env)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int)
    parser.add_argument('--case')
    parser.add_argument('--scenario')
    parser.add_argument('--documented-only', action='store_true')
    parser.add_argument('--hook-name', default='*')
    parser.add_argument('--prepare-tui', action='store_true')
    parser.add_argument('--launch')
    args = parser.parse_args()
    if args.launch:
        launch(args.launch)
    elif args.prepare_tui:
        case, *_ = prepare(args.case,args.port,args.scenario,not args.documented_only,args.hook_name)
        print(case)
    else:
        print(json.dumps(run_case(args.case,args.port,args.scenario,not args.documented_only,args.hook_name),ensure_ascii=False))
