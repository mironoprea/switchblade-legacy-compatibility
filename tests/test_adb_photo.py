from pathlib import Path

from tools import adb_photo


def test_latest_camera_file_returns_first_nonempty(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = "\nIMG_new.jpg\nIMG_old.jpg\n"

    monkeypatch.setattr(adb_photo, "run_adb", lambda *a, **k: _Proc())

    assert adb_photo.latest_camera_file("adb") == "IMG_new.jpg"


def test_latest_camera_file_skips_thumbnail_sidecars(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = "IMG_new.thumb.jpg\nIMG_new.jpg\n"

    monkeypatch.setattr(adb_photo, "run_adb", lambda *a, **k: _Proc())

    assert adb_photo.latest_camera_file("adb") == "IMG_new.jpg"


def test_resolve_adb_uses_explicit_path():
    assert adb_photo.resolve_adb("C:/tools/adb.exe") == "C:/tools/adb.exe"


def test_capture_photo_pulls_new_file(monkeypatch, tmp_path):
    calls = []
    latest = iter(["IMG_old.jpg", "IMG_new.jpg"])

    def fake_latest(adb, *, camera_dir):
        return next(latest)

    def fake_run(adb, args, *, check=True):
        calls.append(args)

        class _Proc:
            returncode = 0
            stdout = ""

        return _Proc()

    monkeypatch.setattr(adb_photo, "latest_camera_file", fake_latest)
    monkeypatch.setattr(adb_photo, "run_adb", fake_run)
    monkeypatch.setattr(adb_photo.time, "sleep", lambda seconds: None)

    output = adb_photo.capture_photo(
        "adb",
        output=tmp_path / "keyboard.jpg",
        settle_seconds=0,
    )

    assert output == tmp_path / "keyboard.jpg"
    assert ["shell", "input", "keyevent", "KEYCODE_CAMERA"] in calls
    assert ["pull", "/sdcard/DCIM/Camera/IMG_new.jpg", str(Path(output))] in calls
