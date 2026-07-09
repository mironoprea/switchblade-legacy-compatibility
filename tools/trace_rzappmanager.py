#!/usr/bin/env python3
"""Trace RzAppManager file I/O and SwitchBlade window messages with Frida.

This is an optional reverse-engineering helper for the Razer SDK path.  Run it
while exercising the SDK to identify whether RzAppManager opens device/file
handles or sends compact message payloads related to key-image rendering.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional


JS = r"""
const handles = {};
const messageNames = {};

function hexDump(ptr, length) {
  const maxLen = Math.min(length, 256);
  if (ptr.isNull() || maxLen <= 0) return "";
  const bytes = ptr.readByteArray(maxLen);
  const array = new Uint8Array(bytes);
  const parts = [];
  for (let i = 0; i < array.length; i++) {
    parts.push(("0" + array[i].toString(16)).slice(-2));
  }
  return parts.join(" ");
}

function emit(event) {
  send(event);
}

function hook(name, callbacks) {
  const address = findExport("kernel32.dll", name) || findExport("user32.dll", name) || findExport("hid.dll", name);
  if (address) {
    Interceptor.attach(address, callbacks);
    emit({type: "hooked", name: name});
  }
}

hook("CreateFileW", {
  onEnter(args) {
    this.path = args[0].isNull() ? "" : args[0].readUtf16String();
    this.access = args[1].toUInt32();
    this.share = args[2].toUInt32();
  },
  onLeave(retval) {
    if (!retval.equals(ptr("-1"))) {
      handles[retval.toString()] = this.path;
    }
    emit({type: "CreateFileW", handle: retval.toString(), path: this.path, access: this.access, share: this.share});
  }
});

hook("WriteFile", {
  onEnter(args) {
    this.handle = args[0].toString();
    this.length = args[2].toUInt32();
    this.path = handles[this.handle] || "";
    this.hex = hexDump(args[1], this.length);
  },
  onLeave(retval) {
    emit({type: "WriteFile", ok: retval.toInt32(), handle: this.handle, path: this.path, length: this.length, hex: this.hex});
  }
});

hook("ReadFile", {
  onEnter(args) {
    this.handle = args[0].toString();
    this.length = args[2].toUInt32();
    this.path = handles[this.handle] || "";
    this.buffer = args[1];
  },
  onLeave(retval) {
    emit({type: "ReadFile", ok: retval.toInt32(), handle: this.handle, path: this.path, length: this.length, hex: hexDump(this.buffer, this.length)});
  }
});

hook("DeviceIoControl", {
  onEnter(args) {
    this.handle = args[0].toString();
    this.path = handles[this.handle] || "";
    this.code = args[1].toUInt32();
    this.inLength = args[3].toUInt32();
    this.inHex = hexDump(args[2], this.inLength);
    this.outBuffer = args[4];
    this.outLength = args[5].toUInt32();
  },
  onLeave(retval) {
    emit({type: "DeviceIoControl", ok: retval.toInt32(), handle: this.handle, path: this.path, code: this.code, inLength: this.inLength, inHex: this.inHex, outLength: this.outLength, outHex: hexDump(this.outBuffer, this.outLength)});
  }
});

function hookHid(name) {
  const address = findExport("hid.dll", name);
  if (!address) return;
  Interceptor.attach(address, {
    onEnter(args) {
      this.handle = args[0].toString();
      this.path = handles[this.handle] || "";
      this.buffer = args[1];
      this.length = args[2].toUInt32();
      this.hex = hexDump(this.buffer, this.length);
    },
    onLeave(retval) {
      emit({type: name, ok: retval.toInt32(), handle: this.handle, path: this.path, length: this.length, hex: this.hex, resultHex: hexDump(this.buffer, this.length)});
    }
  });
  emit({type: "hooked", name: name});
}

hookHid("HidD_SetFeature");
hookHid("HidD_SetOutputReport");
hookHid("HidD_GetFeature");

hook("CloseHandle", {
  onEnter(args) {
    this.handle = args[0].toString();
    this.path = handles[this.handle] || "";
  },
  onLeave(retval) {
    if (this.path) {
      emit({type: "CloseHandle", handle: this.handle, path: this.path});
      delete handles[this.handle];
    }
  }
});

hook("RegisterWindowMessageW", {
  onEnter(args) {
    this.name = args[0].isNull() ? "" : args[0].readUtf16String();
  },
  onLeave(retval) {
    messageNames[retval.toUInt32()] = this.name;
    if (this.name.indexOf("RZWM_") >= 0 || this.name.indexOf("Razer") >= 0) {
      emit({type: "RegisterWindowMessageW", id: retval.toUInt32(), name: this.name});
    }
  }
});

function hookMessage(name) {
  const address = findExport("user32.dll", name);
  if (!address) return;
  Interceptor.attach(address, {
    onEnter(args) {
      const msg = args[1].toUInt32();
      const msgName = messageNames[msg] || "";
      if (msgName || (msg >= 0x9000 && msg <= 0x9100)) {
        emit({type: name, hwnd: args[0].toString(), msg: msg, msgName: msgName, wParam: args[2].toString(), lParam: args[3].toString()});
      }
    }
  });
  emit({type: "hooked", name: name});
}

hookMessage("PostMessageW");
hookMessage("SendMessageW");
hookMessage("SendNotifyMessageW");

function findExport(moduleName, exportName) {
  try {
    if (Module.findExportByName) {
      return Module.findExportByName(moduleName, exportName);
    }
  } catch (_) {
  }
  try {
    const module = Process.getModuleByName(moduleName);
    if (module.findExportByName) {
      return module.findExportByName(exportName);
    }
    for (const symbol of module.enumerateExports()) {
      if (symbol.name === exportName) return symbol.address;
    }
  } catch (_) {
  }
  try {
    if (Module.getGlobalExportByName) {
      return Module.getGlobalExportByName(exportName);
    }
  } catch (_) {
  }
  return null;
}
"""


def find_pid(name: str) -> Optional[int]:
    import psutil

    lower = name.lower()
    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == lower:
            return proc.pid
    return None


def wait_for_pid(name: str, timeout: float) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pid = find_pid(name)
        if pid is not None:
            return pid
        time.sleep(0.25)
    raise TimeoutError(f"{name} was not found within {timeout:.1f}s")


def format_event(event: dict[str, Any]) -> str:
    etype = event.get("type")
    if etype in {"WriteFile", "ReadFile"}:
        path = event.get("path") or event.get("handle")
        return f"{etype} len={event.get('length')} path={path} hex={event.get('hex', '')}"
    if etype == "CreateFileW":
        return f"CreateFileW handle={event.get('handle')} access=0x{event.get('access'):08x} path={event.get('path')}"
    if etype == "DeviceIoControl":
        path = event.get("path") or event.get("handle")
        return (
            f"DeviceIoControl code=0x{event.get('code', 0):08x} path={path} "
            f"in={event.get('inHex', '')} out={event.get('outHex', '')}"
        )
    if etype in {"HidD_SetFeature", "HidD_SetOutputReport", "HidD_GetFeature"}:
        path = event.get("path") or event.get("handle")
        return f"{etype} path={path} len={event.get('length')} hex={event.get('hex', '')} result={event.get('resultHex', '')}"
    if etype in {"PostMessageW", "SendMessageW", "SendNotifyMessageW"}:
        name = event.get("msgName") or f"0x{event.get('msg'):04x}"
        return f"{etype} {name} hwnd={event.get('hwnd')} wParam={event.get('wParam')} lParam={event.get('lParam')}"
    return json.dumps(event, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", default="RzAppManager.exe")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--wait-seconds", type=float, default=30)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        import frida
    except ImportError:
        print("Error: install frida with `python -m pip install frida`.", file=sys.stderr)
        return 1

    try:
        pid = args.pid if args.pid is not None else wait_for_pid(args.process, args.wait_seconds)
        session = frida.attach(pid)
    except Exception as exc:
        print(f"Error attaching to process: {exc}", file=sys.stderr)
        return 1

    lines: list[str] = []

    def on_message(message, data):
        if message["type"] == "send":
            payload = message["payload"]
            line = format_event(payload)
        else:
            line = json.dumps(message, sort_keys=True)
        lines.append(line)
        print(line, flush=True)

    script = session.create_script(JS)
    script.on("message", on_message)
    script.load()

    try:
        time.sleep(args.duration)
    finally:
        try:
            script.unload()
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
