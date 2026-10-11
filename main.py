from __future__ import annotations

import ctypes

# Make multi-monitor captures use physical pixels instead of DPI-scaled coordinates.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass

from lanshot.app import run


if __name__ == "__main__":
    raise SystemExit(run())
