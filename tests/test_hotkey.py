"""Tests for the hotkey string parser."""

import pytest

from sotto.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    format_hotkey,
    parse_hotkey,
)


class TestParseHotkey:
    def test_ctrl_space(self):
        mod, vk = parse_hotkey("ctrl+space")
        assert mod == MOD_CONTROL
        assert vk == 0x20

    def test_case_insensitive(self):
        mod, vk = parse_hotkey("Ctrl+Space")
        assert mod == MOD_CONTROL
        assert vk == 0x20

    def test_ctrl_shift_f1(self):
        mod, vk = parse_hotkey("ctrl+shift+f1")
        assert mod == MOD_CONTROL | MOD_SHIFT
        assert vk == 0x70  # F1

    def test_alt_d(self):
        mod, vk = parse_hotkey("alt+d")
        assert mod == MOD_ALT
        assert vk == ord("D")  # Windows VK codes use uppercase

    def test_ctrl_alt_shift_win(self):
        mod, vk = parse_hotkey("ctrl+alt+shift+win+a")
        assert mod == MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN

    def test_control_alias(self):
        mod, vk = parse_hotkey("control+space")
        assert mod == MOD_CONTROL

    def test_super_alias(self):
        mod, vk = parse_hotkey("super+e")
        assert mod == MOD_WIN

    def test_number_key(self):
        mod, vk = parse_hotkey("ctrl+5")
        assert vk == 0x35

    def test_function_key_f12(self):
        mod, vk = parse_hotkey("ctrl+f12")
        assert vk == 0x7B  # F12

    def test_enter_key(self):
        mod, vk = parse_hotkey("ctrl+enter")
        assert vk == 0x0D

    def test_return_alias(self):
        mod, vk = parse_hotkey("ctrl+return")
        assert vk == 0x0D

    def test_whitespace_tolerance(self):
        mod, vk = parse_hotkey("  ctrl + space  ")
        assert mod == MOD_CONTROL
        assert vk == 0x20

    # --- Error cases ---

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_hotkey("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_hotkey("   ")

    def test_no_modifier_raises(self):
        with pytest.raises(ValueError, match="modifier"):
            parse_hotkey("space")

    def test_single_key_raises(self):
        with pytest.raises(ValueError, match="modifier"):
            parse_hotkey("f1")

    def test_modifiers_only_raises(self):
        with pytest.raises(ValueError, match="no key"):
            parse_hotkey("ctrl+shift")

    def test_two_non_modifier_keys_raises(self):
        with pytest.raises(ValueError, match="exactly one key"):
            parse_hotkey("ctrl+a+b")

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unrecognized key"):
            parse_hotkey("ctrl+notakey")


class TestFormatHotkey:
    def test_ctrl_space(self):
        result = format_hotkey(MOD_CONTROL, 0x20)
        assert result == "Ctrl+Space"

    def test_ctrl_shift_f1(self):
        result = format_hotkey(MOD_CONTROL | MOD_SHIFT, 0x70)
        assert "Ctrl" in result
        assert "Shift" in result

    def test_roundtrip(self):
        """parse → format should produce a readable version of the original."""
        mod, vk = parse_hotkey("alt+shift+f5")
        display = format_hotkey(mod, vk)
        assert "Alt" in display
        assert "Shift" in display

    def test_unknown_vk_shows_hex(self):
        result = format_hotkey(MOD_CONTROL, 0xFF)
        assert "0xFF" in result
