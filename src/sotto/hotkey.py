"""Hotkey string parsing for Windows RegisterHotKey API.

Parses human-readable strings like "ctrl+space", "ctrl+shift+f1",
"alt+d" into (modifiers, vk_code) tuples for RegisterHotKey.
"""

from __future__ import annotations

# Windows modifier flags for RegisterHotKey
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

MODIFIER_MAP: dict[str, int] = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}

# Virtual key codes — covers the keys people actually use for hotkeys
VK_MAP: dict[str, int] = {
    # Function keys
    **{f"f{i}": 0x70 + (i - 1) for i in range(1, 25)},  # F1–F24
    # Letter keys
    **{chr(c).lower(): c for c in range(0x41, 0x5B)},  # a–z → VK_A(0x41)–VK_Z(0x5A)
    # Number keys
    **{str(i): 0x30 + i for i in range(10)},  # 0–9
    # Named keys
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "escape": 0x1B,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "pause": 0x13,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    # Punctuation / symbols
    ";": 0xBA,
    "semicolon": 0xBA,
    "=": 0xBB,
    "equals": 0xBB,
    ",": 0xBC,
    "comma": 0xBC,
    "-": 0xBD,
    "minus": 0xBD,
    ".": 0xBE,
    "period": 0xBE,
    "/": 0xBF,
    "slash": 0xBF,
    "`": 0xC0,
    "backtick": 0xC0,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    "backslash": 0xDC,
    "'": 0xDE,
    "quote": 0xDE,
    # Numpad
    **{f"num{i}": 0x60 + i for i in range(10)},  # num0–num9
    "multiply": 0x6A,
    "add": 0x6B,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
}


def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse a hotkey string into (modifiers, vk_code).

    Args:
        hotkey_str: Human-readable hotkey like "ctrl+space" or "ctrl+shift+f1".
            Parts are separated by '+'. Case-insensitive. At least one modifier
            and exactly one key are required.

    Returns:
        Tuple of (modifier_flags, virtual_key_code) for RegisterHotKey.

    Raises:
        ValueError: If the string is malformed, has no modifier, or has an
            unrecognized key.
    """
    if not hotkey_str or not hotkey_str.strip():
        raise ValueError("Hotkey string cannot be empty")

    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    parts = [p for p in parts if p]  # drop empty from "ctrl+"

    if len(parts) < 2:
        raise ValueError(
            f"Hotkey must have at least one modifier and one key, got: '{hotkey_str}'"
        )

    modifiers = 0
    key_parts = []

    for part in parts:
        if part in MODIFIER_MAP:
            modifiers |= MODIFIER_MAP[part]
        else:
            key_parts.append(part)

    if modifiers == 0:
        raise ValueError(
            f"Hotkey must include at least one modifier (ctrl, alt, shift, win), "
            f"got: '{hotkey_str}'"
        )

    if len(key_parts) != 1:
        if len(key_parts) == 0:
            raise ValueError(f"Hotkey has no key, only modifiers: '{hotkey_str}'")
        raise ValueError(
            f"Hotkey must have exactly one key (got {len(key_parts)}: "
            f"{', '.join(key_parts)}): '{hotkey_str}'"
        )

    key_name = key_parts[0]
    vk_code = VK_MAP.get(key_name)
    if vk_code is None:
        raise ValueError(
            f"Unrecognized key: '{key_name}'. "
            f"Use a letter (a-z), number (0-9), function key (f1-f24), "
            f"or named key (space, enter, tab, etc.)"
        )

    return modifiers, vk_code


def format_hotkey(modifiers: int, vk_code: int) -> str:
    """Format (modifiers, vk_code) back to a human-readable string.

    Useful for display in UI and error messages.
    """
    parts = []
    if modifiers & MOD_CONTROL:
        parts.append("Ctrl")
    if modifiers & MOD_ALT:
        parts.append("Alt")
    if modifiers & MOD_SHIFT:
        parts.append("Shift")
    if modifiers & MOD_WIN:
        parts.append("Win")

    # Reverse lookup the key name
    key_name = None
    for name, code in VK_MAP.items():
        if code == vk_code:
            # Prefer the longer/clearer name for display
            if key_name is None or len(name) > len(key_name):
                key_name = name
    if key_name:
        parts.append(key_name.capitalize() if len(key_name) > 1 else key_name.upper())
    else:
        parts.append(f"0x{vk_code:02X}")

    return "+".join(parts)
