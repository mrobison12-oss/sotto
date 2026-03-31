"""Auto-paste: simulate Ctrl+V to inject clipboard text into the active window."""

import ctypes
import ctypes.wintypes
import logging
import sys

logger = logging.getLogger("sotto")

if sys.platform == "win32":
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0x11
    VK_V = 0x56

    # ULONG_PTR is pointer-sized: 8 bytes on 64-bit, 4 bytes on 32-bit
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.wintypes.LONG),
            ("dy", ctypes.wintypes.LONG),
            ("mouseData", ctypes.wintypes.DWORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

        _anonymous_ = ("_input",)
        _fields_ = [
            ("type", ctypes.wintypes.DWORD),
            ("_input", _INPUT),
        ]

    def _make_key_input(vk: int, flags: int = 0) -> INPUT:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        return inp

    def simulate_paste() -> None:
        """Simulate Ctrl+V keystroke. Caller is responsible for any delay."""
        inputs = (INPUT * 4)(
            _make_key_input(VK_CONTROL),               # Ctrl down
            _make_key_input(VK_V),                      # V down
            _make_key_input(VK_V, KEYEVENTF_KEYUP),     # V up
            _make_key_input(VK_CONTROL, KEYEVENTF_KEYUP),  # Ctrl up
        )
        sent = ctypes.windll.user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
        if sent != 4:
            logger.warning("SendInput returned %d (expected 4)", sent)

else:
    def simulate_paste() -> None:
        """Stub for non-Windows platforms — macOS implementation TBD."""
        logger.warning("Auto-paste not yet implemented on %s", sys.platform)
