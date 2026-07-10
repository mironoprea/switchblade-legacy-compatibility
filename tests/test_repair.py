from __future__ import annotations

from pathlib import Path
import sys

import pytest

from app import repair
from app import legacy_compat as legacy


def _action() -> repair.RepairAction:
    return repair.RepairAction("repair_sdk", "switchblade_sdk", "Razer SDK package v1", ("verified-installer", "/repair"), "sdk_present", "restore pre-action backup")


def _dependencies(events: list[tuple[str, dict]], *, post="healthy", launch=True, fail_action=False):
    def run_action(_action):
        if fail_action:
            raise RuntimeError("private path")
    return repair.RepairDependencies(
        create_backup=lambda **_kwargs: Path("C:/private/backup.zip"),
        stop_processes=lambda: events.append(("stopped", {})),
        launch_configurator=lambda: launch,
        rerun_inventory=lambda: {"classification": post},
        run_action=run_action,
        journal=lambda event, fields: events.append((event, fields)),
    )


def test_healthy_plan_is_a_noop() -> None:
    plan = repair.build_plan({"classification": "healthy", "reason_codes": []})
    assert plan.actions == ()
    assert repair.execute_plan(plan, confirmed=True, dependencies=_dependencies([]))["outcome"] == "blocked"


def test_repairable_without_verified_component_is_blocked() -> None:
    plan = repair.build_plan({"classification": "repairable", "reason_codes": ["missing_sdk"]})
    assert plan.classification == "blocked"
    assert "official_component_identity_unverified" in plan.reason_codes


def test_declined_confirmation_cannot_touch_any_boundary() -> None:
    events: list[tuple[str, dict]] = []
    plan = repair.build_plan({"classification": "repairable"}, [_action()])
    assert repair.execute_plan(plan, confirmed=False, dependencies=_dependencies(events))["outcome"] == "dry_run"
    assert events == []


@pytest.mark.parametrize("post,launch,fail_action,outcome", [("blocked", True, False, "postcondition_failed"), ("healthy", False, False, "launch_failed"), ("healthy", True, True, "action_failed")])
def test_failures_offer_sanitized_recovery(post, launch, fail_action, outcome) -> None:
    events: list[tuple[str, dict]] = []
    plan = repair.build_plan({"classification": "repairable"}, [_action()])
    result = repair.execute_plan(plan, confirmed=True, dependencies=_dependencies(events, post=post, launch=launch, fail_action=fail_action))
    assert result["outcome"] == outcome
    assert result["recovery_command"] == "switchblade-legacy restore backup.zip --confirm"
    assert "private" not in str(events)


def test_backup_failure_does_not_stop_processes() -> None:
    events: list[tuple[str, dict]] = []
    dependencies = _dependencies(events)
    dependencies.create_backup = lambda **_kwargs: (_ for _ in ()).throw(OSError("private"))
    plan = repair.build_plan({"classification": "repairable"}, [_action()])
    assert repair.execute_plan(plan, confirmed=True, dependencies=dependencies)["outcome"] == "backup_failed"
    assert not any(event == "stopped" for event, _ in events)


@pytest.mark.parametrize("command", [("pnputil", "/add-driver"), ("devcon", "install"), ("powershell", "WinUSB")])
def test_forbidden_command_families_cannot_enter_plan(command) -> None:
    unsafe = repair.RepairAction("unsafe", "component", "identity", command, "ok", "recover")
    with pytest.raises(ValueError, match="forbidden"):
        repair.build_plan({"classification": "repairable"}, [unsafe])


def test_successful_transaction_becomes_idempotent_after_reinventory() -> None:
    events: list[tuple[str, dict]] = []
    plan = repair.build_plan({"classification": "repairable"}, [_action()])
    result = repair.execute_plan(plan, confirmed=True, dependencies=_dependencies(events))
    assert result["outcome"] == "completed"
    assert repair.build_plan({"classification": "healthy"}).actions == ()
    assert "repair_completed" in [event for event, _ in events]


def test_cli_dry_run_never_calls_mutation_boundaries(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    status = {"classification": "repairable", "reason_codes": ["missing_sdk"], "next_steps": []}
    monkeypatch.setattr(legacy, "scan", lambda: status)
    monkeypatch.setattr(legacy, "write_report", lambda _status: Path("report.json"))
    monkeypatch.setattr(legacy, "_repair_journal", lambda _plan: (Path("journal.jsonl"), lambda *_args: None))
    monkeypatch.setattr(legacy, "create_backup", lambda **_kwargs: pytest.fail("must not back up"))
    monkeypatch.setattr(sys, "argv", ["switchblade-legacy", "repair"])

    assert legacy.main() == 3
    assert "Dry run only" in capsys.readouterr().out


def test_repair_journal_drops_private_paths_and_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(legacy, "JOURNALS_DIR", tmp_path)
    path, append = legacy._repair_journal(repair.build_plan({"classification": "repairable"}, [_action()]))
    append("repair_action_failed", {"exception_type": "OSError", "path": r"C:\\Users\\alice", "command": "secret"})

    text = path.read_text(encoding="utf-8")
    assert "alice" not in text and "secret" not in text
    assert "repair_plan_created" in text and "repair_action_failed" in text
