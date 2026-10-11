from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class ScreenshotRecord:
    image_id: int
    path: Path
    width: int
    height: int
    created_at: float


class ScreenshotStore:
    def __init__(self, directory: Path, keep: int = 30) -> None:
        self.directory = directory
        self.keep = max(1, keep)
        self._lock = threading.RLock()
        self._records: dict[int, ScreenshotRecord] = {}
        self._latest_id = 0
        directory.mkdir(parents=True, exist_ok=True)

    def publish(self, image: Image.Image) -> ScreenshotRecord:
        with self._lock:
            self._latest_id = max(self._latest_id + 1, int(time.time_ns() // 1_000_000))
            image_id = self._latest_id
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = self.directory / f"LanShot-{stamp}-{image_id % 1000:03d}.png"
            temp = path.with_suffix(".tmp")
            image.save(temp, format="PNG", optimize=True)
            os.replace(temp, path)
            record = ScreenshotRecord(image_id, path, image.width, image.height, time.time())
            self._records[image_id] = record
            self._cleanup_locked()
            return record

    def latest(self) -> ScreenshotRecord | None:
        with self._lock:
            return self._records.get(self._latest_id)

    def get(self, image_id: int) -> ScreenshotRecord | None:
        with self._lock:
            return self._records.get(image_id)

    def _cleanup_locked(self) -> None:
        ordered = sorted(self._records)
        for image_id in ordered[:-self.keep]:
            record = self._records.pop(image_id)
            try:
                record.path.unlink(missing_ok=True)
            except OSError:
                pass
