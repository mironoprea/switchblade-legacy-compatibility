"""Read-only inventory and privacy-safe classification for the legacy stack."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any


MI03_PATTERN = "VID_1532&PID_0114&MI_03"
LEGACY_PROCESSES = ("RzSynapse", "RzAppManager", "RzSBHelper")
LEGACY_SERVICES = ("RzAppManager", "RzSBService")
COM_REGISTRATIONS = ("RzSwitchbladeSDK", "RzSwitchbladeSDK2")
PACKAGE_EXTENSIONS = {".exe", ".msi"}
EXIT_CODES = {"healthy": 0, "repairable": 2, "blocked": 3, "unsupported": 4}


def _normalise(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _list(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _powershell_json(script: str) -> object:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("PowerShell inventory command failed")
    try:
        return json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError as exc:
        raise RuntimeError("PowerShell inventory returned malformed JSON") from exc


def collect_evidence(
    *,
    razer_root: Path,
    program_data: Path,
    powershell_json=_powershell_json,
) -> dict[str, object]:
    """Collect only the minimum data needed to classify the legacy installation."""
    if os.name != "nt":
        return {"os_supported": False, "collection_error": "unsupported_os"}

    try:
        pnp = powershell_json(
            "$d=Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceID -like '*VID_1532&PID_0114*'} | "
            "Select-Object DeviceID,DriverProviderName,Manufacturer,InfName,DeviceName,ServiceName,DriverVersion,IsSigned; "
            "if($d){$d | ConvertTo-Json -Compress}"
        )
        processes = powershell_json(
            "Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('RzSynapse','RzAppManager','RzSBHelper')} | "
            "Select-Object -ExpandProperty ProcessName | ConvertTo-Json -Compress"
        )
        services = powershell_json(
            "Get-Service -Name RzAppManager,RzSBService -ErrorAction SilentlyContinue | "
            "Select-Object Name,Status | ConvertTo-Json -Compress"
        )
        com = powershell_json(
            "@('RzSwitchbladeSDK','RzSwitchbladeSDK2') | ForEach-Object {[PSCustomObject]@{Name=$_;Present=(Test-Path ('Registry::HKEY_CLASSES_ROOT\\' + $_))}} | "
            "ConvertTo-Json -Compress"
        )
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return {"os_supported": True, "collection_error": "windows_query_failed"}

    sdk = program_data / "Razer" / "SwitchBlade" / "SDK" / "RzSwitchbladeSDK2.dll"
    profiles = program_data / "Razer" / "Synapse" / "Devices" / "DeathStalker Ultimate" / "Profiles"
    package_names: list[str] = []
    # Candidate names only: paths and package contents are intentionally never reported.
    for directory in (razer_root.parent, program_data / "Razer"):
        if directory.is_dir():
            package_names.extend(
                item.name for item in directory.glob("*Razer*") if item.suffix.casefold() in PACKAGE_EXTENSIONS
            )
    return {
        "os_supported": True,
        "drivers": _list(pnp),
        "files": {
            "synapse": (razer_root / "Synapse" / "RzSynapse.exe").is_file(),
            "app_manager": (razer_root / "SwitchBlade" / "RzAppManager.exe").is_file(),
            "sdk": sdk.is_file(),
            "profiles": profiles.is_dir() and any(profiles.glob("*.xml")),
        },
        "processes": processes if isinstance(processes, list) else ([processes] if processes else []),
        "services": _list(services),
        "com": {name: bool(item.get("Present")) for item in _list(com) if item.get("Name") in COM_REGISTRATIONS},
        "packages": package_names,
    }


def _driver_state(drivers: list[dict[str, Any]]) -> str:
    mi03 = [driver for driver in drivers if MI03_PATTERN in _normalise(driver.get("DeviceID")).upper()]
    if not mi03:
        return "missing"
    if len(mi03) != 1:
        return "ambiguous"
    driver = mi03[0]
    provider = _normalise(driver.get("DriverProviderName"))
    manufacturer = _normalise(driver.get("Manufacturer"))
    inf = _normalise(driver.get("InfName"))
    device = _normalise(driver.get("DeviceName"))
    service = _normalise(driver.get("ServiceName"))
    if any(token in " ".join((provider, manufacturer, inf, device, service)) for token in ("winusb", "libusb")):
        return "winusb"
    razer_evidence = "razer" in provider or "razer" in manufacturer
    expected_evidence = "razer" in inf or "razer" in service or "deathstalker" in device
    if driver.get("IsSigned") is True and razer_evidence and expected_evidence:
        return "razer_signed"
    return "unknown"


def _package_count(packages: object) -> int:
    if not isinstance(packages, list):
        return 0
    return sum(
        isinstance(name, str)
        and Path(name).suffix.casefold() in PACKAGE_EXTENSIONS
        and "razer" in name.casefold()
        for name in packages
    )


def classify(evidence: dict[str, object]) -> dict[str, object]:
    """Classify sanitized evidence without exposing source paths or command output."""
    if not evidence.get("os_supported", False):
        return _result("unsupported", ["unsupported_os"], ["Run this utility on supported Windows."])
    if evidence.get("collection_error"):
        return _result("blocked", [str(evidence["collection_error"])], ["Retry the read-only inventory from an elevated terminal."])

    drivers = _list(evidence.get("drivers"))
    all_deathstalker = [driver for driver in drivers if "VID_1532&PID_0114" in _normalise(driver.get("DeviceID")).upper()]
    driver = _driver_state(drivers)
    if not all_deathstalker:
        return _result("blocked", ["device_missing"], ["Connect the Razer DeathStalker Ultimate and run scan again."], driver)
    if driver == "winusb":
        return _result("blocked", ["mi03_winusb_bound"], ["Restore the original Razer MI_03 driver before using this utility."], driver)
    if driver == "ambiguous":
        return _result("blocked", ["mi03_ambiguous"], ["Remove duplicate device entries, then run scan again."], driver)
    if driver != "razer_signed":
        return _result("blocked", ["mi03_driver_unverified"], ["Verify the signed original Razer driver on MI_03."], driver)

    files = evidence.get("files") if isinstance(evidence.get("files"), dict) else {}
    missing = [name for name in ("synapse", "app_manager", "sdk", "profiles") if not files.get(name)]
    com = evidence.get("com") if isinstance(evidence.get("com"), dict) else {}
    missing_com = [name for name in COM_REGISTRATIONS if not com.get(name)]
    packages = _package_count(evidence.get("packages"))
    if missing or missing_com:
        reasons = [f"missing_{name}" for name in missing] + ["missing_com_registration" for _ in missing_com]
        if packages:
            return _result("repairable", reasons, ["Review the locally cached official Razer package candidates before repair."], driver)
        return _result("blocked", reasons + ["official_package_not_found"], ["Locate an official locally cached Razer package before repair."], driver)
    return _result("healthy", [], ["No repair action is needed."], driver)


def _result(classification: str, reasons: list[str], next_steps: list[str], driver: str = "unknown") -> dict[str, object]:
    return {"classification": classification, "reason_codes": reasons, "next_steps": next_steps, "driver_state": driver}


def public_report(evidence: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    """Return an explicit allowlist suitable for persistent diagnostics."""
    files = evidence.get("files") if isinstance(evidence.get("files"), dict) else {}
    services = _list(evidence.get("services"))
    service_names = {_normalise(item.get("Name")) for item in services}
    processes = evidence.get("processes") if isinstance(evidence.get("processes"), list) else []
    return {
        "classification": result["classification"],
        "reason_codes": result["reason_codes"],
        "next_steps": result["next_steps"],
        "device": {"model": "deathstalker_ultimate", "mi03_driver": result["driver_state"]},
        "components": {name: bool(files.get(name)) for name in ("synapse", "app_manager", "sdk", "profiles")},
        "services": {name: _normalise(name) in service_names for name in LEGACY_SERVICES},
        "processes_running": sorted(
            name for name in processes if isinstance(name, str) and name in LEGACY_PROCESSES
        ),
        "com_registrations": {
            name: bool((evidence.get("com") or {}).get(name)) for name in COM_REGISTRATIONS
        },
        "official_package_candidates": _package_count(evidence.get("packages")),
    }
