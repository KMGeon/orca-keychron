"""Run semantic mutants only in owned temporary copies; compatible with Python 3.9."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'src/orca_keychron_gjc/assets/gjc_hook.ts').read_text()
tests = (root / 'tests/gjc_hook_faults.test.ts').read_text()
mutations = [
    ('orange-priority', 'if (pendingAsks || pendingDecisions) state = "waiting";',
     'if (pendingAsks || pendingDecisions) state = "unknown";', 'H-PRIORITY'),
    ('deep-pending-retention', 'case "session_shutdown":\n        session.active = false;',
     'case "session_shutdown":\n        session.decisions.clear();\n        session.active = false;', 'H-PENDING'),
]
for name, old, new, selector in mutations:
    assert source.count(old) == 1, name
    with tempfile.TemporaryDirectory(prefix='gjc-hook-mutation-') as temporary:
        directory = Path(temporary)
        module = directory / 'hook.ts'
        module.write_text(source.replace(old, new))
        target = directory / 'faults.test.ts'
        target.write_text(tests.replace('../src/orca_keychron_gjc/assets/gjc_hook', str(module)))
        result = subprocess.run(['bun', 'test', str(target), '--test-name-pattern', selector],
                                capture_output=True, text=True, timeout=20, check=False)
        print('MUTANT:', name, 'EXIT:', result.returncode)
        print(result.stdout + result.stderr)
        assert result.returncode != 0 and '(fail)' in result.stderr, 'mutant survived: ' + name
print('Both semantic mutants killed; shared source was never altered.')
