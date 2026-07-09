# Legacy brightness API memory

This is sanitized memory from live investigation of the user's installed legacy
Razer stack. It documents facts needed to verify compatibility; it is not a copy
of proprietary implementation code.

## Installed boundary

The device API is provided by the locally installed 32-bit Razer DLL at the usual
location `%WINDIR%\SysWOW64\rzdevicedll.dll`. A 64-bit Python process cannot use
the registered COM objects directly, so the diagnostic probe compiles a small x86
.NET client with `%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe`.

Relevant COM identifiers discovered from the registered stack:

- Device enumerator class: `2CCA3A0E-AEEB-4B9C-AFC4-E4D48E95B6C2`
- `IDeviceEnumerator`: `61C39930-F5FB-475C-B7E9-CA693ED698AA`
- `IDevice`: `117FC605-9714-449F-977F-49ED712ADFC5`
- `IDisplayBrightness`: `8A010CD9-0F03-46BC-998D-2E55F36C85A6`

`IDisplayBrightness` exposes `SetBrightness(index, percent)` and
`GetBrightness(index, out percent)`. Enumerate devices first; do not assume the
target device's enumeration index.

## Confirmed display channels

| Index | Legacy UI label | Observed result |
|---|---|---|
| 1 | Keyboard brightness | Normal keyboard backlight |
| 2 | SwitchBlade UI brightness | Ten adaptive-key LCD backlights |

The Synapse Lighting page shows two sliders with these labels. No third slider for
the main 800x480 panel was observed.

## Verification procedure

1. Ensure the original Razer driver and stack are installed and the device is
   physically available.
2. Run query mode before setting anything:

   ```powershell
   python tools\legacy_brightness_probe.py
   ```

3. Identify the correct enumerated device and query results.
4. Use explicit set arguments for one channel and a conservative percentage.
5. Capture a local ADB photo before and after, or have the user confirm visually.
6. Reboot and verify persistence as required by `PRODUCT_PLAN.md`.

Do not package the generated probe executable. A consumer implementation should
ship a reviewed, versioned, publisher-signed owned helper or use another deliberate
32-bit integration strategy; unexpected runtime compilation is not release-ready.
