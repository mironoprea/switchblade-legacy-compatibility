# Diagnostic tools

These tools operate only on the user's locally installed legacy stack and owned
hardware. Generated files belong under `captures/` and are ignored by Git.

## ADB photo

`adb_photo.py` requires Android SDK Platform-Tools. See
`docs/ADB_VISION_SETUP.md`.

## Legacy brightness probe

`legacy_brightness_probe.py` compiles a temporary x86 .NET executable because the
registered Razer device DLL is 32-bit.

Read-only query:

```powershell
python tools\legacy_brightness_probe.py
```

Setting brightness mutates hardware state and requires explicit device/display and
percentage arguments:

```powershell
python tools\legacy_brightness_probe.py --device-index 0 --display-index 1 --percent 50
```

Known display channels are documented in `HANDOFF.md`. Query first; do not assume
the enumerated device index.

## SDK exerciser

Requires the user's installed `RzSwitchbladeSDK2.dll`, 32-bit .NET Framework C#
compiler, and Pillow:

```powershell
python tools\sdk_exerciser.py --all-keys --hold-seconds 20
```

It generates test images and a temporary x86 helper under `captures/sdk-exerciser`.
It does not ship Razer files.

## RzAppManager trace

Requires `frida` and `psutil` and attaches to an existing local legacy process:

```powershell
python tools\trace_rzappmanager.py --process RzAppManager.exe --duration 30
```

Trace output may contain local paths or identifiers. Keep it out of Git until
manually reviewed and sanitized.
