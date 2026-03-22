#!/usr/bin/env python3
"""Windows Service host for scheduled JHCIS sync jobs."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import servicemanager
import win32event
import win32service
import win32serviceutil

from sync_agent import (
    SUMMARY_TYPES,
    get_app_dir,
    load_env_config,
    load_env_file,
    run_sync,
)


SERVICE_NAME = "JHCISSyncService"
SERVICE_DISPLAY_NAME = "JHCIS Sync Service"
SERVICE_DESCRIPTION = "Runs scheduled JHCIS summary sync jobs in the background."


def load_schedule_settings(settings_file: Path) -> Dict[str, Any]:
    if not settings_file.exists():
        return {
            "enabled": False,
            "time": "08:00",
            "use_today_date": True,
        }

    try:
        payload = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "enabled": False,
            "time": "08:00",
            "use_today_date": True,
        }

    return {
        "enabled": bool(payload.get("enabled", False)),
        "time": str(payload.get("time", "08:00")).strip(),
        "use_today_date": bool(payload.get("use_today_date", True)),
    }


def normalize_schedule_time(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%H:%M")
    return parsed.strftime("%H:%M")


class JHCISSyncService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args: Any) -> None:
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.app_dir = get_app_dir()
        self.state_file = self.app_dir / "service_state.json"
        self.logger = self._create_logger()
        self.last_run_key = self._load_last_run_key()

    def SvcStop(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)
        self.logger.info("Service stop requested")

    def SvcDoRun(self) -> None:
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} started")
        self.logger.info("Service started")
        self.main()

    def main(self) -> None:
        while self.running:
            try:
                self._scheduler_tick()
            except Exception as exc:  # pragma: no cover - service guard rail
                self.logger.exception(f"Service loop error: {exc}")
                servicemanager.LogErrorMsg(f"{SERVICE_NAME} loop error: {exc}")

            rc = win32event.WaitForSingleObject(self.stop_event, 30000)
            if rc == win32event.WAIT_OBJECT_0:
                break

        self.logger.info("Service stopped")
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopped")

    def _create_logger(self) -> logging.Logger:
        log_dir = self.app_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        logger = logging.getLogger("jhcis_sync_service")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        file_handler = logging.FileHandler(log_dir / "service.log", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
        return logger

    def _load_last_run_key(self) -> str:
        if not self.state_file.exists():
            return ""

        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""

        return str(payload.get("last_run_key", ""))

    def _save_last_run_key(self, value: str) -> None:
        self.state_file.write_text(
            json.dumps({"last_run_key": value}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        self.last_run_key = value

    def _scheduler_tick(self) -> None:
        env_file = self.app_dir / ".env"
        load_env_file(env_file)
        config = load_env_config()
        settings = load_schedule_settings(self.app_dir / "scheduler_settings.json")

        if not settings["enabled"]:
            return

        schedule_time = normalize_schedule_time(settings["time"])
        now = datetime.now()
        schedule_key = f"{now.strftime('%Y-%m-%d')} {schedule_time}"

        if now.strftime("%H:%M") != schedule_time:
            return

        if self.last_run_key == schedule_key:
            return

        date_value = now.strftime("%Y-%m-%d") if settings["use_today_date"] else now.strftime("%Y-%m-%d")
        log_dir = self.app_dir / "logs"
        log_dir.mkdir(exist_ok=True)

        self.logger.info(f"Scheduled sync started for {schedule_key}")
        results = run_sync(
            date=date_value,
            summary_types=SUMMARY_TYPES,
            config=config,
            log_dir=log_dir,
        )
        success_count = sum(1 for value in results.values() if value)
        self.logger.info(f"Scheduled sync completed: {success_count}/{len(results)} successful")
        self._save_last_run_key(schedule_key)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(JHCISSyncService)
