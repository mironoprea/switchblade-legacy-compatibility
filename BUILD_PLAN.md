# Build and release plan

Work in order. Do not package a release while an earlier gate is open.

## Phase 1 — harden the existing backup and restore core

- Refuse or explicitly handle multiple Synapse account directories during backup;
  never merge them into one neutral archive path and silently drop duplicates.
- Make backup, report, and journal names collision-resistant and create them
  without overwriting existing artifacts.
- Decide and implement operation-level rollback for partial multi-file restores,
  or make the recovery workflow explicit and automatically actionable.
- Bound archive file count, per-file size, total expanded size, and compression
  ratio before reading data into memory or staging it.
- Reject Windows case-insensitive destination collisions and unsafe reparse-point
  destinations.
- Add tests for backup creation, multiple accounts, artifact-name collision,
  partial restore recovery, archive resource limits, and Windows path semantics.

Gate: restore tests plus adversarial archive tests pass; a failed restore cannot
leave the user without a clear, tested recovery action.

## Phase 2 — make inventory reliable

- Replace brittle exact provider-name matching with verified driver identity.
- Inventory installed/cached official packages, relevant COM registrations,
  services, SDK DLL, SwitchBlade framework, device profile, and process state.
- Separate `healthy`, `repairable`, `blocked`, and `unsupported` results.
- Write a privacy-reviewed diagnostic report for every scan/repair run.
- Add mocked Windows-boundary tests plus fixtures based on sanitized real output.

Gate: scan accurately classifies known healthy, incomplete, WinUSB-bound, missing,
and ambiguous installations without making changes.

## Phase 3 — implement bounded repair

- Define an allowlist of repair actions and their preconditions.
- Use only locally installed or locally cached official packages.
- Show the exact proposed actions and require confirmation before mutations.
- Back up first; journal every action; verify postconditions; roll back or provide
  one-command recovery on failure.
- Do not force-stop processes before readiness/repairability is established.
- Ensure a failed backup or driver export does not strand the legacy processes.
- Launch with `RzSynapse.exe -launch` and verify the exact configurator window.

Gate: repair is idempotent and passes success/failure tests on a disposable Windows
environment. No HID interface or driver-binding operation exists in the repair path.

## Phase 4 — consumer UX and packaging

- Provide a small Windows UI for scan, proposed repair, backup, restore, report,
  and launch. Avoid exposing Python tracebacks to users.
- Package a pinned runtime and all owned assets; do not compile helper executables
  unexpectedly at runtime.
- Add version information, Start Menu shortcuts, uninstall, upgrade behavior,
  logs, and unsigned-build messaging.
- Add CI artifact construction and an installed-artifact smoke test.

Gate: clean-VM install, upgrade, reboot, rerun, and uninstall succeed.

## Phase 5 — hardware acceptance

Use `docs/ADB_VISION_SETUP.md` for photo evidence when visual confirmation is
needed. Record only sanitized conclusions in the repository.

- Confirm configurator opens after reboot.
- Confirm keyboard/media/trackpad functionality.
- Confirm main display and ten dynamic keys visually.
- Confirm both brightness channels apply and persist.
- Confirm backup/repair/restore/rerun and uninstall behavior.

Only after all gates pass may a build be called consumer-ready.
