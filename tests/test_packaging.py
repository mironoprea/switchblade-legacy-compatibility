from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_installer_preserves_user_data_and_razer_files() -> None:
    script = (ROOT / "installer" / "SwitchbladeLegacyCompatibility.iss").read_text(encoding="utf-8")
    assert "DisableDirPage=no" in script
    assert "{localappdata}\\SwitchbladeLegacyCompatibility" not in script
    assert "[UninstallDelete]" not in script
    assert "Razer" not in script


def test_package_script_only_collects_owned_application_files() -> None:
    script = (ROOT / "scripts" / "package_smoke.ps1").read_text(encoding="utf-8")
    assert "pyinstaller" in script
    assert "--onefile" in script
    assert "--collect-all app" in script
    assert "Razer" not in script
    assert "drivers" not in script.casefold()
