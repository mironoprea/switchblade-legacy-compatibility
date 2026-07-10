# Release acceptance checklist

This build is unofficial and unsigned. Do not call it consumer-ready or publish a
release until every item is green.

## Automated gates

- [ ] Platform-neutral unit tests pass on Linux and Windows.
- [ ] Windows package CI builds the owned application and installer.
- [ ] Package smoke check confirms the compiled owned executable exists.
- [ ] Install in a clean Windows VM, launch the UI, upgrade it, reboot, rerun it,
  and uninstall it.
- [ ] Confirm uninstall removes only utility-installed files and shortcuts while
  preserving all Razer files and the utility's per-user backups, reports,
  journals, and logs.

## User-assisted hardware gates

Perform each action only with the user physically present and after explicit
confirmation. Do not bind or alter any driver interface. Keep visual evidence
local and inspect it for personal information before publication.

- [ ] After reboot, launch `RzSynapse.exe -launch` and observe `Razer Configurator`.
- [ ] Confirm keyboard, media keys, and trackpad input.
- [ ] Confirm the main 800x480 SwitchBlade panel and all ten LCD keys.
- [ ] Confirm keyboard brightness and SwitchBlade UI brightness apply and persist
  after reboot.
- [ ] Confirm backup, proposed repair/repair rerun, validated restore, and
  recovery guidance behave as documented.

## Current acceptance state

Manual hardware and clean-VM acceptance are pending user-assisted execution.
This is a release and merge blocker for issue #4; mocks and CI do not substitute
for these checks.
