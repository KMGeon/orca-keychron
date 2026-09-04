<div align="center">

# Orca Keychron

### 10x your Orca agents—without watching every terminal.

Turn your Keychron keyboard into a live command center for every Orca worktree.

![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-000000?logo=apple&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)

**English** · [한국어](https://github.com/KMGeon/orca-keychron/blob/main/README.ko.md)

</div>

![Orca agent status rendered on a Keychron keyboard](https://raw.githubusercontent.com/KMGeon/orca-keychron/main/assets/img1.png)

`orca-keychron` maps each Orca worktree to a stable key and renders its agent state with
per-key RGB. See which agents are working, waiting, blocked, or done—and press one shortcut
to jump directly to the worktree that needs you.

Any coding agent reported by Orca works automatically, including Codex, Claude Code, Grok,
local sessions, and agents running on paired hosts. No agent-specific hooks are installed.

> [!IMPORTANT]
> This project requires a Keychron keyboard whose firmware implements the per-key `KC_RGB`
> command `0xA8`. It has been verified on the **Keychron Q65 Max**. Other models are detected
> and tested by the setup command before any persistent service is installed.

<p align="center">
  <img src="https://raw.githubusercontent.com/KMGeon/orca-keychron/main/assets/img2.png" alt="Orca worktree status lights on a Keychron Q65 Max" width="720">
</p>

## What it does

- Assigns one stable indicator key to each active Orca worktree.
- Aggregates multiple agents in the same worktree into one action-oriented state.
- Opens a worktree's current action target with `Option` plus its indicator key.
- Includes agents from local and paired Orca hosts by default.
- Uses the stock Keychron firmware and writes RGB frames to RAM only.

## Status colors

| Orca worktree state | Indicator | What it means |
|---|---|---|
| **Working** | 🟡 Yellow | Agent activity is in progress |
| **Waiting** | 🟠 Orange | An answer or approval is required |
| **Blocked** | 🔴 Red | The current turn failed or needs recovery |
| **Done** | 🟢 Green | The worktree is ready for its next task |
| **Mixed** | 🟣 Magenta | Multiple action states need attention |
| **Idle** | ⚪ White | The tracked worktree is available |

`working` is background activity and does not create a mixed state by itself. Historical
`done` rows are ignored until the same pane has first been observed live, preventing stale
sessions from filling the indicator zone.

## Quick start

### Requirements

- macOS with Python 3.9 or newer
- [uv](https://docs.astral.sh/uv/) installed
- Orca running with the `orca` CLI available on `PATH`
- A compatible Keychron keyboard connected over USB

Most Keychron keyboards do not expose the required raw HID interface over Bluetooth.

### Install

```bash
uv tool install orca-keychron
orca-keychron setup
```

The interactive setup:

1. Verifies the Orca connection.
2. Detects the keyboard and verifies `KC_RGB` support.
3. Previews the default indicator zone, then restores the previous lighting.
4. Saves the keyboard configuration and requests the required macOS permissions.
5. Installs and starts a per-user login service.

After setup, the indicator starts automatically at login. The default zone is the number
row: `1 2 3 4 5 6 7 8 9 0 - =`.

### Verify

```bash
orca-keychron status
orca-keychron autostart status
```

`status` reads Orca without touching keyboard lighting. A healthy background installation
reports `Login autostart installed and loaded`.

### One-off use

Run without keeping the package installed or registering automatic startup:

```bash
uvx orca-keychron setup --no-autostart
uvx orca-keychron run
```

### Upgrade or uninstall

```bash
# Upgrade
uv tool upgrade orca-keychron

# Uninstall the service and command
orca-keychron autostart uninstall
uv tool uninstall orca-keychron
```

The saved configuration and logs remain under
`~/Library/Application Support/orca-keychron/` so an uninstall does not unexpectedly
delete user data. Remove that directory separately only if you no longer need it.

## Keyboard navigation

Press `Option` plus a lit indicator key while Orca is frontmost to open that worktree's
current action target. When several agents in the same worktree need attention, repeated
presses cycle through them in this order:

```text
blocked → waiting → done
```

Plain number keys and `Control`, `Command`, or mixed-modifier shortcuts are never
intercepted. Option-number shortcuts in other frontmost applications pass through
normally. Pressing an unassigned indicator key while Orca is frontmost does nothing.

## How it works

```text
Orca-managed agents
        │ normalized lifecycle state
        ▼
orca worktree ps --json
        │ poll every 0.75 seconds
        ▼
stable worktree slot tracker
        │ aggregate agents per worktree
        ▼
indicator renderer + action-target tracker
        │ KC_RGB raw HID, RAM only
        ▼
Keychron per-key RGB
```

Orca already normalizes agent activity as `working`, `waiting`, `blocked`, and `done`.
This project consumes that public status surface instead of adding another set of Codex,
Claude Code, or Grok lifecycle hooks.

A single long-running process polls Orca, owns the keyboard HID handle, updates RGB only
when the rendered state changes, and checks the selected lighting effect every 10 seconds.

## Configuration

Setup saves configuration to:

```text
~/Library/Application Support/orca-keychron/config.json
```

Choose a different indicator zone during setup:

```bash
orca-keychron setup --leds 1,2,3,4,5,6,7,8,9,10
```

LED indices are firmware positions, not printed key labels, and can vary by keyboard.
Setup previews the selected indices before saving them.

Common runtime options:

| Option | Purpose |
|---|---|
| `--open-hold 0.3` | Require a short hold before opening a worktree |
| `--poll-interval 0.75` | Change the Orca status polling interval |
| `--leds 1,2,3` | Override the saved indicator LED indices |
| `--host local` | Include only one host; repeat to include several hosts |
| `--orca-command orca-dev` | Use a different Orca CLI command |

Run `orca-keychron <command> --help` for the complete command reference.

## macOS permissions

Keyboard navigation requires both **Accessibility** and **Input Monitoring** permission.
Allow the installed Python process or the terminal that runs the indicator under:

```text
System Settings → Privacy & Security → Accessibility
System Settings → Privacy & Security → Input Monitoring
```

Then restart the background service:

```bash
orca-keychron autostart install
```

Unsigned Python tools do not have a stable macOS permission identity. If macOS continues
to report that permission is required, remove the stale entry, add the currently installed
Python process or terminal again, and reinstall the service. Packaging this project as a
signed macOS application would be required to remove that platform limitation entirely.

## Protocol and safety

- Discovers Keychron VID `0x3434`, usage page `0xFF60`, and usage `0x61`.
- Uses VIA channel 3 and per-key effect `23`.
- Sends full RGB frames to keyboard RAM; it never sends `SaveLedConf`.
- Keeps LEDs outside the indicator zone off while the indicator is active.
- Restores the previous effect and brightness when the process stops normally.

Custom RAM-only frame contents from an existing per-key or mixed effect cannot be read
back from the supported protocol. If you were using one before starting the indicator,
reapply that lighting profile after stopping it.

The project does not collect telemetry or send agent state to its own network service. It
invokes the configured Orca CLI and writes only its local configuration and service logs.

Keychron Launcher uses the same raw HID channel. Close long-running Launcher lighting
animations if either application becomes unresponsive or overwrites the other's colors.

## Troubleshooting

### No lights appear

```bash
orca-keychron status
orca-keychron autostart status
orca-keychron run
```

Running in the foreground prints the failure immediately. Background logs are stored at:

```text
~/Library/Application Support/orca-keychron/logs/stdout.log
~/Library/Application Support/orca-keychron/logs/stderr.log
```

### No Keychron raw HID interface found

Connect the keyboard directly over USB instead of Bluetooth. Close Keychron Launcher and
retry. Some docks and KVMs do not forward the required HID interface reliably.

### Firmware does not enable `KC_RGB`

The connected firmware cannot address individual LEDs through command `0xA8`. Standard
VIA lighting support is not enough. This tool deliberately does not fall back to a
whole-keyboard effect because that would remove the per-worktree display.

### Option-key navigation does not work

Confirm that the indicator's Python process or terminal has Accessibility and Input
Monitoring permission, then restart it with:

```bash
orca-keychron autostart install
```

### Lighting resets or becomes unresponsive

Close Keychron Launcher animations, reconnect the keyboard over USB, and restart the
indicator. Only one process should control the raw HID lighting channel at a time.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

Project structure:

```text
src/orca_keychron/   CLI, Orca integration, navigation, tracking, and HID rendering
tests/               Unit and behavior tests
assets/img1.png      Architecture and interaction overview used in this README
assets/img2.png      Keychron Q65 Max hardware photo used in this README
```

## Contributing

Bug reports, compatibility results, documentation improvements, and focused pull requests
are welcome. Fork and clone the repository, create a focused branch, and use the development
commands above. For hardware reports, include the Keychron model, connection type, macOS
version, and the output of this read-only probe:

```bash
orca-keychron probe
```

Before opening a pull request, run:

```bash
.venv/bin/pytest
.venv/bin/ruff check .
```

Do not include personal Orca state, local paths, or configuration files in issues.

## License

Released under the [MIT License](https://github.com/KMGeon/orca-keychron/blob/main/LICENSE).
