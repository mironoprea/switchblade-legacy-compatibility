# Android ADB camera setup for keyboard vision

This workflow gives a local developer or model a repeatable view of the physical
keyboard without committing private images.

## Prerequisites

1. Install official Android SDK Platform-Tools so `adb.exe` is on `PATH`.
2. On the Android phone, enable Developer options and USB debugging.
3. Connect over USB, unlock the phone, and accept the computer's RSA prompt.
4. Aim the phone so the entire keyboard, main panel, and ten LCD keys are visible.
5. Confirm exactly one authorized device:

```powershell
adb devices -l
```

The original setup used a Motorola phone successfully. Do not encode or publish
its serial number.

## Capture

```powershell
python tools\adb_photo.py --output captures\phone\keyboard-latest.jpg
```

Optional arguments:

```powershell
python tools\adb_photo.py `
  --adb C:\Android\platform-tools\adb.exe `
  --camera-dir /sdcard/DCIM/Camera `
  --settle-seconds 4 `
  --output captures\phone\keyboard-latest.jpg
```

The helper records the newest pre-capture filename, wakes the phone, dismisses the
keyguard when permitted, opens the still camera, sends the camera key event, waits,
selects the newest non-thumbnail image, and pulls it.

## Troubleshooting

- `unauthorized`: unlock the phone and accept the RSA dialog, then rerun `adb devices`.
- No new image: unlock the phone, grant camera permission, open the stock camera
  once manually, and increase `--settle-seconds`.
- Wrong camera directory: inspect `adb shell ls -t /sdcard/DCIM/Camera` or pass the
  device's actual camera directory.
- Multiple devices: pass a dedicated ADB server/device selection manually before
  using the helper; the current helper expects the default single device.

## Privacy and evidence handling

`captures/phone/` is gitignored. Before sharing any image, inspect the entire frame
for email addresses, account names, notifications, conversations, desktop content,
reflections, serial numbers, and unrelated people or property. Prefer documenting
the observed result in `HANDOFF.md` rather than committing a photo.

Useful acceptance shots are: baseline after reboot, configurator visible, all ten
keys lit distinctly, minimum/maximum keyboard brightness, and minimum/maximum
SwitchBlade UI brightness.
