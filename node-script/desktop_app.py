#!/usr/bin/env python3
"""Desktop UI for the JHCIS sync agent."""

import json
import logging
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Dict, List, Optional

from sync_agent import (
    get_app_dir,
    SUMMARY_TYPES,
    prepare_runtime,
    run_sync,
    setup_logger,
)


class QueueLogHandler(logging.Handler):
    """Forward log messages to the UI thread through a queue."""

    def __init__(self, log_queue: "queue.Queue[str]") -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.log_queue.put(self.format(record))


class SyncDesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("JHCIS Sync Desktop")
        self.root.geometry("980x720")
        self.root.minsize(900, 640)

        self.script_dir = get_app_dir()
        self.settings_file = self.script_dir / "scheduler_settings.json"
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.last_auto_run_key: Optional[str] = None

        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.env_var = tk.StringVar(value=".env")
        self.log_dir_var = tk.StringVar(value="logs")
        self.status_var = tk.StringVar(value="Ready")
        self.auto_sync_enabled_var = tk.BooleanVar(value=False)
        self.auto_sync_time_var = tk.StringVar(value="08:00")
        self.auto_sync_use_today_var = tk.BooleanVar(value=True)

        self._load_schedule_settings()
        self._build_ui()
        self.root.after(150, self._drain_logs)
        self.root.after(1000, self._scheduler_tick)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="JHCIS Summary Sync",
            font=("Segoe UI", 18, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Desktop app for running sync jobs and watching logs in one place.",
            font=("Segoe UI", 10)
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        controls = ttk.Frame(body, padding=12)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        controls.grid(row=0, column=0, sticky="ew")

        ttk.Label(controls, text="Sync Date").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.date_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0))

        top_action_bar = ttk.Frame(controls)
        top_action_bar.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        top_action_bar.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(top_action_bar, text="Send Data / Run Sync", command=self._start_sync)
        self.run_button.grid(row=0, column=0, sticky="w")

        ttk.Button(top_action_bar, text="Clear Log", command=self._clear_log).grid(row=0, column=2, sticky="e")

        ttk.Label(
            top_action_bar,
            textvariable=self.status_var,
            font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))

        self._add_path_row(controls, 2, "Env File", self.env_var)
        self._add_path_row(controls, 3, "Log Directory", self.log_dir_var, directory=True)

        schedule_frame = ttk.LabelFrame(controls, text="Auto Sync", padding=12)
        schedule_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        schedule_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            schedule_frame,
            text="Enable automatic sync",
            variable=self.auto_sync_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(schedule_frame, text="Run Time (HH:MM)").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(schedule_frame, textvariable=self.auto_sync_time_var, width=12).grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(10, 0)
        )

        ttk.Checkbutton(
            schedule_frame,
            text="Use today's date when auto sync runs",
            variable=self.auto_sync_use_today_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Button(schedule_frame, text="Save Schedule", command=self._save_schedule_settings).grid(
            row=3, column=0, sticky="w", pady=(12, 0)
        )

        log_panel = ttk.Frame(body, padding=12)
        log_panel.columnconfigure(0, weight=1)
        log_panel.rowconfigure(1, weight=1)
        log_panel.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        ttk.Label(log_panel, text="Execution Log", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.log_text = ScrolledText(log_panel, wrap=tk.WORD, font=("Consolas", 10), state=tk.DISABLED)
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _add_path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        directory: bool = False
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Button(
            parent,
            text="Browse",
            command=lambda: self._browse_path(variable, directory)
        ).grid(row=row, column=3, sticky="w", pady=(10, 0))

    def _browse_path(self, variable: tk.StringVar, directory: bool) -> None:
        initial = self.script_dir
        if directory:
            selected = filedialog.askdirectory(initialdir=initial)
        else:
            selected = filedialog.askopenfilename(initialdir=initial)

        if selected:
            try:
                relative = Path(selected).resolve().relative_to(self.script_dir)
                variable.set(str(relative))
            except ValueError:
                variable.set(selected)

    def _selected_types(self) -> List[str]:
        return SUMMARY_TYPES

    def _load_schedule_settings(self) -> None:
        if not self.settings_file.exists():
            return

        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self.auto_sync_enabled_var.set(bool(data.get("enabled", False)))
        self.auto_sync_time_var.set(str(data.get("time", "08:00")))
        self.auto_sync_use_today_var.set(bool(data.get("use_today_date", True)))

    def _save_schedule_settings(self) -> None:
        try:
            normalized_time = self._normalize_schedule_time(self.auto_sync_time_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid schedule", str(exc))
            return

        self.auto_sync_time_var.set(normalized_time)

        payload = {
            "enabled": self.auto_sync_enabled_var.get(),
            "time": normalized_time,
            "use_today_date": self.auto_sync_use_today_var.get(),
        }
        self.settings_file.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        if self.auto_sync_enabled_var.get():
            self.status_var.set(f"Auto sync daily at {normalized_time}")
            self.log_queue.put(f"INFO: Auto sync enabled at {normalized_time} every day")
            try:
                self._maybe_run_scheduled_sync()
            except ValueError as exc:
                self.status_var.set(str(exc))
        else:
            self.status_var.set("Auto sync disabled")
            self.log_queue.put("INFO: Auto sync disabled")

    @staticmethod
    def _normalize_schedule_time(value: str) -> str:
        try:
            parsed = datetime.strptime(value.strip(), "%H:%M")
        except ValueError as exc:
            raise ValueError("Run Time must use HH:MM, for example 08:00") from exc
        return parsed.strftime("%H:%M")

    def _scheduler_tick(self) -> None:
        try:
            if self.auto_sync_enabled_var.get():
                try:
                    self._maybe_run_scheduled_sync()
                except ValueError as exc:
                    self.status_var.set(str(exc))
        finally:
            self.root.after(1000, self._scheduler_tick)

    def _maybe_run_scheduled_sync(self) -> None:
        schedule_time = self._normalize_schedule_time(self.auto_sync_time_var.get())
        self.auto_sync_time_var.set(schedule_time)
        now = datetime.now()
        schedule_key = f"{now.strftime('%Y-%m-%d')} {schedule_time}"

        if now.strftime("%H:%M") != schedule_time:
            return

        if self.last_auto_run_key == schedule_key:
            return

        if self.worker and self.worker.is_alive():
            self.log_queue.put("INFO: Scheduled sync skipped because another sync job is running")
            self.last_auto_run_key = schedule_key
            return

        date_value = self.date_var.get().strip()
        if self.auto_sync_use_today_var.get():
            date_value = now.strftime("%Y-%m-%d")
            self.date_var.set(date_value)

        self.last_auto_run_key = schedule_key
        self.log_queue.put(f"INFO: Auto sync started for schedule {schedule_key}")
        self._launch_sync(date_value, show_completion_dialog=False)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _drain_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)

        self.root.after(150, self._drain_logs)

    def _set_running(self, running: bool) -> None:
        self.run_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.status_var.set("Running..." if running else "Ready")

    def _start_sync(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Sync in progress", "A sync job is already running.")
            return

        try:
            datetime.strptime(self.date_var.get(), "%Y-%m-%d")
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self._clear_log()
        self._launch_sync(self.date_var.get(), show_completion_dialog=True)

    def _launch_sync(self, date_value: str, show_completion_dialog: bool) -> None:
        self._set_running(True)
        self.worker = threading.Thread(
            target=self._run_sync_job,
            args=(date_value, self._selected_types(), show_completion_dialog),
            daemon=True,
        )
        self.worker.start()

    def _run_sync_job(
        self,
        date_value: str,
        summary_types: List[str],
        show_completion_dialog: bool,
    ) -> None:
        try:
            runtime = prepare_runtime(
                script_dir=self.script_dir,
                env_path=self.env_or_default(self.env_var.get(), ".env"),
                log_dir_path=self.env_or_default(self.log_dir_var.get(), "logs"),
            )

            logger = setup_logger(runtime["log_dir"], date_value)
            ui_handler = QueueLogHandler(self.log_queue)
            ui_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            logger.addHandler(ui_handler)

            results = run_sync(
                date=date_value,
                summary_types=summary_types,
                config=runtime["config"],
                log_dir=runtime["log_dir"],
                logger=logger,
            )
            success_count = sum(1 for value in results.values() if value)
            total = len(results)
            self.log_queue.put(f"{'=' * 60}")
            self.log_queue.put(f"Sync Summary: {success_count}/{total} successful")
            self.log_queue.put(f"{'=' * 60}")
            if show_completion_dialog:
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Sync finished",
                        f"Completed: {success_count}/{total} successful"
                    ),
                )
        except Exception as exc:  # pragma: no cover - UI safety net
            self.log_queue.put(f"ERROR: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Sync failed", str(exc)))
        finally:
            self.root.after(0, lambda: self._set_running(False))

    @staticmethod
    def env_or_default(value: str, default: str) -> str:
        return value.strip() or default


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    app = SyncDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
