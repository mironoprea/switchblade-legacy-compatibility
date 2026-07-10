# Switchblade Legacy Compatibility

An unofficial, local-only Windows compatibility and recovery utility for an
existing, legitimately installed Razer Synapse 2 / SwitchBlade stack used by the
Razer DeathStalker Ultimate (`VID_1532`, `PID_0114`).

This repository is intentionally separate from Switchblade Reborn. It contains
only the legacy utility, its safety tests, focused implementation memory, and
diagnostic tools needed to finish and verify the Windows consumer package.

It does not contain or redistribute Razer executables, DLLs, drivers, installers,
account data, or credentials. It is not affiliated with or endorsed by Razer.

## Current state

The archive validation and restore subsystem is implemented and covered by tests.
The complete consumer repair product is not finished. In particular, the current
`repair` command inventories, backs up, and launches the installed configurator;
it does not yet repair missing registrations or components.

Read these files before changing code:

1. [`AGENTS.md`](AGENTS.md) — non-negotiable scope and safety rules.
2. [`PRODUCT_PLAN.md`](PRODUCT_PLAN.md) — product contract and acceptance gate.
3. [`HANDOFF.md`](HANDOFF.md) — verified machine and hardware memory.
4. [`BUILD_PLAN.md`](BUILD_PLAN.md) — ordered implementation and release gates.
5. [`docs/RESTORE_SAFETY_SPEC.md`](docs/RESTORE_SAFETY_SPEC.md) — restore contract.
6. [`docs/ADB_VISION_SETUP.md`](docs/ADB_VISION_SETUP.md) — phone-camera verification.
7. [`docs/BRIGHTNESS_MEMORY.md`](docs/BRIGHTNESS_MEMORY.md) — confirmed legacy COM API facts.

## Developer setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,hardware]"
python -m pytest -q
```

The core utility uses only the Python standard library. Optional hardware tools
use Pillow, psutil, and Frida.

## Commands

```powershell
switchblade-legacy scan
switchblade-legacy backup
switchblade-legacy backup --no-driver
switchblade-legacy launch
switchblade-legacy restore path\to\legacy-config.zip --confirm
switchblade-legacy repair
switchblade-legacy-ui
```

`scan` is read-only. `backup` writes only under
`%LOCALAPPDATA%\SwitchbladeLegacyCompatibility` and may export the locally
installed MI_03 driver with `pnputil`. `restore` writes allowlisted configuration
files under `%PROGRAMDATA%\Razer` only after validation and explicit confirmation.
`repair` force-stops three legacy Razer processes in the current implementation;
do not present it as consumer-safe until the gates in `BUILD_PLAN.md` pass.

The desktop UI is an unofficial, unsigned convenience layer. It keeps operations
off the UI thread, shows bounded repair proposals before confirmation, and stores
rotating privacy-safe logs under the utility's per-user data root. The Windows
installer contains only this utility; uninstall preserves Razer software and all
per-user backups, reports, journals, and logs. See
[`docs/RELEASE_ACCEPTANCE.md`](docs/RELEASE_ACCEPTANCE.md) before any release.

## Safety boundary

- Never modify HID interfaces `MI_00`, `MI_01`, or `MI_02`.
- The legacy product expects the original Razer driver on vendor interface `MI_03`.
- Never bundle proprietary Razer files.
- Never back up or restore `RazerLoginData.xml`, logs, analytics, executables,
  DLLs, drivers, or arbitrary extensions.
- Do not publish captures until they have been inspected for usernames, email
  addresses, account identifiers, conversations, and other personal data.

## Hardware tools

- `tools/adb_photo.py`: take and pull a keyboard photo using an Android phone.
- `tools/legacy_brightness_probe.py`: query/set the installed 32-bit Razer
  brightness COM API for owned-hardware validation.
- `tools/sdk_exerciser.py`: exercise the installed SwitchBlade SDK using generated
  images.
- `tools/trace_rzappmanager.py`: optional Frida trace of legacy process I/O.

See [`tools/README.md`](tools/README.md) for prerequisites and safe usage.

## Origin

Split from [mironoprea/switchblade-reborn](https://github.com/mironoprea/switchblade-reborn)
as a clean-history, narrowly scoped repository. The MIT license applies to this
repository's original code; no proprietary Razer code or binaries are included.
