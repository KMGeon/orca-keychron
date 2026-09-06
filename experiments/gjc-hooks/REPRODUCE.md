# GJC 0.16.4 native-hook experiments

This folder is an experiment, not the Keychron production bridge. Read
[`../../docs/gjc-hook-experiment-results.md`](../../docs/gjc-hook-experiment-results.md)
for conclusions, counterexamples and unverified boundaries.

## Repeat the portable basic experiment

Requires installed `gjc` 0.16.4, Python 3 and Bun. No API key or external model is
used. Keep the fixture server in one terminal:

```sh
python3 experiments/gjc-hooks/mock_provider.py --port 64329
```

In another terminal, run a fresh case name:

```sh
python3 experiments/gjc-hooks/live_driver.py --port 64329 --case check_success --scenario success
python3 experiments/gjc-hooks/live_driver.py --port 64329 --case check_error --scenario http_error
bun test experiments/gjc-hooks/observer.test.ts experiments/gjc-hooks/reducer-model.test.ts
```

Stop only this fixture server with Ctrl+C after the experiment. The driver uses
an isolated agent profile, suppresses credential auto-import and onboarding,
disables SDK for print-mode runs and passes an empty stdin. It preserves HOME.
Data is written under `/tmp/gjc-keychron-repro`; optionally set
`GJC_KEYCHRON_LAB_DIR` to another disposable directory in both terminals. Case
event logs append: use fresh case names for a new run.

The provider also has controlled question, slow response, tool and task plans.
Question interaction requires a real TUI. `--prepare-tui` writes the isolated
profile and launch arguments; `--launch /absolute/case/path` starts that case.
Use Orca terminal creation for an Orca-managed TUI, and record its new handle.

## What needs additional setup

The basic driver does **not** automatically reproduce every advanced case.
The historical experiment used separate disposable profiles for project agent
tool permissions, task isolation, managed model fallback, pause/resume and
extension UI. Their safe inputs and metadata are preserved under `evidence/`.
The original bounded runtime scripts are under `evidence/reproduction/`; they
record historical `/tmp` paths and must be adapted before reuse.

Default executor lacks some of the question/nesting tools used by the custom
agent fixtures. `isolated:false` is rejected when task isolation mode is `none`.
A direct loopback 503 is treated as local provider unavailability; the retry
experiment uses a managed fallback profile to reach session retry events.
These differences are why failed setup attempts are retained separately.

## Evidence interpretation

`events.jsonl` contains metadata emitted by a real native hook inside GJC.
`stream.jsonl` contains the TCP receiver's records. TUI snapshots record Orca's
rendered terminal text, not screenshots of the physical keyboard.
`events-before-close.jsonl` freezes the observation before test cleanup.
The observer omits prompts, answers, tool arguments/results and credentials.
The screen fixtures contain deliberately synthetic local experiment text.

The reducer tests validate a proposed policy, including a replay of captured
TUI metadata. They do not prove all GJC permission/question surfaces are
observable or answerable. The best-effort exporter has no ACK or state replay;
the deliberate loss test demonstrates that a reconnect can still miss events.
