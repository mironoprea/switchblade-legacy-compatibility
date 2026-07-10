from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import inventory
from app import legacy_compat as legacy


FIXTURES = Path(__file__).parent / "fixtures" / "inventory"


@pytest.mark.parametrize(
    ("fixture", "classification", "reason"),
    [
        ("healthy", "healthy", None), ("repairable", "repairable", "missing_app_manager"),
        ("winusb", "blocked", "mi03_winusb_bound"), ("missing-device", "blocked", "device_missing"),
        ("unsupported", "unsupported", "unsupported_os"), ("ambiguous", "blocked", "mi03_ambiguous"),
    ],
)
def test_classifies_sanitized_fixtures(fixture: str, classification: str, reason: str | None) -> None:
    evidence = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    result = inventory.classify(evidence)
    assert result["classification"] == classification
    if reason:
        assert reason in result["reason_codes"]


@pytest.mark.parametrize("provider", ["Razer Inc", " RAZER  INC. ", "Razer Incorporated"])
def test_provider_variations_are_evidence_based(provider: str) -> None:
    evidence = json.loads((FIXTURES / "healthy.json").read_text(encoding="utf-8"))
    evidence["drivers"][0]["DriverProviderName"] = provider
    assert inventory.classify(evidence)["classification"] == "healthy"


def test_requires_signed_provider_and_expected_driver_evidence() -> None:
    evidence = json.loads((FIXTURES / "healthy.json").read_text(encoding="utf-8"))
    evidence["drivers"][0].update({"IsSigned": False, "InfName": "oem42.inf"})
    result = inventory.classify(evidence)
    assert result["classification"] == "blocked"
    assert result["reason_codes"] == ["mi03_driver_unverified"]


def test_collection_handles_powershell_failure_and_malformed_output(tmp_path: Path) -> None:
    def failing(_script: str):
        raise RuntimeError("private command output")

    evidence = inventory.collect_evidence(
        razer_root=tmp_path, program_data=tmp_path, powershell_json=failing, is_windows=True
    )
    assert inventory.classify(evidence)["reason_codes"] == ["windows_query_failed"]


def test_private_report_is_allowlisted() -> None:
    evidence = json.loads((FIXTURES / "healthy.json").read_text(encoding="utf-8"))
    evidence["packages"] = [r"C:\\Users\\alice\\secret-Razer.exe"]
    evidence["drivers"][0]["SerialNumber"] = "private"
    report = inventory.public_report(evidence, inventory.classify(evidence))
    text = json.dumps(report)
    assert "alice" not in text and "secret" not in text and "private" not in text
    assert report["official_package_candidates"] == 1


def test_package_filter_and_exit_codes_are_stable() -> None:
    evidence = json.loads((FIXTURES / "repairable.json").read_text(encoding="utf-8"))
    evidence["packages"] = ["unrelated.exe", "Razer.txt", "Razer_Official.MSI"]
    result = inventory.classify(evidence)
    assert result["classification"] == "repairable"
    assert inventory.EXIT_CODES[result["classification"]] == 2


def test_write_report_drops_unapproved_private_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(legacy, "REPORTS_DIR", tmp_path)
    report = legacy.write_report(
        {"classification": "blocked", "reason_codes": ["device_missing"], "user_path": r"C:\\Users\\alice"}
    )
    text = report.read_text(encoding="utf-8")
    assert "alice" not in text
    assert json.loads(text)["classification"] == "blocked"
