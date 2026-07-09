# Hardware and legacy-stack memory

## Device identity

- Razer DeathStalker Ultimate
- USB VID `0x1532`, PID `0x0114`
- `MI_00`-`MI_02`: HID collections; never alter their drivers
- `MI_03`: vendor-specific SwitchBlade interface; the legacy product requires the
  original Razer driver here

The compatibility product must detect a WinUSB-bound MI_03 as blocked and explain
that the original Razer driver must be restored. It must not change the binding
silently or manipulate any interface itself.

## Legacy stack locations

- `%ProgramFiles(x86)%\Razer\Synapse\RzSynapse.exe`
- `%ProgramFiles(x86)%\Razer\SwitchBlade\RzAppManager.exe`
- `%ProgramData%\Razer\SwitchBlade\SDK\RzSwitchbladeSDK2.dll`
- `%ProgramData%\Razer\Synapse\Devices\DeathStalker Ultimate\Profiles`
- `%ProgramData%\Razer\Synapse\Accounts\<account>\...`

Do not assume these paths prove registrations/services are healthy. Inventory and
postcondition checks must distinguish present files from a functional stack.

## Visual acceptance targets

After repair/reboot verify:

1. `Razer Configurator` opens through `RzSynapse.exe -launch`.
2. Standard keyboard, media keys, and trackpad input work.
3. The 800x480 SwitchBlade panel displays legacy content.
4. All ten physical LCD keys display content and react correctly.
5. Keyboard brightness and SwitchBlade UI brightness apply and persist.

Use the ADB camera workflow for repeatable visual evidence. Keep evidence local
unless it has been manually inspected and sanitized.

## Clean-room and distribution boundary

Facts, GUIDs, public interface shapes, user-owned observations, and test fixtures
may be documented. Do not copy proprietary binaries or redistribute locally
exported drivers/installers. Do not copy GPL implementation code into this MIT
repository.
