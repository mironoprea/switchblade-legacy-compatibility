#!/usr/bin/env python3
"""Take a photo from an ADB-connected Android phone and pull it locally.

The hardware bring-up setup uses a Motorola phone aimed at the keyboard.  This
helper wakes the phone, opens the camera, triggers the shutter, then pulls the
newest image from ``/sdcard/DCIM/Camera``.

Example:

    python tools/adb_photo.py --output captures/phone/keyboard.jpg
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


DEFAULT_ADB = "adb"
DEFAULT_CAMERA_DIR = "/sdcard/DCIM/Camera"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".heic", ".dng")


def run_adb(adb: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [adb, *args],
        check=check,
        capture_output=True,
        text=True,
    )


def latest_camera_file(adb: str, *, camera_dir: str = DEFAULT_CAMERA_DIR) -> Optional[str]:
    proc = run_adb(adb, ["shell", "ls", "-t", camera_dir], check=False)
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        name = line.strip()
        lower = name.lower()
        if name and ".thumb" not in lower and lower.endswith(IMAGE_EXTENSIONS):
            return name
    return None


def capture_photo(
    adb: str,
    *,
    output: Path,
    camera_dir: str = DEFAULT_CAMERA_DIR,
    settle_seconds: float = 3.0,
) -> Path:
    before = latest_camera_file(adb, camera_dir=camera_dir)

    run_adb(adb, ["shell", "input", "keyevent", "KEYCODE_WAKEUP"], check=False)
    run_adb(adb, ["shell", "wm", "dismiss-keyguard"], check=False)
    run_adb(adb, ["shell", "am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA"])
    time.sleep(settle_seconds)
    run_adb(adb, ["shell", "input", "keyevent", "KEYCODE_CAMERA"])
    time.sleep(settle_seconds)

    after = latest_camera_file(adb, camera_dir=camera_dir)
    if not after:
        raise RuntimeError("No camera image found after shutter trigger.")
    if after == before:
        raise RuntimeError(
            "Camera did not create a new image. Check phone unlock/camera permissions."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    remote = f"{camera_dir.rstrip('/')}/{after}"
    run_adb(adb, ["pull", remote, str(output)])
    return output


def resolve_adb(path: Optional[str]) -> str:
    if path:
        return path
    found = shutil.which(DEFAULT_ADB)
    if found:
        return found
    return DEFAULT_ADB


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", help="Path to adb.exe")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/phone/keyboard-latest.jpg"),
        help="local output image path",
    )
    parser.add_argument("--camera-dir", default=DEFAULT_CAMERA_DIR)
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    args = parser.parse_args()

    try:
        output = capture_photo(
            resolve_adb(args.adb),
            output=args.output,
            camera_dir=args.camera_dir,
            settle_seconds=args.settle_seconds,
        )
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
