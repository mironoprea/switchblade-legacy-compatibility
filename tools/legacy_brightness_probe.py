#!/usr/bin/env python3
"""Query or set the legacy Razer display-brightness COM interface.

The registered Razer device DLL is 32-bit, so this helper builds a tiny x86 .NET
probe. Query mode is read-only. Setting brightness requires an explicit index and
percentage and is intended for protocol capture on the user's own hardware.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


CS_SOURCE = r"""
using System;
using System.Runtime.InteropServices;
using System.Threading;

[ComImport]
[Guid("8A010CD9-0F03-46BC-998D-2E55F36C85A6")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDisplayBrightness
{
    [PreserveSig] int SetBrightness(uint index, uint percent);
    [PreserveSig] int GetBrightness(uint index, out uint percent);
}

[ComImport]
[Guid("117FC605-9714-449F-977F-49ED712ADFC5")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDevice
{
}

[ComImport]
[Guid("61C39930-F5FB-475C-B7E9-CA693ED698AA")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDeviceEnumerator
{
    [PreserveSig] int EnumDevices(uint index, [MarshalAs(UnmanagedType.Interface)] out IDevice device);
}

internal static class Program
{
    private static readonly Guid EnumeratorClassId = new Guid("2CCA3A0E-AEEB-4B9C-AFC4-E4D48E95B6C2");

    private static int Main(string[] args)
    {
        Type type = Type.GetTypeFromCLSID(EnumeratorClassId, true);
        object instance = Activator.CreateInstance(type);
        IDeviceEnumerator enumerator = (IDeviceEnumerator)instance;
        try
        {
            bool set = args.Length == 4 && args[0] == "set";
            uint targetDevice = set ? UInt32.Parse(args[1]) : UInt32.MaxValue;
            uint targetDisplay = set ? UInt32.Parse(args[2]) : 0;
            uint targetPercent = set ? UInt32.Parse(args[3]) : 0;
            uint displayCount = args.Length == 2 && args[0] == "query" ? UInt32.Parse(args[1]) : 4;
            int startupDelay;
            if (!set && Int32.TryParse(Environment.GetEnvironmentVariable("SWITCHBLADE_BRIGHTNESS_PRECALL_MS"), out startupDelay) && startupDelay > 0)
            {
                Console.WriteLine("WAIT milliseconds=" + startupDelay);
                Thread.Sleep(startupDelay);
            }

            for (uint deviceIndex = 0; deviceIndex < 64; deviceIndex++)
            {
                IDevice device;
                int enumResult = enumerator.EnumDevices(deviceIndex, out device);
                if (enumResult != 0 || device == null) break;
                try
                {
                    IDisplayBrightness display;
                    try { display = (IDisplayBrightness)device; }
                    catch (InvalidCastException)
                    {
                        Console.WriteLine("DEVICE index=" + deviceIndex + " display=no");
                        continue;
                    }

                    if (set && deviceIndex == targetDevice)
                    {
                        int setDelay;
                        if (Int32.TryParse(Environment.GetEnvironmentVariable("SWITCHBLADE_BRIGHTNESS_PRECALL_MS"), out setDelay) && setDelay > 0)
                        {
                            Console.WriteLine("WAIT milliseconds=" + setDelay);
                            Thread.Sleep(setDelay);
                        }
                        int result = display.SetBrightness(targetDisplay, targetPercent);
                        Console.WriteLine("SET device=" + deviceIndex + " display=" + targetDisplay + " percent=" + targetPercent + " hr=0x" + result.ToString("X8"));
                        return result == 0 ? 0 : 1;
                    }
                    for (uint displayIndex = 0; displayIndex < displayCount; displayIndex++)
                    {
                        uint percent;
                        int result = display.GetBrightness(displayIndex, out percent);
                        Console.WriteLine("GET device=" + deviceIndex + " display=" + displayIndex + " percent=" + percent + " hr=0x" + result.ToString("X8"));
                    }
                }
                finally
                {
                    Marshal.FinalReleaseComObject(device);
                }
            }
            return set ? 2 : 0;
        }
        finally
        {
            Marshal.FinalReleaseComObject(instance);
        }
    }
}
"""


def compile_probe(output_dir: Path) -> Path:
    csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / r"Microsoft.NET\Framework\v4.0.30319\csc.exe"
    if not csc.is_file():
        raise FileNotFoundError(f"32-bit C# compiler not found: {csc}")
    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / "LegacyBrightnessProbe.cs"
    executable = output_dir / "LegacyBrightnessProbe.exe"
    source.write_text(CS_SOURCE, encoding="utf-8")
    subprocess.run(
        [str(csc), "/nologo", "/target:exe", "/platform:x86", f"/out:{executable}", str(source)],
        check=True,
    )
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("captures/legacy-brightness"))
    parser.add_argument("--query-count", type=int, default=12)
    parser.add_argument("--device-index", type=int)
    parser.add_argument("--display-index", type=int, default=0)
    parser.add_argument("--percent", type=int)
    parser.add_argument("--pre-call-seconds", type=float, default=0)
    args = parser.parse_args()

    if (args.device_index is None) != (args.percent is None):
        parser.error("--device-index and --percent must be supplied together")
    if args.device_index is not None and args.device_index < 0:
        parser.error("--device-index must be non-negative")
    if args.display_index < 0:
        parser.error("--display-index must be non-negative")
    if args.percent is not None and not 0 <= args.percent <= 100:
        parser.error("--percent must be 0-100")

    try:
        executable = compile_probe(args.output_dir)
        command = [str(executable)]
        if args.device_index is None:
            command += ["query", str(args.query_count)]
        else:
            command += ["set", str(args.device_index), str(args.display_index), str(args.percent)]
        environment = os.environ.copy()
        if args.pre_call_seconds > 0:
            environment["SWITCHBLADE_BRIGHTNESS_PRECALL_MS"] = str(int(args.pre_call_seconds * 1000))
        return subprocess.run(command, env=environment).returncode
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
