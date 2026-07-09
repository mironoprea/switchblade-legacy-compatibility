# Handoff and verified memory

Last consolidated: 2026-07-10. Source work originated in
`mironoprea/switchblade-reborn` on branch `codex/windows-consumer-package`.

## Current implementation

`app/legacy_compat.py` currently provides:

- read-only installation/driver/process inventory;
- allowlisted configuration backup with SHA-256 manifest;
- optional local `pnputil /export-driver` of the installed MI_03 package;
- strict ZIP validation and confirmed restore with a JSONL operation journal;
- launch of `RzSynapse.exe -launch` with visible-window confirmation;
- a preliminary `repair` command that stops three processes, backs up, and launches.

The restore subsystem has strong path-traversal, undeclared-member, extension,
checksum, confirmation, process-state, and privacy safeguards. Its tests are
mocked and do not constitute a live restore.

## Known release blockers

1. `repair` does not repair registrations or missing components.
2. `repair` force-stops processes before checking whether the stack is ready or
   repairable and does not restart them after failure.
3. Multiple account directories are neutralized to the same archive root; duplicate
   relative names may be silently dropped by the backup `seen` set.
4. A multi-file restore can leave earlier files replaced if a later replacement
   fails. A pre-restore backup exists, but recovery is not automatic.
5. Backup/report timestamps have one-second precision and may overwrite artifacts.
6. Core tests do not exercise scan, backup creation, driver export, launch-window
   detection, process stopping, or the end-to-end repair path.
7. There is no Windows installer or consumer error UI.

These issues are ordered in `BUILD_PLAN.md`.

## Verified hardware and installation facts

- Device: Razer DeathStalker Ultimate, USB VID `0x1532`, PID `0x0114`.
- Interface `MI_03` is vendor-specific and uses the original Razer driver for the
  legacy product. Interfaces `MI_00`, `MI_01`, and `MI_02` are HID and must never
  be rebound or modified.
- Typical legacy root: `C:\Program Files (x86)\Razer`.
- Synapse launcher: `Razer\Synapse\RzSynapse.exe -launch`.
- App manager: `Razer\SwitchBlade\RzAppManager.exe`.
- SDK DLL: `C:\ProgramData\Razer\SwitchBlade\SDK\RzSwitchbladeSDK2.dll`.
- Expected configurator window title: `Razer Configurator`.
- Legacy processes in current scope: `RzSynapse`, `RzAppManager`, `RzSBHelper`.
- The legacy device DLL is 32-bit; probes must compile/run x86.

## Brightness finding

The installed Razer COM device API exposes two confirmed channels:

| Channel | Synapse label | Physical result |
|---|---|---|
| 1 | Keyboard brightness | Normal keyboard backlight |
| 2 | SwitchBlade UI brightness | Ten adaptive-key LCD backlights |

The main 800x480 panel was not observed to have a third Synapse brightness slider.
`tools/legacy_brightness_probe.py` contains the discovered COM interface GUIDs and
can query or set values for owned-hardware testing. Setting requires explicit
arguments and must be visually verified.

## Visual verification memory

An Android Motorola phone was successfully used over ADB as a fixed camera aimed
at the keyboard. `tools/adb_photo.py` wakes the phone, dismisses the keyguard,
opens the camera, triggers `KEYCODE_CAMERA`, selects the newest non-thumbnail file,
and pulls it locally. The setup is documented in `docs/ADB_VISION_SETUP.md`.

No prior screenshots or photos are carried into this repository because some
contained personal account or conversation content. Generate fresh local evidence,
inspect it, and commit only deliberately sanitized reference material.

## Last known test result

In the source workspace, `python -m pytest tests/test_legacy_compat.py -q` passed
28 tests on Python 3.13. This split repository must establish its own CI baseline.
