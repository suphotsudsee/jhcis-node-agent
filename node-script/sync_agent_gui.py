#!/usr/bin/env python3
"""
JHCIS Summary Centralization Sync Agent - Desktop GUI
สำหรับ รพ.สต./สถานบริการ ในระบบ JHCIS
"""

import os
import pymysql
import subprocess
import sys
import threading
import tkinter as tk
import mysql.connector
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import sync functions from sync_agent
try:
    from sync_agent import (
        SUMMARY_TYPES,
        load_env_config,
        load_env_file,
        connect_to_database,
        fetch_summary_data,
        send_to_central_api,
        sync_central_queries_to_file,
        get_app_dir,
    )
except ImportError:
    # When running as compiled exe
    import importlib.util
    spec = importlib.util.spec_from_file_location("sync_agent", Path(__file__).parent / "sync_agent.py")
    sync_agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_agent)
    SUMMARY_TYPES = sync_agent.SUMMARY_TYPES
    load_env_config = sync_agent.load_env_config
    load_env_file = sync_agent.load_env_file
    connect_to_database = sync_agent.connect_to_database
    fetch_summary_data = sync_agent.fetch_summary_data
    send_to_central_api = sync_agent.send_to_central_api
    sync_central_queries_to_file = sync_agent.sync_central_queries_to_file
    get_app_dir = sync_agent.get_app_dir


class JHCISyncApp:
    """Main Application Class"""

    SCHEDULE_DAY_OPTIONS = [
        ("sunday", "อาทิตย์"),
        ("monday", "จันทร์"),
        ("tuesday", "อังคาร"),
        ("wednesday", "พุธ"),
        ("thursday", "พฤหัสบดี"),
        ("friday", "ศุกร์"),
        ("saturday", "เสาร์"),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("JHCIS Sync Agent")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Set icon if available
        self._set_icon()
        
        # Variables
        self.is_syncing = False
        self.config = {}
        self.sync_thread: Optional[threading.Thread] = None
        
        # Load config
        self._load_config()
        
        # Build UI
        self._build_ui()
        
        # Center window
        self._center_window()
        
    
    def _set_icon(self):
        """Set window icon if available"""
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path))
    
    def _center_window(self):
        """Center window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def _load_config(self):
        """Load configuration from .env file"""
        import os
        
        script_dir = get_app_dir()
        
        # Clear environment variables from previous load
        env_keys = [k for k in os.environ.keys() if k.startswith('JHCIS_')]
        for key in env_keys:
            del os.environ[key]
        
        # Try external .env first (for user configuration)
        env_file = script_dir / ".env"
        
        # Also check for .env.example as fallback
        env_example = script_dir / ".env.example"
        
        loaded = False
        config_source = None
        
        # Load .env if it exists externally
        if env_file.exists():
            load_env_file(env_file)
            loaded = True
            config_source = str(env_file)
        else:
            # When running as exe, try to find .env in common locations
            if getattr(sys, 'frozen', False):
                # Check same directory as exe
                exe_dir = Path(sys.executable).parent
                exe_env = exe_dir / ".env"
                if exe_env.exists():
                    load_env_file(exe_env)
                    loaded = True
                    config_source = str(exe_env)
                
                # Check working directory
                if not loaded:
                    cwd_env = Path.cwd() / ".env"
                    if cwd_env.exists():
                        load_env_file(cwd_env)
                        loaded = True
                        config_source = str(cwd_env)
        
        # Load from .env.example as fallback
        if not loaded and env_example.exists():
            try:
                import shutil
                shutil.copy(env_example, env_file)
                load_env_file(env_file)
                loaded = True
                config_source = str(env_file)
            except:
                pass
        
        self.config = load_env_config()
        self._config_source = config_source
        
        # Update settings vars if they exist (for reloading)
        if hasattr(self, 'settings_vars') and self.settings_vars:
            self._reload_settings_vars()
            
            # Log after UI is built
            if config_source and hasattr(self, 'log_text'):
                self._log(f"Loaded config from {config_source}")

    def _config_from_settings_vars(self) -> Dict[str, Any]:
        """Build a runtime config from the current Settings tab values."""
        config = {
            section: dict(values) if isinstance(values, dict) else values
            for section, values in self.config.items()
        }

        if not hasattr(self, "settings_vars"):
            return config

        config.setdefault("database", {})
        config.setdefault("api", {})
        config.setdefault("facility", {})
        config.setdefault("schedule", {})
        config.setdefault("settings", {})

        config["database"]["host"] = self.settings_vars["db_host"].get().strip()
        config["database"]["port"] = int(self.settings_vars["db_port"].get().strip())
        config["database"]["user"] = self.settings_vars["db_user"].get().strip()
        config["database"]["password"] = self.settings_vars["db_password"].get()
        config["database"]["database"] = self.settings_vars["db_name"].get().strip()

        config["api"]["endpoint"] = self.settings_vars["api_endpoint"].get().strip()
        config["api"]["api_key"] = self.settings_vars["api_key"].get().strip()

        config["facility"]["facility_id"] = self.settings_vars["facility_id"].get().strip()
        config["facility"]["facility_name"] = self.settings_vars["facility_name"].get().strip()
        config["facility"]["facility_code"] = self.settings_vars["facility_code"].get().strip()

        config["schedule"]["day"] = self.settings_vars["schedule_day"].get().strip().lower()
        config["schedule"]["time"] = self.settings_vars["schedule_time"].get().strip()

        config["settings"]["retry_attempts"] = int(self.settings_vars["retry_attempts"].get().strip())
        config["settings"]["retry_delay_seconds"] = int(self.settings_vars["retry_delay"].get().strip())
        config["settings"]["timeout_seconds"] = int(self.settings_vars["timeout"].get().strip())

        return config
    
    def _build_ui(self):
        """Build the user interface"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Sync
        sync_frame = ttk.Frame(notebook, padding="10")
        notebook.add(sync_frame, text="🔄 Sync")
        self._build_sync_tab(sync_frame)
        
        # Tab 2: Settings
        settings_frame = ttk.Frame(notebook, padding="10")
        notebook.add(settings_frame, text="⚙️ Settings")
        self._build_settings_tab(settings_frame)
        
        # Tab 3: Schedule
        schedule_frame = ttk.Frame(notebook, padding="10")
        notebook.add(schedule_frame, text="🗓 Schedule")
        self._build_schedule_tab(schedule_frame)
        
        # Tab 4: Logs
        logs_frame = ttk.Frame(notebook, padding="10")
        notebook.add(logs_frame, text="📋 Logs")
        self._build_logs_tab(logs_frame)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def _build_sync_tab(self, parent: ttk.Frame):
        """Build the sync tab"""
        # Date selection
        date_frame = ttk.LabelFrame(parent, text="📅 วันที่ Sync", padding="10")
        date_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(date_frame, text="วันที่:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        date_entry = ttk.Entry(date_frame, textvariable=self.date_var, width=15)
        date_entry.grid(row=0, column=1, sticky=tk.W)
        
        ttk.Button(date_frame, text="📅", command=self._pick_date, width=3).grid(row=0, column=2, padx=5)
        ttk.Button(date_frame, text="วันนี้", command=lambda: self.date_var.set(datetime.now().strftime("%Y-%m-%d"))).grid(row=0, column=3, padx=5)
        
        # Sync buttons
        sync_btn_frame = ttk.Frame(parent)
        sync_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.sync_btn = ttk.Button(sync_btn_frame, text="▶️ เริ่ม Sync", command=self._start_sync)
        self.sync_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(sync_btn_frame, text="⏹️ หยุด", command=self._stop_sync, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(sync_btn_frame, text="🔍 ทดสอบการเชื่อมต่อ", command=self._test_connection).pack(side=tk.LEFT, padx=5)
        
        # Progress
        progress_frame = ttk.Frame(parent)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, side=tk.LEFT, expand=True)
        
        self.progress_label = ttk.Label(progress_frame, text="")
        self.progress_label.pack(side=tk.LEFT, padx=10)
        
        # Results
        results_frame = ttk.LabelFrame(parent, text="📊 ผลการ Sync", padding="10")
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview for results
        columns = ("type", "status", "records", "message")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=10)
        
        self.results_tree.heading("type", text="ประเภท")
        self.results_tree.heading("status", text="สถานะ")
        self.results_tree.heading("records", text="Records")
        self.results_tree.heading("message", text="Message")
        
        self.results_tree.column("type", width=100)
        self.results_tree.column("status", width=80)
        self.results_tree.column("records", width=80)
        self.results_tree.column("message", width=300)
        
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _build_settings_tab(self, parent: ttk.Frame):
        """Build the settings tab"""
        # Database settings
        db_frame = ttk.LabelFrame(parent, text="🗄️ Database Settings", padding="10")
        db_frame.pack(fill=tk.X, pady=(0, 10))
        
        db_fields = [
            ("Host:", "db_host", "localhost"),
            ("Port:", "db_port", "3306"),
            ("User:", "db_user", "jhcis_user"),
            ("Password:", "db_password", ""),
            ("Database:", "db_name", "jhcis_db"),
        ]
        
        self.settings_vars = {}
        for i, (label, key, default) in enumerate(db_fields):
            ttk.Label(db_frame, text=label).grid(row=i, column=0, sticky=tk.W, padx=(0, 10), pady=2)
            db_config_key = "database" if key == "db_name" else key.replace("db_", "")
            var = tk.StringVar(value=self.config.get("database", {}).get(db_config_key, default))
            self.settings_vars[key] = var
            entry = ttk.Entry(db_frame, textvariable=var, width=30)
            if key == "db_password":
                entry.configure(show="*")
            entry.grid(row=i, column=1, sticky=tk.W, pady=2)
        
        # API settings
        api_frame = ttk.LabelFrame(parent, text="🌐 API Settings", padding="10")
        api_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(api_frame, text="Endpoint:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=2)
        api_endpoint_var = tk.StringVar(value=self.config.get("api", {}).get("endpoint", ""))
        self.settings_vars["api_endpoint"] = api_endpoint_var
        ttk.Entry(api_frame, textvariable=api_endpoint_var, width=50).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=2)
        api_key_var = tk.StringVar(value=self.config.get("api", {}).get("api_key", ""))
        self.settings_vars["api_key"] = api_key_var
        api_key_entry = ttk.Entry(api_frame, textvariable=api_key_var, width=50, show="*")
        api_key_entry.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # Facility settings
        facility_frame = ttk.LabelFrame(parent, text="🏥 Facility Settings", padding="10")
        facility_frame.pack(fill=tk.X, pady=(0, 10))
        
        facility_fields = [
            ("Facility ID:", "facility_id", ""),
            ("Facility Name:", "facility_name", ""),
            ("Facility Code:", "facility_code", ""),
        ]
        
        for i, (label, key, default) in enumerate(facility_fields):
            ttk.Label(facility_frame, text=label).grid(row=i, column=0, sticky=tk.W, padx=(0, 10), pady=2)
            var = tk.StringVar(value=self.config.get("facility", {}).get(key, default))
            self.settings_vars[key] = var
            ttk.Entry(facility_frame, textvariable=var, width=40).grid(row=i, column=1, sticky=tk.W, pady=2)
        
        # Sync settings
        sync_frame = ttk.LabelFrame(parent, text="⚙️ Sync Settings", padding="10")
        sync_frame.pack(fill=tk.X, pady=(0, 10))
        
        sync_fields = [
            ("Retry Attempts:", "retry_attempts", "3"),
            ("Retry Delay (sec):", "retry_delay", "30"),
            ("Timeout (sec):", "timeout", "60"),
        ]
        
        for i, (label, key, default) in enumerate(sync_fields):
            ttk.Label(sync_frame, text=label).grid(row=i, column=0, sticky=tk.W, padx=(0, 10), pady=2)
            var = tk.StringVar(value=str(self.config.get("settings", {}).get(key.replace("_delay", "_delay_seconds").replace("_timeout", "_timeout_seconds"), default)))
            self.settings_vars[key] = var
            ttk.Entry(sync_frame, textvariable=var, width=10).grid(row=i, column=1, sticky=tk.W, pady=2)
        
        # Buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="💾 บันทึก Settings", command=self._save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 โหลดใหม่", command=self._reload_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📁 เปิดโฟลเดอร์", command=self._open_folder).pack(side=tk.LEFT, padx=5)

    def _build_schedule_tab(self, parent: ttk.Frame):
        """Build the sync schedule tab with multi-day selection."""
        schedule_frame = ttk.LabelFrame(parent, text="🗓 Sync Schedule", padding="10")
        schedule_frame.pack(fill=tk.X, pady=(0, 10))

        schedule_config = self.config.get("schedule", {})
        stored_days = str(schedule_config.get("day", "")).lower()
        default_time = str(schedule_config.get("time", "08:00")).strip() or "08:00"

        # Day selection with checkboxes
        ttk.Label(schedule_frame, text="วันที่จะ sync:").grid(row=0, column=0, sticky=tk.NW, padx=(0, 10), pady=2)
        
        day_frame = ttk.Frame(schedule_frame)
        day_frame.grid(row=0, column=1, sticky=tk.W, pady=2)

        self.schedule_day_vars = {}
        stored_days_list = [d.strip() for d in stored_days.split(",") if d.strip()]
        
        for i, (day_key, day_label) in enumerate(self.SCHEDULE_DAY_OPTIONS):
            var = tk.BooleanVar(value=day_key in stored_days_list or stored_days == "all")
            self.schedule_day_vars[day_key] = var
            cb = ttk.Checkbutton(day_frame, text=day_label, variable=var)
            cb.grid(row=i // 4, column=i % 4, sticky=tk.W, padx=5, pady=1)

        # All days checkbox
        all_frame = ttk.Frame(schedule_frame)
        all_frame.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        self.schedule_all_days = tk.BooleanVar(value=stored_days == "all" or len(stored_days_list) == 7)
        all_cb = ttk.Checkbutton(all_frame, text="ทุกวัน (All)", variable=self.schedule_all_days, command=self._toggle_all_days)
        all_cb.pack(side=tk.LEFT)

        # Time selection
        ttk.Label(schedule_frame, text="เวลา:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=2)
        time_frame = ttk.Frame(schedule_frame)
        time_frame.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        self.settings_vars["schedule_time"] = tk.StringVar(value=default_time)
        ttk.Entry(time_frame, textvariable=self.settings_vars["schedule_time"], width=8).pack(side=tk.LEFT)
        ttk.Label(time_frame, text=" (HH:MM รูปแบบ 24 ชั่วโมง)").pack(side=tk.LEFT)

        # Schedule info
        info_frame = ttk.LabelFrame(parent, text="📋 ข้อมูล", padding="10")
        info_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(info_frame, text="• เลือกวันที่ต้องการ sync ได้หลายวัน", anchor=tk.W).pack(fill=tk.X)
        ttk.Label(info_frame, text="• ถ้าเลือก 'ทุกวัน' จะ sync ทุกวัน", anchor=tk.W).pack(fill=tk.X)
        ttk.Label(info_frame, text="• ตั้งค่าเวลาเป็นรูปแบบ HH:MM (เช่น 08:00, 21:30)", anchor=tk.W).pack(fill=tk.X)
        ttk.Label(info_frame, text="• กด 'บันทึก Settings' เพื่อสร้าง Windows Task Scheduler", anchor=tk.W).pack(fill=tk.X)

    def _toggle_all_days(self):
        """Toggle all days selection."""
        if self.schedule_all_days.get():
            for var in self.schedule_day_vars.values():
                var.set(True)
        else:
            for var in self.schedule_day_vars.values():
                var.set(False)
    
    def _get_selected_days(self) -> str:
        """Get selected days as comma-separated string."""
        if self.schedule_all_days.get():
            return "all"
        
        selected = [day_key for day_key, var in self.schedule_day_vars.items() if var.get()]
        return ",".join(selected) if selected else "all"
    
    def _build_logs_tab(self, parent: ttk.Frame):
        """Build the logs tab"""
        # Log display
        self.log_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Log buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="🗑️ Clear", command=self._clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="💾 Save Log", command=self._save_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📂 Open Log Folder", command=self._open_log_folder).pack(side=tk.LEFT, padx=5)
    
    def _pick_date(self):
        """Open date picker dialog"""
        # Simple date picker using askstring
        from tkinter import simpledialog
        date = simpledialog.askstring("เลือกวันที่", "กรอกวันที่ (YYYY-MM-DD):", initialvalue=self.date_var.get())
        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
                self.date_var.set(date)
            except ValueError:
                self._log("Invalid date format. Use YYYY-MM-DD", "ERROR")

    def _normalize_schedule_time(self, raw_time: str) -> Optional[str]:
        """Normalize schedule time input to HH:MM."""
        value = raw_time.strip()
        try:
            return datetime.strptime(value, "%H:%M").strftime("%H:%M")
        except ValueError:
            return None

    def _scheduled_task_name(self) -> str:
        facility_code = self.settings_vars.get("facility_code").get().strip() if self.settings_vars.get("facility_code") else ""
        suffix = facility_code or "Default"
        return f"JHCIS Sync Agent {suffix}"

    def _find_cli_executable(self) -> Optional[Path]:
        app_dir = get_app_dir()
        candidates = [
            app_dir / "jhcis-sync-agent.exe",
            app_dir / "dist" / "jhcis-sync-agent.exe",
            Path.cwd() / "dist" / "jhcis-sync-agent.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _apply_windows_schedule(self) -> None:
        schedule_days = self._get_selected_days()
        schedule_time = self._normalize_schedule_time(self.settings_vars["schedule_time"].get())
        if not schedule_time:
            raise ValueError("Schedule time must use HH:MM format")
        task_name = self._scheduled_task_name()
        cli_executable = self._find_cli_executable()
        if not cli_executable:
            raise FileNotFoundError("Cannot find jhcis-sync-agent.exe for scheduled sync")
        log_dir = get_app_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        task_log = log_dir / "scheduled-task.log"
        runner_script = get_app_dir() / "run-scheduled-sync.cmd"
        runner_script.write_text(
            "\r\n".join([
                "@echo off",
                f"cd /d \"{get_app_dir()}\"",
                f"\"{cli_executable}\" --all-types >> \"{task_log}\" 2>&1",
            ]) + "\r\n",
            encoding="utf-8",
        )

        if schedule_days == "all":
            schedule_args = ["/SC", "DAILY"]
        else:
            # Convert days to Windows Task Scheduler format
            day_map = {
                "sunday": "SUN",
                "monday": "MON",
                "tuesday": "TUE",
                "wednesday": "WED",
                "thursday": "THU",
                "friday": "FRI",
                "saturday": "SAT",
            }
            days_list = [d.strip() for d in schedule_days.split(",") if d.strip()]
            mapped_days = [day_map.get(d.lower()) for d in days_list if day_map.get(d.lower())]
            
            if not mapped_days:
                raise ValueError(f"Unsupported schedule days: {schedule_days}")
            
            # Windows Task Scheduler uses comma-separated days for WEEKLY
            schedule_args = ["/SC", "WEEKLY", "/D", ",".join(mapped_days)]

        task_command = f'"{runner_script}"'
        command = [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            *schedule_args,
            "/ST",
            schedule_time,
            "/TR",
            task_command,
            "/F",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "Unknown schedule creation error"
            raise RuntimeError(message)
        self._log(f"Windows Task Scheduler updated: {task_name} at {schedule_days} {schedule_time}", "INFO")
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message to the log tab"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}\n"
        
        # Only write to log_text if it exists (UI is built)
        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.insert(tk.END, log_line)
            self.log_text.see(tk.END)
            self.root.update_idletasks()
        else:
            # Fallback to console if UI not ready
            print(f"[{level}] {message}")
    
    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress bar"""
        percent = (current / total * 100) if total > 0 else 0
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{current}/{total} {message}")
        self.root.update_idletasks()
    
    def _set_ui_state(self, syncing: bool):
        """Enable/disable UI elements during sync"""
        self.is_syncing = syncing
        self.sync_btn.config(state=tk.DISABLED if syncing else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if syncing else tk.DISABLED)
        
        if syncing:
            self.status_var.set("Syncing...")
        else:
            self.status_var.set("Ready")
    
    def _start_sync(self):
        """Start sync process"""
        if self.is_syncing:
            return
        
        selected_types = list(SUMMARY_TYPES)
        
        date = self.date_var.get()
        
        # Validate date
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            self._log("Invalid date format. Use YYYY-MM-DD", "ERROR")
            return
        
        # Clear results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        self._set_ui_state(True)
        self._log(f"Starting sync for {date}: {', '.join(selected_types)}")
        
        # Run sync in background thread
        self.sync_thread = threading.Thread(
            target=self._run_sync,
            args=(date, selected_types),
            daemon=True
        )
        self.sync_thread.start()
    
    def _run_sync(self, date: str, summary_types: List[str]):
        """Run sync in background thread"""
        import logging
        
        # Create logger for this sync
        script_dir = get_app_dir()
        log_dir = script_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        
        logger = logging.getLogger("jhcis_sync_gui")
        logger.setLevel(logging.INFO)
        
        # Load fresh config
        self._load_config()
        
        results = {}
        total = len(summary_types)
        
        # Sync central queries first
        self._log("Fetching central queries...")
        queries_by_type = sync_central_queries_to_file(summary_types, self.config, logger)
        
        if not queries_by_type:
            self._log("Failed to fetch central queries from API", "ERROR")
            self.root.after(0, lambda: self._set_ui_state(False))
            return
        
        # Connect to database
        self._log("Connecting to database...")
        connection = connect_to_database(self.config, logger)
        
        if not connection:
            self._log("Failed to connect to database", "ERROR")
            self.root.after(0, lambda: self._set_ui_state(False))
            return
        
        try:
            for i, summary_type in enumerate(summary_types):
                if not self.is_syncing:
                    self._log("Sync cancelled by user", "WARN")
                    break
                
                self._update_progress(i, total, f"- {summary_type}")
                self._log(f"Processing: {summary_type}")
                
                # Get query
                query = queries_by_type.get(summary_type)
                if not query:
                    self._log(f"Query not found for {summary_type}", "WARN")
                    results[summary_type] = False
                    self._add_result(summary_type, "Skipped", 0, "Query not found")
                    continue
                
                # Fetch data
                data = fetch_summary_data(connection, query, date)
                
                if not data:
                    self._log(f"No data for {summary_type}", "WARN")
                    results[summary_type] = False
                    self._add_result(summary_type, "No Data", 0, "No records found")
                    continue
                
                self._log(f"Found {len(data)} records for {summary_type}")
                
                # Send to API
                success = send_to_central_api(data, summary_type, date, self.config, logger)
                results[summary_type] = success
                
                if success:
                    self._add_result(summary_type, "Success", len(data), "Synced successfully")
                    self._log(f"{summary_type} synced successfully", "INFO")
                else:
                    self._add_result(summary_type, "Failed", len(data), "API error")
                    self._log(f"{summary_type} sync failed", "ERROR")
        
        finally:
            connection.close()
        
        # Update UI
        self._update_progress(total, total, "Done")
        success_count = sum(1 for v in results.values() if v)
        self._log(f"Sync completed: {success_count}/{len(summary_types)} successful")
        self.root.after(0, lambda: self._set_ui_state(False))
    
    def _add_result(self, summary_type: str, status: str, records: int, message: str):
        """Add result to treeview"""
        self.root.after(0, lambda: self.results_tree.insert("", tk.END, values=(summary_type, status, records, message)))
    
    def _stop_sync(self):
        """Stop sync process"""
        self.is_syncing = False
        self._log("Stopping sync...", "WARN")
    
    def _test_connection(self):
        """Test database and API connections"""
        import logging
        
        self._log("Testing connections...")
        self.status_var.set("Testing connection...")
        self.root.update()
        
        try:
            self.config = self._config_from_settings_vars()
        except ValueError as e:
            self.status_var.set("Ready")
            self._log(f"Invalid settings: {e}", "ERROR")
            return
        
        results = []
        errors = []
        
        # Test Database connection
        self._log("Testing database connection...")
        try:
            logger = logging.getLogger("jhcis_sync_gui_test")
            connection = connect_to_database(self.config, logger)
            
            if connection:
                self._log("✓ Database connection successful", "INFO")
                results.append("✓ Database: สำเร็จ")
                connection.close()
            else:
                probe_error = self._probe_database_error()
                self._log(f"✗ Database connection failed: {probe_error}", "ERROR")
                results.append(f"✗ Database: {probe_error}")
                db = self.config.get("database", {})
                errors.append(
                    f"Database connection failed ({db.get('host')}:{db.get('port')}/{db.get('database')} user={db.get('user')}): {probe_error}"
                )
        except Exception as e:
            error_msg = str(e)
            self._log(f"✗ Database error: {error_msg}", "ERROR")
            results.append(f"✗ Database: {error_msg}")
            errors.append(f"Database: {error_msg}")
        
        # Test API connection
        self._log("Testing API connection...")
        try:
            import requests
            api_endpoint = self.config.get("api", {}).get("endpoint", "")
            api_key = self.config.get("api", {}).get("api_key", "")
            
            if not api_endpoint:
                self._log("✗ API endpoint not configured", "ERROR")
                results.append("✗ API: ไม่ได้ตั้งค่า endpoint")
                errors.append("API endpoint not configured")
            else:
                # Get base URL (remove /sync suffix if present)
                base_url = api_endpoint.replace("/sync", "")
                health_url = f"{base_url}/health"
                
                headers = {"X-API-Key": api_key} if api_key else {}
                response = requests.get(health_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    self._log("✓ API connection successful", "INFO")
                    results.append("✓ API: สำเร็จ")
                    queries_by_type = sync_central_queries_to_file(SUMMARY_TYPES, self.config, logger)
                    if queries_by_type:
                        query_file = get_app_dir() / "docs" / "queries.sql"
                        self._log(f"Saved {len(queries_by_type)} queries to {query_file}", "INFO")
                        results.append(f"✓ Queries: บันทึก {len(queries_by_type)} รายการ")
                    else:
                        self._log("✗ Failed to fetch queries from API", "ERROR")
                        results.append("✗ Queries: ไม่สามารถดึง query ได้")
                        errors.append("Failed to fetch queries from API")
                else:
                    self._log(f"✗ API returned status {response.status_code}", "ERROR")
                    results.append(f"✗ API: HTTP {response.status_code}")
                    errors.append(f"API returned status {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            self._log(f"✗ API connection error: Cannot connect to server", "ERROR")
            results.append("✗ API: ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์")
            errors.append("API: Cannot connect to server")
        except requests.exceptions.Timeout as e:
            self._log(f"✗ API timeout", "ERROR")
            results.append("✗ API: Timeout")
            errors.append("API: Connection timeout")
        except Exception as e:
            error_msg = str(e)
            self._log(f"✗ API error: {error_msg}", "ERROR")
            results.append(f"✗ API: {error_msg}")
            errors.append(f"API: {error_msg}")
        
        # Show results
        self.status_var.set("Ready")
        for line in results:
            self._log(line, "ERROR" if line.startswith("✗") else "INFO")
        for line in errors:
            self._log(line, "ERROR")

    def _probe_database_error(self) -> str:
        """Run a direct MySQL probe and return the exact error text."""
        db = self.config.get("database", {})
        try:
            connection = pymysql.connect(
                host=db.get("host"),
                port=db.get("port"),
                user=db.get("user"),
                password=db.get("password"),
                database=db.get("database"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.Cursor,
            )
            cursor = connection.cursor()
            cursor.execute("SELECT DATABASE(), VERSION()")
            cursor.fetchone()
            cursor.close()
            connection.close()
            return "connection succeeded via PyMySQL fallback"
        except Exception as e:
            return str(e)
    
    def _save_settings(self):
        """Save settings to .env file"""
        script_dir = get_app_dir()
        env_file = script_dir / ".env"
        
        try:
            normalized_schedule_time = self._normalize_schedule_time(self.settings_vars["schedule_time"].get())
            if not normalized_schedule_time:
                raise ValueError("Schedule time must use HH:MM format, for example 21:26")
            self.settings_vars["schedule_time"].set(normalized_schedule_time)

            # Get selected days
            schedule_days = self._get_selected_days()

            # Build .env content
            env_content = f"""# JHCIS Sync Agent Configuration
# Generated: {datetime.now().isoformat()}

# Database
JHCIS_DB_HOST={self.settings_vars['db_host'].get()}
JHCIS_DB_PORT={self.settings_vars['db_port'].get()}
JHCIS_DB_USER={self.settings_vars['db_user'].get()}
JHCIS_DB_PASSWORD={self.settings_vars['db_password'].get()}
JHCIS_DB_NAME={self.settings_vars['db_name'].get()}

# API
JHCIS_API_ENDPOINT={self.settings_vars['api_endpoint'].get()}
JHCIS_API_KEY={self.settings_vars['api_key'].get()}

# Facility
JHCIS_FACILITY_ID={self.settings_vars['facility_id'].get()}
JHCIS_FACILITY_NAME={self.settings_vars['facility_name'].get()}
JHCIS_FACILITY_CODE={self.settings_vars['facility_code'].get()}

# Schedule
JHCIS_SYNC_SCHEDULE_DAY={schedule_days}
JHCIS_SYNC_SCHEDULE_TIME={self.settings_vars['schedule_time'].get()}

# Settings
JHCIS_RETRY_ATTEMPTS={self.settings_vars['retry_attempts'].get()}
JHCIS_RETRY_DELAY_SECONDS={self.settings_vars['retry_delay'].get()}
JHCIS_TIMEOUT_SECONDS={self.settings_vars['timeout'].get()}
"""
            
            env_file.write_text(env_content, encoding='utf-8')
            self._log(f"Settings saved to {env_file}")
            self._log(f"Schedule days: {schedule_days}")
            self._apply_windows_schedule()
            
            # Reload config
            self._load_config()
            self.status_var.set("Settings saved")
            
        except Exception as e:
            self._log(f"Failed to save settings: {e}", "ERROR")
            self.status_var.set("Save failed")
    
    def _reload_settings(self):
        """Reload settings from .env"""
        self._load_config()
        
        # Update UI vars
        self._reload_settings_vars()
        
        self._log("Settings reloaded")
        self.status_var.set("Settings reloaded")
    
    def _reload_settings_vars(self):
        """Update settings vars from config"""
        if not hasattr(self, 'settings_vars'):
            return
        
        self.settings_vars['db_host'].set(self.config.get("database", {}).get("host", "localhost"))
        self.settings_vars['db_port'].set(self.config.get("database", {}).get("port", "3306"))
        self.settings_vars['db_user'].set(self.config.get("database", {}).get("user", ""))
        self.settings_vars['db_password'].set(self.config.get("database", {}).get("password", ""))
        self.settings_vars['db_name'].set(self.config.get("database", {}).get("database", "jhcisdb"))
        self.settings_vars['api_endpoint'].set(self.config.get("api", {}).get("endpoint", ""))
        self.settings_vars['api_key'].set(self.config.get("api", {}).get("api_key", ""))
        self.settings_vars['facility_id'].set(self.config.get("facility", {}).get("facility_id", ""))
        self.settings_vars['facility_name'].set(self.config.get("facility", {}).get("facility_name", ""))
        self.settings_vars['facility_code'].set(self.config.get("facility", {}).get("facility_code", ""))
        
        # Reload schedule days
        schedule_time = str(self.config.get("schedule", {}).get("time", "08:00")).strip()
        schedule_days = str(self.config.get("schedule", {}).get("day", "all")).lower()
        
        self.settings_vars['schedule_time'].set(schedule_time or "08:00")
        
        # Update day checkboxes
        if hasattr(self, 'schedule_day_vars'):
            stored_days_list = [d.strip() for d in schedule_days.split(",") if d.strip()]
            for day_key, var in self.schedule_day_vars.items():
                var.set(day_key in stored_days_list or schedule_days == "all")
            
            # Update "all days" checkbox
            if hasattr(self, 'schedule_all_days'):
                self.schedule_all_days.set(schedule_days == "all" or len(stored_days_list) == 7)
        
        self.settings_vars['retry_attempts'].set(str(self.config.get("settings", {}).get("retry_attempts", "3")))
        self.settings_vars['retry_delay'].set(str(self.config.get("settings", {}).get("retry_delay_seconds", "30")))
        self.settings_vars['timeout'].set(str(self.config.get("settings", {}).get("timeout_seconds", "60")))
        
        self._log("Settings reloaded")
        self.status_var.set("Settings reloaded")
    
    def _clear_logs(self):
        """Clear log display"""
        self.log_text.delete(1.0, tk.END)
    
    def _save_log(self):
        """Save log to file"""
        log_content = self.log_text.get(1.0, tk.END)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"jhcis_sync_log_{timestamp}.txt"
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_name
        )
        
        if file_path:
            Path(file_path).write_text(log_content, encoding='utf-8')
            self._log(f"Log saved to {file_path}")
    
    def _open_folder(self):
        """Open application folder"""
        script_dir = get_app_dir()
        os.startfile(str(script_dir))
    
    def _open_log_folder(self):
        """Open log folder"""
        script_dir = get_app_dir()
        log_dir = script_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        os.startfile(str(log_dir))


def main():
    """Main entry point"""
    root = tk.Tk()
    
    # Set theme
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    # Create app
    app = JHCISyncApp(root)
    
    # Run
    root.mainloop()


if __name__ == "__main__":
    main()
