from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from lanshot.config import Settings
from lanshot.server import MobileServer
from lanshot.store import ScreenshotStore


class SettingsTests(unittest.TestCase):
    def test_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            settings, actual = Settings.load(path)
            self.assertEqual(actual, path)
            self.assertTrue(settings.token)
            settings.first_run = False
            settings.save(path)
            loaded, _ = Settings.load(path)
            self.assertFalse(loaded.first_run)
            self.assertEqual(loaded.token, settings.token)


class StoreTests(unittest.TestCase):
    def test_publish_and_retention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenshotStore(Path(directory), keep=2)
            records = [store.publish(Image.new("RGB", (10 + i, 8), "red")) for i in range(3)]
            self.assertIsNone(store.get(records[0].image_id))
            self.assertFalse(records[0].path.exists())
            self.assertEqual(store.latest(), records[-1])
            self.assertTrue(records[-1].path.exists())


class ServerTests(unittest.TestCase):
    def test_pairing_page_status_and_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenshotStore(Path(directory))
            record = store.publish(Image.new("RGB", (17, 11), "blue"))
            server = MobileServer(store, "test-token", 0)
            server.start()
            try:
                base = f"http://127.0.0.1:{server.port}"
                with urllib.request.urlopen(base + "/?token=test-token", timeout=3) as response:
                    self.assertIn("LanShot", response.read().decode("utf-8"))
                with urllib.request.urlopen(base + "/api/status?token=test-token", timeout=3) as response:
                    payload = json.load(response)
                    self.assertEqual(payload["latest"]["id"], record.image_id)
                with urllib.request.urlopen(
                    base + f"/image/{record.image_id}.png?token=test-token", timeout=3
                ) as response:
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                    self.assertTrue(response.read().startswith(b"\x89PNG"))
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(base + "/api/status?token=wrong", timeout=3)
                self.assertEqual(denied.exception.code, 403)
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
