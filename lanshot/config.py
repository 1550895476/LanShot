from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME = "LanShot"


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / APP_NAME


@dataclass
class Settings:
    token: str
    preferred_port: int = 8765
    first_run: bool = True
    keep_images: int = 30

    @classmethod
    def load(cls, path: Path | None = None) -> tuple["Settings", Path]:
        config_path = path or app_data_dir() / "config.json"
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            settings = cls(
                token=str(raw["token"]),
                preferred_port=int(raw.get("preferred_port", 8765)),
                first_run=bool(raw.get("first_run", False)),
                keep_images=max(1, int(raw.get("keep_images", 30))),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            settings = cls(token=secrets.token_urlsafe(18))
            settings.save(config_path)
        return settings, config_path

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else Path(sys.executable)
    main_file = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{launcher}" "{main_file}"'
