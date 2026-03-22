"""Transient recording indicator — translucent pill overlay."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from sotto.main import AppState

# Pill dimensions
PILL_W = 120
PILL_H = 36
PILL_RADIUS = PILL_H // 2

# Colors (match tray.py)
COLOR_BG = QColor(0, 0, 0, 180)
COLOR_RED = QColor(220, 50, 50)
COLOR_BLUE = QColor(50, 150, 220)
COLOR_TRACK = QColor(255, 255, 255, 40)


class RecordingIndicator(QWidget):
    """Click-through translucent pill shown during LISTENING/PROCESSING."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(PILL_W, PILL_H)

        self._state: str = "idle"
        self._level: float = 0.0

        # Pulse animation for PROCESSING state
        self._phase: float = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._tick_pulse)

    def show_for_state(self, state: AppState) -> None:
        """Show/hide and update appearance based on app state."""
        self._state = state.value
        self._level = 0.0

        if self._state == "idle":
            self._pulse_timer.stop()
            self.hide()
            return

        if self._state == "processing":
            self._phase = 0.0
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()

        self._position_on_active_screen()
        self.show()
        self.update()

    @Slot(float)
    def update_level(self, level: float) -> None:
        """Update audio level bar during LISTENING."""
        if self._state != "listening":
            return
        self._level = level
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Pill background
            path = QPainterPath()
            path.addRoundedRect(0, 0, PILL_W, PILL_H, PILL_RADIUS, PILL_RADIUS)
            painter.fillPath(path, COLOR_BG)

            if self._state == "listening":
                self._paint_listening(painter)
            elif self._state == "processing":
                self._paint_processing(painter)
        finally:
            painter.end()

    def _paint_listening(self, painter: QPainter) -> None:
        """Red dot (left) + level bar (right)."""
        # Red dot
        dot_r = 6
        dot_cx = 18
        dot_cy = PILL_H // 2
        painter.setBrush(COLOR_RED)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2)

        # Level bar track
        bar_x = 34
        bar_w = PILL_W - bar_x - 12
        bar_h = 6
        bar_y = (PILL_H - bar_h) // 2
        painter.fillRect(bar_x, bar_y, bar_w, bar_h, COLOR_TRACK)

        # Level bar fill
        if self._level > 0.02:
            fill_w = int(bar_w * min(self._level, 1.0))
            painter.fillRect(bar_x, bar_y, fill_w, bar_h, COLOR_RED)

    def _paint_processing(self, painter: QPainter) -> None:
        """Pulsing blue dot (center)."""
        # Sine oscillation: radius 4–8px, alpha 140–255
        t = math.sin(self._phase)
        dot_r = 4 + 4 * (0.5 + 0.5 * t)
        alpha = int(140 + 115 * (0.5 + 0.5 * t))

        color = QColor(COLOR_BLUE)
        color.setAlpha(alpha)

        cx = PILL_W // 2
        cy = PILL_H // 2
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx - dot_r), int(cy - dot_r),
                            int(dot_r * 2), int(dot_r * 2))

    def _tick_pulse(self) -> None:
        """Advance pulse phase (~2s cycle at 50ms interval)."""
        self._phase += 0.16  # ~39 ticks per full cycle (2*pi / 0.16)
        self.update()

    def closeEvent(self, event) -> None:
        self._pulse_timer.stop()
        super().closeEvent(event)

    def _position_on_active_screen(self) -> None:
        """Position at center-lower-third of the screen containing the cursor."""
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()

        x = geo.x() + (geo.width() - PILL_W) // 2
        y = geo.y() + geo.height() * 2 // 3
        self.move(x, y)
