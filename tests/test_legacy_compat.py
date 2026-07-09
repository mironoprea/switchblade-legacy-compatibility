from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from app import legacy_compat as legacy


DEVICE_MEMBER = "data/Synapse/Devices/DeathStalker Ultimate/Profiles/profile.xml"
ACCOUNT_MEMBER = "data/Synapse/Accounts/User/Macros/macro.xml"


def _record(path: str, content: bytes) -> dict:
    return {"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _archive(
    path: Path,
    files: dict[str, bytes] | None = None,
    *,
    manifest: object | None = None,
    extras: dict[str, bytes] | None = None,
) -> Path:
    files = files or {}
    if manifest is None:
        manifest = {"format": 1, "files": [_record(name, content) for name, content in files.items()]}
    with zipfile.ZipFile(path, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
        for name, content in (extras or {}).items():
            bundle.writestr(name, content)
        bundle.writestr("manifest.json", json.dumps(manifest))
    return path


def _restore_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    program_data = tmp_path / "program-data"
    data_root = tmp_path / "utility-data"
    monkeypatch.setattr(legacy, "PROGRAM_DATA", program_data)
    monkeypatch.setattr(legacy, "DATA_ROOT", data_root)
    monkeypatch.setattr(legacy, "JOURNALS_DIR", data_root / "Journals")
    monkeypatch.setattr(legacy, "_processes", lambda: [])
    return program_data, data_root


def _backup_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    program_data = tmp_path / "program-data"
    data_root = tmp_path / "utility-data"
    monkeypatch.setattr(legacy, "PROGRAM_DATA", program_data)
    monkeypatch.setattr(legacy, "DATA_ROOT", data_root)
    monkeypatch.setattr(legacy, "BACKUPS_DIR", data_root / "Backups")
    monkeypatch.setattr(legacy, "REPORTS_DIR", data_root / "Reports")
    monkeypatch.setattr(legacy, "_processes", lambda: [])
    monkeypatch.setattr(legacy, "get_mi03_driver", lambda: None)
    return program_data, data_root


def test_validate_backup_accepts_valid_archive(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "valid.zip", {DEVICE_MEMBER: b"profile"})

    manifest = legacy.validate_backup(archive)

    assert manifest["format"] == 1
    assert manifest["files"][0]["path"] == DEVICE_MEMBER


@pytest.mark.parametrize(
    "writer",
    [
        lambda bundle: bundle.writestr("other.json", "{}"),
        lambda bundle: bundle.writestr("manifest.json", "not-json"),
        lambda bundle: bundle.writestr("manifest.json", json.dumps({"format": 2, "files": []})),
        lambda bundle: bundle.writestr("manifest.json", json.dumps({"format": 1, "files": {}})),
    ],
)
def test_validate_backup_rejects_missing_or_malformed_manifest(tmp_path: Path, writer) -> None:
    archive = tmp_path / "bad-manifest.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        writer(bundle)

    with pytest.raises(ValueError):
        legacy.validate_backup(archive)


def test_validate_backup_rejects_duplicate_member(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    content = b"x"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(DEVICE_MEMBER, content)
            bundle.writestr(DEVICE_MEMBER, content)
            bundle.writestr(
                "manifest.json",
                json.dumps({"format": 1, "files": [_record(DEVICE_MEMBER, content)]}),
            )

    with pytest.raises(ValueError, match="duplicate"):
        legacy.validate_backup(archive)


def test_validate_backup_rejects_case_insensitive_duplicate_members(tmp_path: Path) -> None:
    case_variant = DEVICE_MEMBER.replace("profile.xml", "PROFILE.XML")
    archive = tmp_path / "case-duplicate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(DEVICE_MEMBER, b"one")
        bundle.writestr(case_variant, b"two")
        bundle.writestr(
            "manifest.json",
            json.dumps({"format": 1, "files": [_record(DEVICE_MEMBER, b"one")]}),
        )

    with pytest.raises(ValueError, match="case-insensitive duplicate"):
        legacy.validate_backup(archive)


@pytest.mark.parametrize(
    "limit_name,limit_value,files,error",
    [
        ("MAX_ZIP_MEMBERS", 1, {DEVICE_MEMBER: b"x"}, "member-count"),
        ("MAX_MANIFEST_SIZE", 1, {DEVICE_MEMBER: b"x"}, "manifest"),
        ("MAX_EXPANDED_FILE_SIZE", 3, {DEVICE_MEMBER: b"four"}, "expanded-size"),
        (
            "MAX_TOTAL_EXPANDED_SIZE",
            5,
            {DEVICE_MEMBER: b"one", "data/SwitchBlade/DeathStalker/second.xml": b"two"},
            "total expanded-size",
        ),
    ],
)
def test_validate_backup_enforces_resource_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    limit_name: str,
    limit_value: int,
    files: dict[str, bytes],
    error: str,
) -> None:
    archive = _archive(tmp_path / f"{limit_name}.zip", files)
    monkeypatch.setattr(legacy, limit_name, limit_value)

    with pytest.raises(ValueError, match=error):
        legacy.validate_backup(archive)


def test_validate_backup_rejects_excessive_compression_ratio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    content = b"A" * 10_000
    archive = tmp_path / "ratio.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(DEVICE_MEMBER, content)
        bundle.writestr(
            "manifest.json",
            json.dumps({"format": 1, "files": [_record(DEVICE_MEMBER, content)]}),
        )
    monkeypatch.setattr(legacy, "MAX_COMPRESSION_RATIO", 2)

    with pytest.raises(ValueError, match="compression-ratio"):
        legacy.validate_backup(archive)


@pytest.mark.parametrize(
    "unsafe",
    [
        "/data/SwitchBlade/DeathStalker/config.xml",
        "C:/data/SwitchBlade/DeathStalker/config.xml",
        "data\\SwitchBlade\\DeathStalker\\config.xml",
        "data/SwitchBlade//DeathStalker/config.xml",
        "data/SwitchBlade/../DeathStalker/config.xml",
    ],
)
def test_validate_backup_rejects_unsafe_paths(tmp_path: Path, unsafe: str) -> None:
    archive = _archive(tmp_path / "unsafe.zip", {unsafe: b"x"})

    with pytest.raises(ValueError):
        legacy.validate_backup(archive)


def test_validate_backup_rejects_undeclared_data_member(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "undeclared.zip",
        {DEVICE_MEMBER: b"declared"},
        extras={"data/SwitchBlade/DeathStalker/config.xml": b"undeclared"},
    )

    with pytest.raises(ValueError, match="undeclared"):
        legacy.validate_backup(archive)


@pytest.mark.parametrize(
    "member",
    [
        "data/SwitchBlade/DeathStalker/tool.exe",
        "data/SwitchBlade/DeathStalker/library.dll",
        "data/SwitchBlade/DeathStalker/RazerLoginData.xml",
        "data/SwitchBlade/DeathStalker/logs/trace.xml",
        "data/SwitchBlade/DeathStalker/analytics/event.xml",
    ],
)
def test_validate_backup_enforces_restore_allowlist(tmp_path: Path, member: str) -> None:
    archive = _archive(tmp_path / "disallowed.zip", {member: b"unsafe"})

    with pytest.raises(ValueError, match="allowlist"):
        legacy.validate_backup(archive)


@pytest.mark.parametrize("field,value", [("size", 100), ("sha256", "0" * 64)])
def test_validate_backup_rejects_size_or_digest_mismatch(tmp_path: Path, field: str, value) -> None:
    content = b"content"
    record = _record(DEVICE_MEMBER, content)
    record[field] = value
    archive = _archive(
        tmp_path / f"bad-{field}.zip",
        {DEVICE_MEMBER: content},
        manifest={"format": 1, "files": [record]},
    )

    with pytest.raises(ValueError):
        legacy.validate_backup(archive)


def test_restore_requires_confirmation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(legacy, "validate_backup", lambda _archive: pytest.fail("validation must not run"))

    with pytest.raises(PermissionError, match="confirmation"):
        legacy.restore_backup(tmp_path / "anything.zip")


def test_restore_refuses_while_legacy_process_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(legacy, "_processes", lambda: ["RzSynapse"])
    monkeypatch.setattr(legacy, "validate_backup", lambda _archive: pytest.fail("validation must not run"))

    with pytest.raises(RuntimeError, match="Close RzSynapse"):
        legacy.restore_backup(tmp_path / "anything.zip", confirmed=True)


@pytest.mark.parametrize("account_count", [0, 2])
def test_account_restore_requires_exactly_one_local_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, account_count: int
) -> None:
    program_data, data_root = _restore_environment(monkeypatch, tmp_path)
    accounts = program_data / "Razer" / "Synapse" / "Accounts"
    for index in range(account_count):
        (accounts / f"account-{index}").mkdir(parents=True)
    archive = _archive(tmp_path / "account.zip", {ACCOUNT_MEMBER: b"macro"})
    monkeypatch.setattr(legacy, "create_backup", lambda **_kwargs: pytest.fail("backup must not run"))

    with pytest.raises(RuntimeError, match="exactly one"):
        legacy.restore_backup(archive, confirmed=True)

    assert not data_root.exists()


def test_restore_destinations_reject_windows_case_collision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(legacy, "PROGRAM_DATA", tmp_path)
    case_variant = DEVICE_MEMBER.replace("profile.xml", "PROFILE.XML")
    manifest = {"format": 1, "files": [_record(DEVICE_MEMBER, b"one"), _record(case_variant, b"two")]}

    with pytest.raises(ValueError, match="Windows destination"):
        legacy._restore_destinations(manifest)


def test_restore_rejects_reparse_point_in_destination_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_data, data_root = _restore_environment(monkeypatch, tmp_path)
    archive = _archive(tmp_path / "restore.zip", {DEVICE_MEMBER: b"profile"})
    blocked = program_data / "Razer" / "Synapse"
    monkeypatch.setattr(legacy, "_is_reparse_point", lambda path: path == blocked)
    blocked.mkdir(parents=True)
    monkeypatch.setattr(legacy, "create_backup", lambda **_kwargs: pytest.fail("backup must not run"))

    with pytest.raises(RuntimeError, match="reparse point"):
        legacy.restore_backup(archive, confirmed=True)

    assert not data_root.exists()


def test_pre_restore_backup_failure_changes_no_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_data, _data_root = _restore_environment(monkeypatch, tmp_path)
    destination = (
        program_data
        / "Razer"
        / "Synapse"
        / "Devices"
        / "DeathStalker Ultimate"
        / "Profiles"
        / "profile.xml"
    )
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"original")
    archive = _archive(tmp_path / "restore.zip", {DEVICE_MEMBER: b"replacement"})

    def fail_backup(**_kwargs):
        raise OSError("backup unavailable")

    monkeypatch.setattr(legacy, "create_backup", fail_backup)

    with pytest.raises(OSError, match="backup unavailable"):
        legacy.restore_backup(archive, confirmed=True)

    assert destination.read_bytes() == b"original"


def test_successful_restore_writes_declared_files_and_safe_journal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_data, data_root = _restore_environment(monkeypatch, tmp_path)
    real_account = program_data / "Razer" / "Synapse" / "Accounts" / "private-account-name"
    real_account.mkdir(parents=True)
    unrelated = program_data / "Razer" / "SwitchBlade" / "DeathStalker" / "unrelated.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")
    archive = _archive(
        tmp_path / "restore.zip",
        {DEVICE_MEMBER: b"profile", ACCOUNT_MEMBER: b"macro"},
    )
    pre_restore = data_root / "Backups" / "before.zip"
    monkeypatch.setattr(legacy, "create_backup", lambda *, export_driver: pre_restore)

    journal = legacy.restore_backup(archive, confirmed=True)

    device = (
        program_data / "Razer" / "Synapse" / "Devices" / "DeathStalker Ultimate" / "Profiles" / "profile.xml"
    )
    assert device.read_bytes() == b"profile"
    assert (real_account / "Macros" / "macro.xml").read_bytes() == b"macro"
    assert unrelated.read_text(encoding="utf-8") == "keep"
    entries = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [entry["event"] for entry in entries] == [
        "restore_started",
        "pre_restore_backup_created",
        "file_restored",
        "file_restored",
        "restore_completed",
    ]
    assert all(entry["operation_id"] == entries[0]["operation_id"] for entry in entries)
    assert "private-account-name" not in journal.read_text(encoding="utf-8")
    assert all(entry["archive_path"] == "restore.zip" for entry in entries)


def test_mid_restore_failure_rolls_back_existing_and_new_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_data, data_root = _restore_environment(monkeypatch, tmp_path)
    unrelated = program_data / "Razer" / "SwitchBlade" / "DeathStalker" / "unrelated.xml"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"keep")
    original = (
        program_data
        / "Razer"
        / "Synapse"
        / "Devices"
        / "DeathStalker Ultimate"
        / "Profiles"
        / "profile.xml"
    )
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    second = "data/SwitchBlade/DeathStalker/second.xml"
    third = "data/SwitchBlade/DeathStalker/third.xml"
    second_destination = program_data / "Razer" / "SwitchBlade" / "DeathStalker" / "second.xml"
    archive = _archive(
        tmp_path / "restore.zip",
        {DEVICE_MEMBER: b"one", second: b"two", third: b"three"},
    )
    monkeypatch.setattr(
        legacy,
        "create_backup",
        lambda *, export_driver: data_root / "Backups" / "before.zip",
    )
    real_replace = legacy.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("simulated replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(legacy.os, "replace", fail_second)

    with pytest.raises(OSError, match="simulated"):
        legacy.restore_backup(archive, confirmed=True)

    assert original.read_bytes() == b"original"
    assert not second_destination.exists()
    assert unrelated.read_bytes() == b"keep"
    journals = list((data_root / "Journals").glob("*.jsonl"))
    assert len(journals) == 1
    entries = [json.loads(line) for line in journals[0].read_text(encoding="utf-8").splitlines()]
    assert [entry["event"] for entry in entries[-5:]] == [
        "rollback_started",
        "file_rollback_succeeded",
        "file_rollback_succeeded",
        "rollback_completed",
        "restore_failed",
    ]
    assert entries[-1]["exception_type"] == "OSError"
    assert "simulated replacement failure" not in entries[-1]["message"]
    assert str(program_data) not in journals[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("account_count", [0, 1])
def test_backup_accepts_zero_or_one_account_with_eligible_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, account_count: int
) -> None:
    program_data, _data_root = _backup_environment(monkeypatch, tmp_path)
    accounts = program_data / "Razer" / "Synapse" / "Accounts"
    for index in range(account_count):
        macros = accounts / f"private-{index}" / "Macros"
        macros.mkdir(parents=True)
        (macros / "same.xml").write_bytes(b"macro")

    archive = legacy.create_backup(export_driver=False)

    manifest = legacy.validate_backup(archive)
    assert len(manifest["files"]) == account_count
    assert all("private-" not in record["path"] for record in manifest["files"])


def test_backup_refuses_multiple_accounts_with_overlapping_eligible_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_data, data_root = _backup_environment(monkeypatch, tmp_path)
    accounts = program_data / "Razer" / "Synapse" / "Accounts"
    for index in range(2):
        macros = accounts / f"private-{index}" / "Macros"
        macros.mkdir(parents=True)
        (macros / "same.xml").write_bytes(f"macro-{index}".encode())

    with pytest.raises(RuntimeError, match="more than one Synapse account"):
        legacy.create_backup(export_driver=False)

    assert list((data_root / "Backups").glob("*.zip")) == []


def test_artifacts_do_not_collide_when_created_at_the_same_instant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _program_data, data_root = _backup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(legacy, "JOURNALS_DIR", data_root / "Journals")

    backups = [legacy.create_backup(export_driver=False) for _ in range(2)]
    reports = [legacy.write_report({"ready": False}) for _ in range(2)]
    journals = [legacy._reserve_artifact_file(legacy.JOURNALS_DIR, "restore", ".jsonl") for _ in range(2)]

    assert len(set(backups)) == len(set(reports)) == len(set(journals)) == 2
    assert all(path.exists() for path in backups + reports + journals)


def test_artifact_reservation_never_overwrites_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tokens = iter(["collision", "unique"])
    monkeypatch.setattr(legacy, "_artifact_token", lambda: next(tokens))
    existing = tmp_path / "artifact-collision.json"
    existing.write_text("keep", encoding="utf-8")

    reserved = legacy._reserve_artifact_file(tmp_path, "artifact", ".json")

    assert existing.read_text(encoding="utf-8") == "keep"
    assert reserved.name == "artifact-unique.json"


def test_driver_export_directories_do_not_collide(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _program_data, data_root = _backup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(legacy, "get_mi03_driver", lambda: {"InfName": "razer.inf"})
    exported: list[Path] = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(command, **_kwargs):
        exported.append(Path(command[-1]))
        return Result()

    monkeypatch.setattr(legacy.subprocess, "run", fake_run)

    legacy.create_backup(export_driver=True)
    legacy.create_backup(export_driver=True)

    assert len(set(exported)) == 2
    assert all(path.parent == data_root / "Backups" for path in exported)


def test_cli_restore_requires_confirm(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["switchblade-legacy", "restore", "backup.zip"])
    monkeypatch.setattr(legacy, "restore_backup", lambda *_args, **_kwargs: pytest.fail("must not restore"))

    with pytest.raises(SystemExit) as exc:
        legacy.main()

    assert exc.value.code != 0
    assert "requires --confirm" in capsys.readouterr().err


def test_cli_restore_prints_journal_path(monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path) -> None:
    journal = tmp_path / "restore.jsonl"
    called = {}

    def fake_restore(archive: Path, *, confirmed: bool) -> Path:
        called.update(archive=archive, confirmed=confirmed)
        return journal

    monkeypatch.setattr(sys, "argv", ["switchblade-legacy", "restore", "backup.zip", "--confirm"])
    monkeypatch.setattr(legacy, "restore_backup", fake_restore)

    assert legacy.main() == 0
    assert called == {"archive": Path("backup.zip"), "confirmed": True}
    assert str(journal) in capsys.readouterr().out
