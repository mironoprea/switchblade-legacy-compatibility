#!/usr/bin/env python3
"""Exercise the installed Razer SwitchBlade SDK during USB reference captures.

This helper is intentionally capture-oriented: it builds a tiny x86 .NET
program that calls the 32-bit Razer SDK DLL, generates distinct touchpad/key
images, and holds the SDK session open long enough for USBPcap.

Example:

    python tools/sdk_exerciser.py --key 1 --hold-seconds 20
    python tools/sdk_exerciser.py --all-keys --no-touchpad --hold-seconds 30
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


DEFAULT_SDK_DIR = Path(r"C:\ProgramData\Razer\SwitchBlade\SDK")
DEFAULT_OUTPUT_DIR = Path("captures/sdk-exerciser")
DEFAULT_CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / (
    r"Microsoft.NET\Framework\v4.0.30319\csc.exe"
)


CS_SOURCE = r"""
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

internal static class Program
{
    [StructLayout(LayoutKind.Sequential)]
    private struct NativePoint
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativeMessage
    {
        public IntPtr hwnd;
        public uint message;
        public UIntPtr wParam;
        public IntPtr lParam;
        public uint time;
        public NativePoint pt;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string lpPathName);

    [DllImport("user32.dll")]
    private static extern bool PeekMessage(out NativeMessage lpMsg, IntPtr hWnd, uint wMsgFilterMin, uint wMsgFilterMax, uint wRemoveMsg);

    [DllImport("user32.dll")]
    private static extern bool TranslateMessage(ref NativeMessage lpMsg);

    [DllImport("user32.dll")]
    private static extern IntPtr DispatchMessage(ref NativeMessage lpMsg);

    [DllImport("RzSwitchbladeSDK2.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int RzSBStart();

    [DllImport("RzSwitchbladeSDK2.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int RzSBStop();

    [DllImport("RzSwitchbladeSDK2.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int RzSBSetImageDynamicKey(int key, int keyState, string imagePath);

    [DllImport("RzSwitchbladeSDK2.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int RzSBSetImageTouchpad(string imagePath);

    private static int Main(string[] args)
    {
        if (args.Length < 3 || ((args.Length - 3) % 2) != 0)
        {
            Console.Error.WriteLine("Usage: SdkExerciser.exe <sdkDir> <holdSeconds> <touchPath|-> [<key> <imagePath>]...");
            return 64;
        }

        string sdkDir = args[0];
        int holdSeconds = int.Parse(args[1]);
        string touchPath = args[2];
        SetDllDirectory(sdkDir);

        int start = RzSBStart();
        Console.WriteLine("RzSBStart=0x" + start.ToString("X8") + " LastError=" + Marshal.GetLastWin32Error());
        PumpMessages(1000);
        if (start != 0)
        {
            return 2;
        }

        int preCallMilliseconds = 0;
        string preCallValue = Environment.GetEnvironmentVariable("SWITCHBLADE_SDK_PRECALL_MS");
        if (!String.IsNullOrEmpty(preCallValue) && Int32.TryParse(preCallValue, out preCallMilliseconds) && preCallMilliseconds > 0)
        {
            Console.WriteLine("Pre-call hold for " + preCallMilliseconds + " ms.");
            PumpMessages(preCallMilliseconds);
        }

        int failures = 0;
        try
        {
            if (touchPath != "-")
            {
                int touch = RzSBSetImageTouchpad(touchPath);
                Console.WriteLine("RzSBSetImageTouchpad=0x" + touch.ToString("X8") + " path=" + touchPath);
                if (touch != 0) failures++;
            }

            for (int i = 3; i < args.Length; i += 2)
            {
                int key = int.Parse(args[i]);
                string imagePath = args[i + 1];
                int up = RzSBSetImageDynamicKey(key, 1, imagePath);
                Console.WriteLine("RzSBSetImageDynamicKey key=" + key + " state=up hr=0x" + up.ToString("X8") + " path=" + imagePath);
                if (up != 0) failures++;

                int down = RzSBSetImageDynamicKey(key, 2, imagePath);
                Console.WriteLine("RzSBSetImageDynamicKey key=" + key + " state=down hr=0x" + down.ToString("X8") + " path=" + imagePath);
                if (down != 0) failures++;
            }

            Console.WriteLine("Holding for " + holdSeconds + " seconds.");
            PumpMessages(holdSeconds * 1000);
        }
        finally
        {
            int stop = RzSBStop();
            Console.WriteLine("RzSBStop=0x" + stop.ToString("X8") + " LastError=" + Marshal.GetLastWin32Error());
        }

        return failures == 0 ? 0 : 1;
    }

    private static void PumpMessages(int milliseconds)
    {
        Stopwatch sw = Stopwatch.StartNew();
        do
        {
            NativeMessage msg;
            while (PeekMessage(out msg, IntPtr.Zero, 0, 0, 1))
            {
                TranslateMessage(ref msg);
                DispatchMessage(ref msg);
            }
            Thread.Sleep(10);
        }
        while (sw.ElapsedMilliseconds < milliseconds);
    }
}
"""


def selected_keys(args: argparse.Namespace) -> list[int]:
    if args.all_keys:
        return list(range(1, 11))
    keys = args.key or [1]
    bad = [key for key in keys if key < 1 or key > 10]
    if bad:
        raise ValueError(f"dynamic key numbers must be 1-10, got {bad}")
    return keys


def find_csc(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    if DEFAULT_CSC.is_file():
        return DEFAULT_CSC
    found = shutil.which("csc")
    if found:
        return Path(found)
    raise FileNotFoundError("csc.exe not found; install .NET Framework build tools")


def build_csc_command(csc: Path, source: Path, exe: Path) -> list[str]:
    return [
        str(csc),
        "/nologo",
        "/target:exe",
        "/platform:x86",
        f"/out:{exe}",
        str(source),
    ]


def compile_exerciser(csc: Path, output_dir: Path) -> Path:
    source = output_dir / "SdkExerciser.cs"
    exe = output_dir / "SdkExerciser.exe"
    source.write_text(CS_SOURCE, encoding="utf-8")
    subprocess.run(build_csc_command(csc, source, exe), check=True)
    return exe


def make_key_image(path: Path, key: int) -> None:
    image = Image.new("RGB", (115, 115), (10 + key * 18, 20, 150 - key * 8))
    draw = ImageDraw.Draw(image)
    draw.rectangle((3, 3, 111, 111), outline=(255, 255, 255), width=4)
    draw.rectangle((0, 0, 114, 18), fill=(255, 210, 0))
    draw.text((18, 35), "CAPTURE", fill=(255, 255, 255))
    draw.text((43, 62), f"K{key}", fill=(255, 255, 255))
    image.save(path)


def make_touchpad_image(path: Path) -> None:
    image = Image.new("RGB", (800, 480), (8, 24, 70))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 799, 60), fill=(255, 210, 0))
    draw.text((240, 180), "SDK CAPTURE", fill=(255, 255, 255))
    draw.text((230, 230), "Touchpad reference image", fill=(255, 255, 255))
    image.save(path)


def build_exerciser_args(
    sdk_dir: Path,
    hold_seconds: int,
    touchpad: Path | None,
    key_images: list[tuple[int, Path]],
) -> list[str]:
    args = [str(sdk_dir), str(hold_seconds), str(touchpad) if touchpad else "-"]
    for key, path in key_images:
        args.extend([str(key), str(path)])
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-dir", type=Path, default=DEFAULT_SDK_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--csc", help="path to 32-bit-capable csc.exe")
    parser.add_argument("--hold-seconds", type=int, default=20)
    parser.add_argument(
        "--pre-call-seconds",
        type=float,
        default=0,
        help="delay after RzSBStart before image calls, useful for attaching tracers",
    )
    parser.add_argument("--key", action="append", type=int, help="1-based dynamic key number; repeatable")
    parser.add_argument("--all-keys", action="store_true")
    parser.add_argument("--no-touchpad", action="store_true")
    args = parser.parse_args()

    if not args.sdk_dir.is_dir():
        print(f"Error: SDK directory not found: {args.sdk_dir}", file=sys.stderr)
        return 1
    if not (args.sdk_dir / "RzSwitchbladeSDK2.dll").is_file():
        print(f"Error: RzSwitchbladeSDK2.dll not found in {args.sdk_dir}", file=sys.stderr)
        return 1

    try:
        keys = selected_keys(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    key_images = []
    for key in keys:
        path = args.output_dir / f"sdk-key-{key}.png"
        make_key_image(path, key)
        key_images.append((key, path.resolve()))

    touchpad = None
    if not args.no_touchpad:
        touchpad = (args.output_dir / "sdk-touchpad.png").resolve()
        make_touchpad_image(touchpad)

    try:
        csc = find_csc(args.csc)
        exe = compile_exerciser(csc, args.output_dir)
        cmd = [str(exe), *build_exerciser_args(args.sdk_dir, args.hold_seconds, touchpad, key_images)]
        env = os.environ.copy()
        if args.pre_call_seconds > 0:
            env["SWITCHBLADE_SDK_PRECALL_MS"] = str(int(args.pre_call_seconds * 1000))
        print("Running:", " ".join(cmd))
        return subprocess.run(cmd, env=env).returncode
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Error running SDK exerciser: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
