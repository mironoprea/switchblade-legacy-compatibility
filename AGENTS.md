# Agent instructions

This repository has one product: **Switchblade Legacy Compatibility**. Do not add
the independent Switchblade Reborn application or its direct-USB renderer.

## Required reading order

Before implementation, read completely:

1. `README.md`
2. `PRODUCT_PLAN.md`
3. `HANDOFF.md`
4. `BUILD_PLAN.md`
5. `docs/RESTORE_SAFETY_SPEC.md`
6. The source and tests relevant to the requested task

For hardware or visual work, also read `docs/HARDWARE_MEMORY.md`,
`docs/BRIGHTNESS_MEMORY.md`, `docs/ADB_VISION_SETUP.md`, and `tools/README.md`.

## Non-negotiable safety rules

1. Never change a device driver without an explicit user request, a precise
   explanation, confirmation, and a tested rollback plan.
2. Never modify DeathStalker Ultimate HID interfaces `MI_00`, `MI_01`, or `MI_02`.
   The legacy stack uses the original Razer driver on vendor interface `MI_03`.
3. Never download, commit, package, or redistribute Razer binaries, drivers,
   installers, account data, or credentials.
4. Repairs may use only the user's locally installed or locally cached official
   packages, after inventory and backup.
5. Preserve the restore allowlist. Do not restore destinations supplied by an
   archive. Do not include `RazerLoginData.xml`, logs, analytics, executables,
   DLLs, drivers, or arbitrary extensions.
6. Hardware actions require the user at the Windows machine. Prepare commands and
   explain effects before any process stop, configuration write, or driver action.
7. Do not commit generated executables, camera photos, packet captures, diagnostic
   reports, backups, or user-specific paths. Inspect every proposed reference image
   for personal information before publication.
8. Do not claim live hardware acceptance from mocked tests.

## Definition of a consumer-ready change

- Unit tests pass on Windows and Linux where applicable.
- Windows integration behavior is tested on a disposable or backed-up machine.
- Failure paths leave a usable recovery route and produce a non-sensitive report.
- Packaging is tested by install, upgrade, repair rerun, reboot, and uninstall.
- Uninstall does not remove Razer software, profiles, backups, or user data.
- The unsigned-build warning is documented until publisher signing is available.

## Repository scope

Allowed product code: `app/legacy_compat.py` and future narrowly related modules.
Allowed tools are those already documented in `tools/README.md` or tools needed to
inventory/verify the legacy stack. Prefer adding focused modules and tests over
mixing more behavior into one file.
