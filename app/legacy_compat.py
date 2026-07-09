"""Unofficial compatibility utility for an existing Razer Synapse 2 install.

This module never ships Razer files. It inventories the local installation,
creates user-owned backups, exports the currently installed MI_03 driver for
local rollback, and launches the legacy configurator with its required
``-launch`` argument.
"""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

VID = "1532"
PID = "0114"
MI03_PATTERN = "VID_1532&PID_0114&MI_03"
RAZER_ROOT = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Razer"
SYNAPSE_EXE = RAZER_ROOT / "Synapse" / "RzSynapse.exe"
APP_MANAGER_EXE = RAZER_ROOT / "SwitchBlade" / "RzAppManager.exe"
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SwitchbladeLegacyCompatibility"
BACKUPS_DIR = DATA_ROOT / "Backups"
REPORTS_DIR = DATA_ROOT / "Reports"
JOURNALS_DIR = DATA_ROOT / "Journals"

_LOGICAL_ROOTS = (
    "Synapse/Devices/DeathStalker Ultimate/Profiles",
    "Synapse/Accounts/User/Devices/DeathStalker Ultimate/Profiles",
    "Synapse/Accounts/User/Macros",
    "SwitchBlade/DeathStalker",
    "SwitchBlade/Apps/Razer",
)
_ACCOUNT_PREFIX = "Synapse/Accounts/User/"
_ALLOWED_NAMES = {"config.xml", "profiles.json"}
_ALLOWED_SUFFIXES = {".xml", ".png", ".jpg", ".jpeg", ".bmp", ".rzdisplaystate"}


def _powershell_json(script: str):
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell inventory failed")
    output = result.stdout.strip()
    return json.loads(output) if output else None


def get_mi03_driver() -> dict | None:
    if os.name != "nt":
        return None
    script = (
        "$d=Get-CimInstance Win32_PnPSignedDriver | "
        f"Where-Object {{$_.DeviceID -like '*{MI03_PATTERN}*'}} | Select-Object -First 1 "
        "DeviceName,DeviceID,DriverProviderName,DriverVersion,InfName,DriverDate,IsSigned; "
        "if($d){$d | ConvertTo-Json -Compress}"
    )
    return _powershell_json(script)


def _processes() -> list[str]:
    if os.name != "nt":
        return []
    script = (
        "Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object {$_.ProcessName -in @('RzSynapse','RzAppManager','RzSBHelper')} | "
        "Select-Object -ExpandProperty ProcessName | ConvertTo-Json -Compress"
    )
    value = _powershell_json(script)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def scan() -> dict:
    driver = get_mi03_driver()
    sdk = PROGRAM_DATA / "Razer" / "SwitchBlade" / "SDK" / "RzSwitchbladeSDK2.dll"
    profile_dir = PROGRAM_DATA / "Razer" / "Synapse" / "Devices" / "DeathStalker Ultimate" / "Profiles"
    status = {
        "product": "Switchblade Legacy Compatibility (Unofficial)",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "synapse_executable": str(SYNAPSE_EXE),
        "synapse_installed": SYNAPSE_EXE.is_file(),
        "switchblade_manager_installed": APP_MANAGER_EXE.is_file(),
        "sdk_installed": sdk.is_file(),
        "device_profiles_present": profile_dir.is_dir() and any(profile_dir.glob("*.xml")),
        "mi03_driver": driver,
        "mi03_is_razer": bool(driver and driver.get("DriverProviderName") == "Razer Inc"),
        "legacy_processes": _processes(),
    }
    status["ready"] = all(
        [
            status["synapse_installed"],
            status["switchblade_manager_installed"],
            status["sdk_installed"],
            status["device_profiles_present"],
            status["mi03_is_razer"],
        ]
    )
    return status


def _backup_candidates() -> list[tuple[Path, str]]:
    razer = PROGRAM_DATA / "Razer"
    candidates: list[tuple[Path, str]] = []
    device_profiles = razer / "Synapse" / "Devices" / "DeathStalker Ultimate" / "Profiles"
    if device_profiles.is_dir():
        candidates.append((device_profiles, "Synapse/Devices/DeathStalker Ultimate/Profiles"))
    accounts = razer / "Synapse" / "Accounts"
    if accounts.is_dir():
        for account in accounts.iterdir():
            if not account.is_dir():
                continue
            for relative in (
                Path("Devices") / "DeathStalker Ultimate" / "Profiles",
                Path("Macros"),
            ):
                source = account / relative
                if source.is_dir():
                    # Account directory names are replaced with a stable neutral label.
                    candidates.append((source, f"Synapse/Accounts/User/{relative.as_posix()}"))
    switchblade_state = razer / "SwitchBlade" / "DeathStalker"
    if switchblade_state.is_dir():
        candidates.append((switchblade_state, "SwitchBlade/DeathStalker"))
    apps = razer / "SwitchBlade" / "Apps" / "Razer"
    if apps.is_dir():
        candidates.append((apps, "SwitchBlade/Apps/Razer"))
    return candidates


def _iter_backup_files(source: Path):
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        lower_parts = {part.lower() for part in item.parts}
        if "analytics" in lower_parts or "logs" in lower_parts:
            continue
        if item.name.lower() == "razerlogindata.xml":
            continue
        if item.name.lower() in _ALLOWED_NAMES or item.suffix.lower() in _ALLOWED_SUFFIXES:
            yield item


def _safe_member_parts(name: str) -> tuple[str, ...]:
    """Return safe POSIX ZIP member components or reject the member."""
    if not isinstance(name, str) or not name or "\\" in name or name.startswith("/"):
        raise ValueError(f"Unsafe ZIP member path: {name!r}")
    parts = tuple(name.split("/"))
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError(f"Unsafe ZIP member path: {name!r}")
    if len(parts[0]) >= 2 and parts[0][0].isalpha() and parts[0][1] == ":":
        raise ValueError(f"Unsafe ZIP member path: {name!r}")
    return parts


def _split_logical_path(member: str) -> tuple[str, tuple[str, ...]]:
    parts = _safe_member_parts(member)
    if parts[0] != "data":
        raise ValueError(f"Restorable member must begin with data/: {member}")
    logical = "/".join(parts[1:])
    for root in _LOGICAL_ROOTS:
        prefix = root + "/"
        if logical.startswith(prefix):
            relative = tuple(logical[len(prefix):].split("/"))
            return root, relative
    raise ValueError(f"Unsupported logical restore path: {member}")


def _allowed_restore_member(member: str) -> bool:
    _root, relative = _split_logical_path(member)
    lowered = {part.lower() for part in relative}
    name = relative[-1].lower()
    suffix = Path(relative[-1]).suffix.lower()
    return (
        "analytics" not in lowered
        and "logs" not in lowered
        and name != "razerlogindata.xml"
        and (name in _ALLOWED_NAMES or suffix in _ALLOWED_SUFFIXES)
    )


def validate_backup(archive: Path) -> dict:
    """Completely validate a legacy backup without extracting any members."""
    archive = Path(archive)
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            for name in names:
                _safe_member_parts(name)
            if len(names) != len(set(names)):
                raise ValueError("Backup contains duplicate ZIP member names")
            if names.count("manifest.json") != 1:
                raise ValueError("Backup must contain exactly one manifest.json")
            try:
                manifest = json.loads(bundle.read("manifest.json"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Backup manifest is not valid JSON") from exc
            if not isinstance(manifest, dict) or manifest.get("format") != 1:
                raise ValueError("Unsupported or malformed backup manifest")
            records = manifest.get("files")
            if not isinstance(records, list):
                raise ValueError("Backup manifest files must be a list")

            declared: set[str] = set()
            info_by_name = {info.filename: info for info in infos}
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Backup manifest contains a malformed file record")
                member = record.get("path")
                size = record.get("size")
                digest = record.get("sha256")
                if (
                    not isinstance(member, str)
                    or isinstance(size, bool)
                    or not isinstance(size, int)
                    or size < 0
                    or not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdefABCDEF" for character in digest)
                ):
                    raise ValueError("Backup manifest contains a malformed file record")
                if member in declared:
                    raise ValueError(f"Backup manifest declares a member more than once: {member}")
                declared.add(member)
                if not _allowed_restore_member(member):
                    raise ValueError(f"Backup member is not on the restore allowlist: {member}")
                info = info_by_name.get(member)
                if info is None:
                    raise ValueError(f"Declared backup member is missing: {member}")
                content = bundle.read(info)
                if info.file_size != size or len(content) != size:
                    raise ValueError(f"Backup member size does not match its manifest: {member}")
                if hashlib.sha256(content).hexdigest().lower() != digest.lower():
                    raise ValueError(f"Backup member checksum does not match its manifest: {member}")

            data_members = {name for name in names if name.startswith("data/")}
            if data_members != declared:
                undeclared = data_members - declared
                if undeclared:
                    raise ValueError("Backup contains undeclared data members")
                raise ValueError("Backup manifest declares missing data members")
            extra_members = set(names) - declared - {"manifest.json"}
            if extra_members:
                raise ValueError("Backup contains unsupported non-data members")
            return manifest
    except zipfile.BadZipFile as exc:
        raise ValueError("Backup is not a valid ZIP archive") from exc


def _restore_destinations(manifest: dict) -> list[tuple[str, Path]]:
    """Resolve fixed local destinations without accepting archive destinations."""
    razer = PROGRAM_DATA / "Razer"
    roots: dict[str, Path] = {
        "Synapse/Devices/DeathStalker Ultimate/Profiles": (
            razer / "Synapse" / "Devices" / "DeathStalker Ultimate" / "Profiles"
        ),
        "SwitchBlade/DeathStalker": razer / "SwitchBlade" / "DeathStalker",
        "SwitchBlade/Apps/Razer": razer / "SwitchBlade" / "Apps" / "Razer",
    }
    records = manifest["files"]
    needs_account = any(record["path"].startswith("data/" + _ACCOUNT_PREFIX) for record in records)
    if needs_account:
        accounts = razer / "Synapse" / "Accounts"
        account_dirs = [path for path in accounts.iterdir() if path.is_dir()] if accounts.is_dir() else []
        if len(account_dirs) != 1:
            raise RuntimeError(
                "Account-scoped backup data requires exactly one local Synapse account directory"
            )
        account = account_dirs[0]
        roots["Synapse/Accounts/User/Devices/DeathStalker Ultimate/Profiles"] = (
            account / "Devices" / "DeathStalker Ultimate" / "Profiles"
        )
        roots["Synapse/Accounts/User/Macros"] = account / "Macros"

    destinations: list[tuple[str, Path]] = []
    for record in records:
        member = record["path"]
        root, relative = _split_logical_path(member)
        destinations.append((member, roots[root].joinpath(*relative)))
    return destinations


def _journal_destination(member: str) -> str:
    # Logical destinations intentionally preserve the neutral User label.
    return member.removeprefix("data/")


def _append_journal(journal: Path, operation_id: str, event: str, archive: Path, **details) -> None:
    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "operation_id": operation_id,
        "event": event,
        # A basename identifies the input without leaking a Windows user profile path.
        "archive_path": Path(archive).name,
        **details,
    }
    with journal.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


def restore_backup(archive: Path, *, confirmed: bool = False) -> Path:
    """Validate and restore an owned backup, returning its JSONL journal."""
    if not confirmed:
        raise PermissionError("Restore requires explicit confirmation (--confirm)")
    running = _processes()
    if running:
        raise RuntimeError("Close RzSynapse, RzAppManager, and RzSBHelper before restore")

    archive = Path(archive)
    manifest = validate_backup(archive)
    destinations = _restore_destinations(manifest)
    operation_id = uuid.uuid4().hex
    JOURNALS_DIR.mkdir(parents=True, exist_ok=True)
    journal = JOURNALS_DIR / f"restore-{operation_id}.jsonl"
    _append_journal(journal, operation_id, "restore_started", archive)
    staging: Path | None = None
    try:
        pre_restore = create_backup(export_driver=False)
        _append_journal(
            journal,
            operation_id,
            "pre_restore_backup_created",
            archive,
            backup_path=pre_restore.name,
        )
        staging = Path(tempfile.mkdtemp(prefix=f"restore-{operation_id}-", dir=DATA_ROOT))
        with zipfile.ZipFile(archive, "r") as bundle:
            staged_files: dict[str, Path] = {}
            for index, (member, _destination) in enumerate(destinations):
                staged = staging / f"{index:08d}.stage"
                staged.write_bytes(bundle.read(member))
                staged_files[member] = staged

        for member, destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.parent / f".{destination.name}.{operation_id}.tmp"
            try:
                shutil.copyfile(staged_files[member], temporary)
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
            _append_journal(
                journal,
                operation_id,
                "file_restored",
                archive,
                logical_path=member,
                destination_path=_journal_destination(member),
            )
        _append_journal(journal, operation_id, "restore_completed", archive)
        return journal
    except Exception as exc:
        _append_journal(
            journal,
            operation_id,
            "restore_failed",
            archive,
            exception_type=type(exc).__name__,
            message="Restore failed; sensitive filesystem details were omitted",
        )
        raise
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def stop_legacy_processes() -> None:
    """Stop only the three known legacy processes for a consistent snapshot."""
    if os.name != "nt":
        return
    subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-Process -Name RzSynapse,RzAppManager,RzSBHelper -ErrorAction SilentlyContinue | Stop-Process -Force",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )


def create_backup(*, export_driver: bool = True, allow_live: bool = False) -> Path:
    running = _processes()
    if running and not allow_live:
        raise RuntimeError(
            "Close the legacy Razer processes before backup, or explicitly use --live. "
            f"Running: {', '.join(running)}"
        )
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = BACKUPS_DIR / f"legacy-config-{stamp}.zip"
    manifest: dict = {
        "format": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "unofficial": True,
        "mi03_driver": get_mi03_driver(),
        "files": [],
        "excluded": ["credentials", "RazerLoginData.xml", "analytics", "logs", "installed binaries"],
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        seen: set[str] = set()
        for source, logical_root in _backup_candidates():
            for item in _iter_backup_files(source):
                relative = item.relative_to(source).as_posix()
                archive_name = f"data/{logical_root}/{relative}"
                if archive_name in seen:
                    continue
                seen.add(archive_name)
                content = item.read_bytes()
                bundle.writestr(archive_name, content)
                manifest["files"].append(
                    {"path": archive_name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                )
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    # Driver export is intentionally separate from the ZIP: it is a local rollback
    # copy of the user's installed proprietary package and is never distributed.
    driver = manifest.get("mi03_driver") or {}
    inf = driver.get("InfName")
    if export_driver and inf:
        driver_dir = BACKUPS_DIR / f"driver-{stamp}"
        driver_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["pnputil", "/export-driver", inf, str(driver_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "driver export failed")
        (driver_dir / "export-metadata.json").write_text(
            json.dumps({"driver": driver, "exported_utc": datetime.now(timezone.utc).isoformat()}, indent=2, default=str),
            encoding="utf-8",
        )
    return archive


def _window_visible(title: str) -> bool:
    if os.name != "nt":
        return False
    found = False
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        nonlocal found
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length:
            text = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, text, length + 1)
            if text.value == title and ctypes.windll.user32.IsWindowVisible(hwnd):
                found = True
                return False
        return True

    ctypes.windll.user32.EnumWindows(enum_proc(callback), 0)
    return found


def launch_configurator(timeout: float = 15.0) -> bool:
    if not SYNAPSE_EXE.is_file():
        raise FileNotFoundError(f"Razer Synapse is not installed at {SYNAPSE_EXE}")
    subprocess.Popen(
        [str(SYNAPSE_EXE), "-launch"],
        cwd=str(SYNAPSE_EXE.parent),
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _window_visible("Razer Configurator"):
            return True
        time.sleep(0.25)
    return False


def write_report(status: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"diagnostic-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(status, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scan", help="Read-only compatibility inventory")
    commands.add_parser("launch", help="Open the original Razer Configurator correctly")
    backup = commands.add_parser("backup", help="Back up profiles and the current MI_03 driver")
    backup.add_argument("--no-driver", action="store_true")
    backup.add_argument("--live", action="store_true", help="allow a potentially inconsistent backup while Razer processes run")
    restore = commands.add_parser("restore", help="Validate and restore a legacy configuration backup")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--confirm", action="store_true", help="confirm that the validated backup should be restored")
    commands.add_parser("repair", help="Back up, validate, and launch without redistributing Razer files")
    args = parser.parse_args()

    if args.command == "scan":
        status = scan()
        report = write_report(status)
        print(json.dumps(status, indent=2, default=str))
        print(f"Report: {report}")
        return 0 if status["ready"] else 1
    if args.command == "launch":
        ok = launch_configurator()
        print("Razer Configurator opened." if ok else "Razer Configurator did not appear.")
        return 0 if ok else 1
    if args.command == "backup":
        path = create_backup(export_driver=not args.no_driver, allow_live=args.live)
        print(path)
        return 0
    if args.command == "restore":
        if not args.confirm:
            parser.error("restore requires --confirm; no files were changed")
        print(restore_backup(args.archive, confirmed=True))
        return 0
    if args.command == "repair":
        status = scan()
        stop_legacy_processes()
        backup_path = create_backup(export_driver=True)
        if not status["ready"]:
            print(json.dumps(status, indent=2, default=str))
            print("The installed stack is incomplete or MI_03 is not on the Razer driver; no automatic system changes were made.")
            print(f"Backup: {backup_path}")
            return 1
        opened = launch_configurator()
        print(f"Backup: {backup_path}")
        print("Compatibility launch succeeded." if opened else "Installed components passed, but the window did not appear.")
        return 0 if opened else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
