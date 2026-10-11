from __future__ import annotations

import ctypes
import io

from PIL import Image

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_DIB = 8
GMEM_MOVEABLE = 0x0002


def copy_image_to_clipboard(image: Image.Image) -> None:
    stream = io.BytesIO()
    image.convert("RGB").save(stream, format="BMP")
    data = stream.getvalue()[14:]
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("无法分配剪贴板内存")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise OSError("无法锁定剪贴板内存")
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise OSError("剪贴板正被其他程序占用")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_DIB, handle):
            raise OSError("写入剪贴板失败")
        handle = None
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)
