# Product plan

## Purpose

Keep an existing, licensed Razer Synapse 2 / SwitchBlade installation working on
modern Windows for owners of the Razer DeathStalker Ultimate.

## Product contract

The Windows package will:

1. Detect `VID_1532&PID_0114` and verify the original Razer driver is attached to
   vendor interface `MI_03`. It must never alter HID interfaces `MI_00`-`MI_02`.
2. Inventory Synapse, SwitchBlade Framework, SDK, device profiles, registrations,
   relevant services/processes, and locally cached official installers before
   proposing a change.
3. Back up relevant configuration and driver identity before repair or restore.
4. Repair missing registrations or components using only the user's locally
   installed or locally cached official Razer packages.
5. Launch `RzSynapse.exe -launch`, confirm that the `Razer Configurator` window
   appears, and provide clear diagnostics and rollback.
6. Remain opt-in and mutually exclusive with software that binds WinUSB to MI_03.

The package will not contain or redistribute proprietary Razer files.

## Acceptance gate

- The original Razer Configurator opens reliably after reboot.
- Keyboard input, media keys, trackpad, main SwitchBlade display, and all ten
  dynamic LCD keys function.
- Keyboard and SwitchBlade UI brightness changes apply and persist.
- Repair is idempotent, creates a non-sensitive diagnostic report, and can restore
  the backed-up configuration.
- Failure at every mutation boundary has a tested recovery path.
- Uninstall removes only this utility and its shortcuts/registration; it does not
  remove Razer software, profiles, backups, or user data.

Final artifact: `Switchblade Legacy Compatibility Setup.exe`.

## Packaging gate

The installer must include version metadata, Start Menu entries, clean uninstall,
per-user writable data, rotating logs, single-instance handling, diagnostics, and
documented unsigned-build warnings. Code signing is blocked until the publisher
supplies a certificate.
