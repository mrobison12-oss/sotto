"""Tests for the RecordingIndicator widget.

Import strategy: sotto.main triggers CUDA initialization at module scope
(ensure_cuda_dlls() is called on import). AppState is therefore defined
locally here with matching string values so we never import sotto.main.
indicator.py uses TYPE_CHECKING for its AppState import, so the real
widget accepts any object whose .value is a string — our local enum is
fully compatible.
"""

from __future__ import annotations

import enum
import math
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sotto.indicator import PILL_H, PILL_W, NUM_BARS, RecordingIndicator


# ---------------------------------------------------------------------------
# Local AppState — mirrors sotto.main.AppState without triggering CUDA import
# ---------------------------------------------------------------------------

class AppState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def indicator(qtbot):
    """Construct a RecordingIndicator and register it with qtbot for cleanup."""
    widget = RecordingIndicator()
    qtbot.addWidget(widget)
    return widget


# ---------------------------------------------------------------------------
# Widget lifecycle
# ---------------------------------------------------------------------------

class TestWidgetLifecycle:
    def test_starts_hidden(self, indicator):
        assert not indicator.isVisible()

    def test_listening_shows_widget(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        assert indicator.isVisible()

    def test_processing_shows_widget(self, indicator):
        indicator.show_for_state(AppState.PROCESSING)
        assert indicator.isVisible()

    def test_idle_hides_widget(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        assert indicator.isVisible()

        indicator.show_for_state(AppState.IDLE)
        assert not indicator.isVisible()

    def test_full_cycle_listening_processing_idle(self, indicator):
        """Drive through the complete recording lifecycle."""
        indicator.show_for_state(AppState.LISTENING)
        assert indicator.isVisible()
        assert indicator._state == "listening"

        indicator.show_for_state(AppState.PROCESSING)
        assert indicator.isVisible()
        assert indicator._state == "processing"

        indicator.show_for_state(AppState.IDLE)
        assert not indicator.isVisible()
        assert indicator._state == "idle"

    def test_idle_from_cold_start_stays_hidden(self, indicator):
        indicator.show_for_state(AppState.IDLE)
        assert not indicator.isVisible()


# ---------------------------------------------------------------------------
# Visual state — _level tracking
# ---------------------------------------------------------------------------

class TestVisualState:
    def test_update_level_stored_during_listening(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        indicator.update_level(0.75)
        assert indicator._level == pytest.approx(0.75)

    def test_update_level_ignored_when_processing(self, indicator):
        indicator.show_for_state(AppState.PROCESSING)
        indicator.update_level(0.5)
        assert indicator._level == pytest.approx(0.0)

    def test_update_level_ignored_when_idle(self, indicator):
        indicator.update_level(0.9)
        assert indicator._level == pytest.approx(0.0)

    def test_update_level_ignored_after_transition_to_processing(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        indicator.update_level(0.6)
        assert indicator._level == pytest.approx(0.6)

        indicator.show_for_state(AppState.PROCESSING)
        # Level resets to 0.0 on state change, and update_level is ignored
        assert indicator._level == pytest.approx(0.0)
        indicator.update_level(0.9)
        assert indicator._level == pytest.approx(0.0)

    def test_level_stores_raw_value_above_one(self, indicator):
        """_level stores the raw value; clamping happens in paintEvent via min()."""
        indicator.show_for_state(AppState.LISTENING)
        indicator.update_level(1.5)
        assert indicator._level == pytest.approx(1.5)

    def test_level_zero_default(self, indicator):
        assert indicator._level == pytest.approx(0.0)

    def test_update_level_appends_to_history(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        indicator.update_level(0.5)
        indicator.update_level(0.8)
        # Last two values should be at the end of the deque
        levels = list(indicator._levels)
        assert levels[-1] == pytest.approx(0.8)
        assert levels[-2] == pytest.approx(0.5)

    def test_level_history_resets_on_listening_entry(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        indicator.update_level(0.9)
        # Re-enter listening — history should reset
        indicator.show_for_state(AppState.IDLE)
        indicator.show_for_state(AppState.LISTENING)
        assert all(v == 0.0 for v in indicator._levels)

    def test_level_history_maxlen(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        for i in range(NUM_BARS + 10):
            indicator.update_level(float(i) / (NUM_BARS + 10))
        assert len(indicator._levels) == NUM_BARS


# ---------------------------------------------------------------------------
# Animation timer
# ---------------------------------------------------------------------------

class TestAnimTimer:
    def test_timer_starts_on_processing(self, indicator):
        indicator.show_for_state(AppState.PROCESSING)
        assert indicator._anim_timer.isActive()

    def test_timer_starts_on_listening(self, indicator):
        indicator.show_for_state(AppState.LISTENING)
        assert indicator._anim_timer.isActive()

    def test_timer_stops_on_idle(self, indicator):
        indicator.show_for_state(AppState.PROCESSING)
        assert indicator._anim_timer.isActive()

        indicator.show_for_state(AppState.IDLE)
        assert not indicator._anim_timer.isActive()

    def test_timer_not_running_initially(self, indicator):
        assert not indicator._anim_timer.isActive()

    def test_timer_interval_is_33ms(self, indicator):
        """~30fps animation loop."""
        assert indicator._anim_timer.interval() == 33

    def test_phase_resets_on_processing_entry(self, indicator):
        indicator.show_for_state(AppState.PROCESSING)
        indicator._phase = 2.5
        # Re-enter PROCESSING — phase should reset
        indicator.show_for_state(AppState.IDLE)
        indicator.show_for_state(AppState.PROCESSING)
        assert indicator._phase == pytest.approx(0.0)

    def test_tick_advances_phase(self, indicator):
        indicator.show_for_state(AppState.PROCESSING)
        phase_before = indicator._phase
        indicator._tick()
        assert indicator._phase > phase_before

    def test_tick_phase_increment_value(self, indicator):
        indicator._tick()
        assert indicator._phase == pytest.approx(0.08)


# ---------------------------------------------------------------------------
# Multi-monitor positioning
# ---------------------------------------------------------------------------

class TestPositioning:
    def _make_mock_screen(self, x, y, w, h):
        screen = MagicMock()
        geo = MagicMock()
        geo.x.return_value = x
        geo.y.return_value = y
        geo.width.return_value = w
        geo.height.return_value = h
        screen.availableGeometry.return_value = geo
        return screen

    def test_position_center_lower_third(self, indicator):
        mock_screen = self._make_mock_screen(0, 0, 1920, 1080)
        with patch.object(QApplication, "screenAt", return_value=mock_screen):
            indicator.show_for_state(AppState.LISTENING)

        pos = indicator.pos()
        assert pos.x() == (1920 - PILL_W) // 2
        assert pos.y() == 1080 * 2 // 3

    def test_fallback_to_primary_when_screen_at_returns_none(self, indicator):
        mock_screen = self._make_mock_screen(0, 0, 2560, 1440)
        with patch.object(QApplication, "screenAt", return_value=None), \
             patch.object(QApplication, "primaryScreen", return_value=mock_screen):
            indicator.show_for_state(AppState.LISTENING)

        pos = indicator.pos()
        assert pos.x() == (2560 - PILL_W) // 2
        assert pos.y() == 1440 * 2 // 3

    def test_position_accounts_for_screen_offset(self, indicator):
        """Second monitor with x-offset of 1920."""
        mock_screen = self._make_mock_screen(1920, 0, 2560, 1440)
        with patch.object(QApplication, "screenAt", return_value=mock_screen):
            indicator.show_for_state(AppState.LISTENING)

        pos = indicator.pos()
        assert pos.x() == 1920 + (2560 - PILL_W) // 2
        assert pos.y() == 1440 * 2 // 3

    def test_position_not_called_for_idle(self, indicator):
        with patch.object(indicator, "_position_on_active_screen") as mock_pos:
            indicator.show_for_state(AppState.IDLE)
            mock_pos.assert_not_called()


# ---------------------------------------------------------------------------
# Window flags and attributes
# ---------------------------------------------------------------------------

class TestWindowFlags:
    def test_frameless_window_hint(self, indicator):
        assert indicator.windowFlags() & Qt.WindowType.FramelessWindowHint

    def test_window_stays_on_top_hint(self, indicator):
        assert indicator.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    def test_tool_flag(self, indicator):
        assert indicator.windowFlags() & Qt.WindowType.Tool

    def test_window_transparent_for_input(self, indicator):
        assert indicator.windowFlags() & Qt.WindowType.WindowTransparentForInput

    def test_wa_translucent_background(self, indicator):
        assert indicator.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def test_fixed_size(self, indicator):
        assert indicator.width() == PILL_W
        assert indicator.height() == PILL_H


# ---------------------------------------------------------------------------
# Config integration — _update_state logic from main.py
# ---------------------------------------------------------------------------

class TestConfigIntegration:
    """Tests for the show_indicator config guard in SottoApp._update_state.

    Replicates the branching logic from main.py:240-246 directly against
    the widget, since importing SottoApp triggers CUDA/hotkey initialization.
    """

    def _simulate_update_state(self, indicator, state, show_indicator):
        if show_indicator:
            indicator.show_for_state(state)
        elif state == AppState.IDLE:
            indicator.hide()

    def test_shown_when_enabled_listening(self, indicator):
        self._simulate_update_state(indicator, AppState.LISTENING, show_indicator=True)
        assert indicator.isVisible()

    def test_shown_when_enabled_processing(self, indicator):
        self._simulate_update_state(indicator, AppState.PROCESSING, show_indicator=True)
        assert indicator.isVisible()

    def test_hidden_when_enabled_idle(self, indicator):
        self._simulate_update_state(indicator, AppState.LISTENING, show_indicator=True)
        self._simulate_update_state(indicator, AppState.IDLE, show_indicator=True)
        assert not indicator.isVisible()

    def test_not_shown_when_disabled_listening(self, indicator):
        self._simulate_update_state(indicator, AppState.LISTENING, show_indicator=False)
        assert not indicator.isVisible()

    def test_not_shown_when_disabled_processing(self, indicator):
        self._simulate_update_state(indicator, AppState.PROCESSING, show_indicator=False)
        assert not indicator.isVisible()

    def test_hidden_on_idle_even_when_disabled(self, indicator):
        """Covers mid-session toggle: widget may be visible from before the toggle."""
        indicator.show()
        self._simulate_update_state(indicator, AppState.IDLE, show_indicator=False)
        assert not indicator.isVisible()
