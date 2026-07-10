"""Bounded repair planning and execution.

The inventory layer intentionally reports package candidates without paths or
trust assertions.  Until a future adapter can prove an exact official component
and its supported repair semantics, this module produces a blocked plan rather
than guessing an installer command.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence


FORBIDDEN_COMMAND_TOKENS = (
    "pnputil", "add-driver", "devcon", "winusb", "libusb", "hid", "remove-item",
    "del ", "rd ", "rmdir", "format ", "cmd.exe", "powershell",
)


@dataclass(frozen=True)
class RepairAction:
    """A pre-approved action supplied only by a verified component adapter."""

    action_id: str
    component_id: str
    executable_identity: str
    command: tuple[str, ...]
    postcondition: str
    rollback_command: str
    requires_process_shutdown: bool = True


# There are intentionally no production actions yet. Gate 2 does not provide a
# verified installer identity or documented repair invocation to allowlist.
ACTION_REGISTRY: tuple[RepairAction, ...] = ()


@dataclass(frozen=True)
class RepairPlan:
    classification: str
    reason_codes: tuple[str, ...]
    actions: tuple[RepairAction, ...]
    manual_guidance: tuple[str, ...]

    @property
    def requires_process_shutdown(self) -> bool:
        return any(action.requires_process_shutdown for action in self.actions)

    def public(self) -> dict[str, object]:
        return {
            "classification": self.classification,
            "reason_codes": list(self.reason_codes),
            "actions": [asdict(action) for action in self.actions],
            "manual_guidance": list(self.manual_guidance),
            "requires_process_shutdown": self.requires_process_shutdown,
        }


@dataclass
class RepairDependencies:
    create_backup: Callable[..., Path]
    stop_processes: Callable[[], None]
    launch_configurator: Callable[[], bool]
    rerun_inventory: Callable[[], dict[str, object]]
    run_action: Callable[[RepairAction], None]
    journal: Callable[[str, dict[str, object]], None]


def _validate_action(action: RepairAction) -> None:
    command_text = " ".join(action.command).casefold()
    if not action.action_id or not action.component_id or not action.executable_identity or not action.command:
        raise ValueError("Repair actions require complete, exact component identity")
    if any(token in command_text for token in FORBIDDEN_COMMAND_TOKENS):
        raise ValueError("Repair action contains a forbidden command family")


def build_plan(status: dict[str, object], action_registry: Sequence[RepairAction] = ACTION_REGISTRY) -> RepairPlan:
    """Return a complete immutable plan without inspecting or changing the system."""
    classification = str(status.get("classification", "blocked"))
    reasons = tuple(str(reason) for reason in status.get("reason_codes", ()))
    for action in action_registry:
        _validate_action(action)

    if classification == "healthy":
        return RepairPlan("healthy", reasons, (), ("No repair action is needed.",))
    if classification != "repairable":
        return RepairPlan(classification, reasons, (), tuple(str(step) for step in status.get("next_steps", ())))
    if not action_registry:
        return RepairPlan(
            "blocked",
            reasons + ("official_component_identity_unverified",),
            (),
            (
                "No automatic repair is available because the local package identity and repair semantics are unverified.",
                "Use the original Razer installer or support guidance, then run scan again.",
            ),
        )
    return RepairPlan("repairable", reasons, tuple(action_registry), ())


def execute_plan(plan: RepairPlan, *, confirmed: bool, dependencies: RepairDependencies) -> dict[str, object]:
    """Execute an already printed plan, with backup, recovery, and re-inventory."""
    if not confirmed:
        return {"outcome": "dry_run", "mutated": False}
    if plan.classification != "repairable" or not plan.actions:
        return {"outcome": "blocked", "mutated": False}

    dependencies.journal("repair_started", {"action_ids": [action.action_id for action in plan.actions]})
    try:
        # Snapshot before stopping processes or starting any component action.
        backup = dependencies.create_backup(export_driver=True, allow_live=True)
    except Exception as exc:
        dependencies.journal("repair_backup_failed", {"exception_type": type(exc).__name__})
        return {"outcome": "backup_failed", "mutated": False}

    stopped = False
    try:
        if plan.requires_process_shutdown:
            dependencies.stop_processes()
            stopped = True
            dependencies.journal("repair_processes_stopped", {})
        for action in plan.actions:
            dependencies.journal("repair_action_started", {"action_id": action.action_id})
            dependencies.run_action(action)
            dependencies.journal("repair_action_completed", {"action_id": action.action_id})
        post_status = dependencies.rerun_inventory()
        if post_status.get("classification") != "healthy":
            dependencies.journal("repair_postcondition_failed", {"classification": str(post_status.get("classification"))})
            return _recover(dependencies, backup, "postcondition_failed", stopped)
        if not dependencies.launch_configurator():
            dependencies.journal("repair_launch_failed", {})
            return _recover(dependencies, backup, "launch_failed", stopped)
        dependencies.journal("repair_completed", {})
        return {"outcome": "completed", "mutated": True}
    except Exception as exc:
        dependencies.journal("repair_action_failed", {"exception_type": type(exc).__name__})
        return _recover(dependencies, backup, "action_failed", stopped)


def _recover(dependencies: RepairDependencies, backup: Path, outcome: str, stopped: bool) -> dict[str, object]:
    """Give one actionable recovery command and relaunch only after process shutdown."""
    recovery = f"switchblade-legacy restore {backup.name} --confirm"
    dependencies.journal("repair_recovery_available", {"recovery": "restore_pre_action_backup"})
    relaunched = False
    if stopped:
        try:
            relaunched = dependencies.launch_configurator()
        except Exception:
            relaunched = False
    return {"outcome": outcome, "mutated": True, "recovery_command": recovery, "relaunched": relaunched}
