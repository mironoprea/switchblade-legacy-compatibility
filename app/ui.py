"""Small, privacy-safe desktop interface for the legacy compatibility utility."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from app import legacy_compat as legacy
from app import repair


PRODUCT_NAME = "Switchblade Legacy Compatibility"
UNSIGNED_WARNING = "Unofficial, unsigned build. It does not include Razer software or drivers."


def configure_logging(data_root: Path = legacy.DATA_ROOT) -> logging.Logger:
    """Create a bounded local log without recording exception details or paths."""
    logger = logging.getLogger("switchblade_legacy.ui")
    if logger.handlers:
        return logger
    logs = data_root / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "ui.log", maxBytes=256 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class CompatibilityApp:
    """Threaded UI facade; all details presented to users are sanitized summaries."""

    def __init__(self, root: tk.Tk, *, operations=legacy, plan_builder=repair.build_plan) -> None:
        self.root = root
        self.operations = operations
        self.plan_builder = plan_builder
        self.results: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.status: dict[str, object] | None = None
        self.plan: repair.RepairPlan | None = None
        self.logger = configure_logging()
        root.title(PRODUCT_NAME)
        root.minsize(620, 420)

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=PRODUCT_NAME, font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=UNSIGNED_WARNING, foreground="#9c5700", wraplength=570).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self.summary = tk.StringVar(value="Run a read-only scan to check the installed legacy stack.")
        ttk.Label(frame, textvariable=self.summary, wraplength=570).grid(row=2, column=0, sticky="w")
        self.details = tk.Text(frame, height=11, width=72, wrap="word", state="disabled")
        self.details.grid(row=3, column=0, sticky="nsew", pady=12)
        frame.rowconfigure(3, weight=1)
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="ew")
        self.buttons: list[ttk.Button] = []
        self._button(buttons, "Scan status", self.scan)
        self._button(buttons, "Backup", self.backup)
        self._button(buttons, "Restore", self.restore)
        self._button(buttons, "Propose repair", self.propose_repair)
        self._button(buttons, "Confirm repair", self.confirm_repair)
        self._button(buttons, "Launch configurator", self.launch)
        self._button(buttons, "Open data folder", self.open_data_folder)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self._poll)

    def _button(self, parent: ttk.Frame, label: str, command: Callable[[], None]) -> None:
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side="left", padx=(0, 6), pady=4)
        self.buttons.append(button)

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _run(self, label: str, operation: Callable[[], object]) -> None:
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.state(["disabled"])
        self.summary.set(f"{label} in progress. It can only be cancelled before the next safe operation.")

        def worker() -> None:
            try:
                self.results.put(("success", operation()))
            except Exception as exc:  # Never expose raw exception text, which may contain a path.
                self.logger.warning("%s failed: %s", label, type(exc).__name__)
                self.results.put(("error", type(exc).__name__))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll)
            return
        self.busy = False
        for button in self.buttons:
            button.state(["!disabled"])
        if kind == "success":
            self._show_result(value)
        else:
            self.summary.set("The operation did not complete. No sensitive details were recorded.")
            messagebox.showerror(PRODUCT_NAME, "The operation did not complete. Review the diagnostic report or recovery guidance.")
        self.root.after(100, self._poll)

    def _show_result(self, value: object) -> None:
        if isinstance(value, dict) and "outcome" in value:
            outcome = str(value["outcome"])
            self.summary.set(f"Repair result: {outcome}.")
            recovery = value.get("recovery_command")
            self._set_details("Repair completed." if outcome == "completed" else "Repair did not complete. " + ("Recovery guidance is available in the repair journal." if recovery else "No mutation was performed."))
        elif isinstance(value, dict):
            classification = str(value.get("classification", "unknown"))
            self.status = value
            self.summary.set(f"Status: {classification}.")
            lines = [f"Status: {classification}"]
            lines.extend(str(step) for step in value.get("next_steps", []) if isinstance(step, str))
            self._set_details("\n".join(lines))
        elif isinstance(value, repair.RepairPlan):
            self.plan = value
            self.summary.set(f"Repair proposal: {value.classification}.")
            actions = [f"- {action.component_id}: {action.postcondition}" for action in value.actions]
            guidance = list(value.manual_guidance)
            self._set_details("Proposed mutations:\n" + ("\n".join(actions) if actions else "None") + "\n\nGuidance:\n" + "\n".join(guidance))
        elif value is True:
            self.summary.set("Razer Configurator was detected.")
        else:
            self.summary.set("Operation completed. Its location is available in the utility data folder.")

    def scan(self) -> None:
        self._run("Read-only scan", lambda: self.operations.scan())

    def propose_repair(self) -> None:
        def operation() -> repair.RepairPlan:
            status = self.operations.scan()
            return self.plan_builder(status)
        self._run("Repair proposal", operation)

    def backup(self) -> None:
        if not messagebox.askyesno(PRODUCT_NAME, "Create a backup? This writes only to this utility's per-user data folder and may export the installed MI_03 driver for local rollback. It does not change device drivers."):
            return
        self._run("Backup", lambda: self.operations.create_backup(export_driver=True))

    def confirm_repair(self) -> None:
        plan = self.plan
        if plan is None:
            messagebox.showinfo(PRODUCT_NAME, "Propose a repair first. No system change has been made.")
            return
        if not plan.actions:
            messagebox.showinfo(PRODUCT_NAME, "No verified automatic repair is available. Follow the displayed guidance instead.")
            return
        action_names = ", ".join(action.component_id for action in plan.actions)
        if not messagebox.askyesno(PRODUCT_NAME, f"Apply the reviewed repair for: {action_names}? A backup is created first. The legacy Razer processes will then be stopped only if the approved plan requires it. Driver bindings are never changed."):
            return

        def operation() -> dict[str, object]:
            journal, append_journal = self.operations._repair_journal(plan)
            result = repair.execute_plan(
                plan,
                confirmed=True,
                dependencies=repair.RepairDependencies(
                    create_backup=self.operations.create_backup,
                    stop_processes=self.operations.stop_legacy_processes,
                    launch_configurator=self.operations.launch_configurator,
                    rerun_inventory=self.operations.scan,
                    run_action=lambda _action: (_ for _ in ()).throw(RuntimeError("No verified repair actions registered")),
                    journal=append_journal,
                ),
            )
            result["journal_created"] = journal.exists()
            return result

        self._run("Confirmed repair", operation)

    def restore(self) -> None:
        archive = filedialog.askopenfilename(title="Select a legacy configuration backup", filetypes=[("ZIP backups", "*.zip")])
        if not archive:
            return
        if not messagebox.askyesno(PRODUCT_NAME, "Restore this validated backup? The utility will first create a pre-restore backup, then replace only allowlisted configuration files. Close legacy Razer processes before continuing."):
            return
        self._run("Restore", lambda: self.operations.restore_backup(Path(archive), confirmed=True))

    def launch(self) -> None:
        self._run("Configurator launch", self.operations.launch_configurator)

    def open_data_folder(self) -> None:
        self.operations.DATA_ROOT.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(self.operations.DATA_ROOT)  # type: ignore[attr-defined]
        self._set_details("Reports, journals, backups, and logs are stored under the utility's per-user data folder. They are preserved if the application is uninstalled.")

    def close(self) -> None:
        if not self.busy:
            self.root.destroy()


def main() -> int:
    root = tk.Tk()
    CompatibilityApp(root)
    root.mainloop()
    return 0
