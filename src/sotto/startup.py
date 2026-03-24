"""Windows startup management — add/remove Sotto from auto-start."""

import logging
import os
import shutil
import sys

logger = logging.getLogger("sotto")

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_NAME = "Sotto"


def _get_sotto_command() -> str:
    """Get the command to launch Sotto.

    Prefers a .exe entry point (reliable without venv activation);
    falls back to 'pythonw -m sotto' using the current interpreter.
    Uses pythonw to avoid a console window flash on startup.
    """
    sotto_exe = shutil.which("sotto")
    # Only use the found binary if it's a .exe (not a script wrapper)
    if sotto_exe and sotto_exe.lower().endswith(".exe"):
        return f'"{sotto_exe}"'
    # Use pythonw if available (no console window), fall back to python
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{interpreter}" -m sotto'


def set_startup_enabled(enabled: bool) -> bool:
    """Add or remove Sotto from Windows startup. Returns True on success."""
    if sys.platform != "win32":
        logger.warning("Startup management only supported on Windows")
        return False

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                cmd = _get_sotto_command()
                winreg.SetValueEx(key, _REG_NAME, 0, winreg.REG_SZ, cmd)
                logger.info("Added Sotto to Windows startup: %s", cmd)
            else:
                try:
                    winreg.DeleteValue(key, _REG_NAME)
                    logger.info("Removed Sotto from Windows startup")
                except FileNotFoundError:
                    pass  # already absent
        finally:
            winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error("Failed to update Windows startup: %s", e)
        return False


def is_startup_enabled() -> bool:
    """Check if Sotto is in the Windows startup registry."""
    if sys.platform != "win32":
        return False

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, _REG_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False
