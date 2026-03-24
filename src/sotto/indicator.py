"""Transient recording indicator — translucent pill with waveform visualizer."""

from __future__ import annotations

import collections
import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Slot, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QCursor, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from sotto.main import AppState

# Pill dimensions
PILL_W = 160
PILL_H = 44
PILL_RADIUS = PILL_H // 2

# Waveform config
NUM_BARS = 20          # number of vertical bars in the visualizer
BAR_GAP = 1            # px between bars
WAVEFORM_LEFT = 38     # start x (after the dot)
WAVEFORM_RIGHT = PILL_W - 14  # end x
BAR_REGION_W = WAVEFORM_RIGHT - WAVEFORM_LEFT
BAR_W = max(1, (BAR_REGION_W - (NUM_BARS - 1) * BAR_GAP) // NUM_BARS)
MAX_BAR_H = (PILL_H - 8) // 2  # max half-height — tighter vertical margin for bigger bars

# Colors
COLOR_BG = QColor(20, 20, 24, 210)
COLOR_BG_BORDER = QColor(60, 60, 68, 120)

# Listening — warm red/coral gradient
COLOR_DOT = QColor(235, 60, 55)
COLOR_DOT_GLOW = QColor(235, 60, 55, 60)
COLOR_BAR_BASE = QColor(180, 40, 40)         # center of bar (dark)
COLOR_BAR_TIP = QColor(255, 100, 60)         # tip of bar (bright coral)
COLOR_BAR_PEAK = QColor(255, 180, 80)        # loudest bars get orange-gold tips
COLOR_BAR_TRACK = QColor(255, 255, 255, 18)  # ghost track

# Processing — cool blue wave
COLOR_WAVE_BASE = QColor(40, 120, 200)
COLOR_WAVE_TIP = QColor(100, 200, 255)
COLOR_WAVE_GLOW = QColor(80, 170, 255, 40)


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

        # Rolling level history for waveform (newest at the right)
        self._levels: collections.deque[float] = collections.deque(
            [0.0] * NUM_BARS, maxlen=NUM_BARS
        )
        # Smoothed display levels (for interpolation / decay)
        self._display_levels: list[float] = [0.0] * NUM_BARS

        # Animation timers
        self._phase: float = 0.0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)  # ~30fps
        self._anim_timer.timeout.connect(self._tick)

        # Dot pulse phase (subtle throb while listening)
        self._dot_phase: float = 0.0

    def show_for_state(self, state: AppState) -> None:
        """Show/hide and update appearance based on app state."""
        self._state = state.value
        self._level = 0.0

        if self._state in ("idle", "loading", "confirming"):
            self._anim_timer.stop()
            self.hide()
            return

        if self._state == "listening":
            # Reset waveform
            self._levels.clear()
            self._levels.extend([0.0] * NUM_BARS)
            self._display_levels = [0.0] * NUM_BARS
            self._dot_phase = 0.0

        self._phase = 0.0
        self._anim_timer.start()
        self._position_on_active_screen()
        self.show()
        self.update()

    @Slot(float)
    def update_level(self, level: float) -> None:
        """Push a new audio level sample into the waveform history."""
        if self._state != "listening":
            return
        self._level = level
        self._levels.append(level)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_pill_bg(painter)

            if self._state == "listening":
                self._paint_listening(painter)
            elif self._state == "processing":
                self._paint_processing(painter)
        finally:
            painter.end()

    def _paint_pill_bg(self, painter: QPainter) -> None:
        """Draw the rounded pill background with subtle border."""
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0.5, 0.5, PILL_W - 1, PILL_H - 1),
            PILL_RADIUS, PILL_RADIUS,
        )
        painter.fillPath(path, COLOR_BG)
        painter.setPen(QPen(COLOR_BG_BORDER, 1.0))
        painter.drawPath(path)

    def _paint_listening(self, painter: QPainter) -> None:
        """Red recording dot + mirrored waveform bars with gradient."""
        cy = PILL_H / 2.0

        # --- Recording dot with glow ---
        dot_r = 5.5 + 0.8 * math.sin(self._dot_phase)
        dot_cx = 20.0
        dot_cy = cy

        # Glow behind dot
        glow_r = dot_r + 4
        glow_grad = QLinearGradient(
            QPointF(dot_cx - glow_r, dot_cy),
            QPointF(dot_cx + glow_r, dot_cy),
        )
        glow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        glow_grad.setColorAt(0.3, COLOR_DOT_GLOW)
        glow_grad.setColorAt(0.7, COLOR_DOT_GLOW)
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QRectF(dot_cx - glow_r, dot_cy - glow_r, glow_r * 2, glow_r * 2)
        )

        # Dot
        painter.setBrush(COLOR_DOT)
        painter.drawEllipse(
            QRectF(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2)
        )

        # --- Waveform bars ---
        for i in range(NUM_BARS):
            target = self._levels[i] if i < len(self._levels) else 0.0
            # Smooth toward target (fast attack, slower decay)
            current = self._display_levels[i]
            if target > current:
                self._display_levels[i] = current + (target - current) * 0.6
            else:
                self._display_levels[i] = current + (target - current) * 0.15
            level = self._display_levels[i]

            bar_x = WAVEFORM_LEFT + i * (BAR_W + BAR_GAP)
            # Amplify so normal speech fills more of the range
            boosted = min(level * 1.5, 1.0)
            half_h = max(1.0, boosted * MAX_BAR_H)

            # Ghost track (faint background bar showing max range)
            track_half = MAX_BAR_H * 0.6
            painter.fillRect(
                QRectF(bar_x, cy - track_half, BAR_W, track_half * 2),
                COLOR_BAR_TRACK,
            )

            # Bar gradient: center is dark, tips are bright
            if boosted > 0.02:
                grad = QLinearGradient(
                    QPointF(bar_x, cy - half_h),
                    QPointF(bar_x, cy + half_h),
                )
                # Pick tip color based on intensity
                tip_color = (
                    COLOR_BAR_PEAK if boosted > 0.65
                    else COLOR_BAR_TIP
                )
                grad.setColorAt(0.0, tip_color)
                grad.setColorAt(0.4, COLOR_BAR_BASE)
                grad.setColorAt(0.6, COLOR_BAR_BASE)
                grad.setColorAt(1.0, tip_color)

                painter.fillRect(
                    QRectF(bar_x, cy - half_h, BAR_W, half_h * 2),
                    grad,
                )

    def _paint_processing(self, painter: QPainter) -> None:
        """Flowing sine wave across the pill — cool blue gradient."""
        cy = PILL_H / 2.0
        wave_left = 16.0
        wave_right = PILL_W - 16.0
        wave_w = wave_right - wave_left
        num_points = 60

        # Build wave path
        path = QPainterPath()
        points_top = []
        points_bot = []

        for i in range(num_points + 1):
            t = i / num_points
            x = wave_left + t * wave_w

            # Composite wave: main sine + harmonic + traveling component
            amplitude = 6.0 + 3.0 * math.sin(self._phase * 0.4 + t * math.pi)
            y_offset = (
                math.sin(self._phase + t * math.pi * 3.0) * amplitude
                + math.sin(self._phase * 1.7 + t * math.pi * 5.0) * amplitude * 0.3
            )

            # Taper at edges for clean look
            edge_fade = min(t * 5.0, (1.0 - t) * 5.0, 1.0)
            y_offset *= edge_fade

            points_top.append(QPointF(x, cy + y_offset))
            points_bot.append(QPointF(x, cy - y_offset))

        # Top wave
        path.moveTo(points_top[0])
        for pt in points_top[1:]:
            path.lineTo(pt)
        # Connect back along bottom wave (reversed) to form filled shape
        for pt in reversed(points_bot):
            path.lineTo(pt)
        path.closeSubpath()

        # Glow layer (wider, translucent)
        glow_pen = QPen(COLOR_WAVE_GLOW, 6.0)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(Qt.PenStyle.NoPen)

        # Fill with gradient
        grad = QLinearGradient(
            QPointF(wave_left, cy - 12),
            QPointF(wave_left, cy + 12),
        )
        grad.setColorAt(0.0, COLOR_WAVE_TIP)
        grad.setColorAt(0.35, COLOR_WAVE_BASE)
        grad.setColorAt(0.65, COLOR_WAVE_BASE)
        grad.setColorAt(1.0, COLOR_WAVE_TIP)

        # Glow behind
        glow_fill = QLinearGradient(
            QPointF(wave_left, cy - 16),
            QPointF(wave_left, cy + 16),
        )
        glow_fill.setColorAt(0.0, QColor(80, 170, 255, 0))
        glow_fill.setColorAt(0.3, COLOR_WAVE_GLOW)
        glow_fill.setColorAt(0.7, COLOR_WAVE_GLOW)
        glow_fill.setColorAt(1.0, QColor(80, 170, 255, 0))
        painter.fillPath(path, glow_fill)

        # Main wave fill
        painter.fillPath(path, grad)

        # Bright center line
        center_path = QPainterPath()
        center_path.moveTo(points_top[0])
        for pt in points_top[1:]:
            center_path.lineTo(pt)
        painter.setPen(QPen(QColor(180, 220, 255, 160), 1.2))
        painter.drawPath(center_path)

    def _tick(self) -> None:
        """Advance animation phase and repaint."""
        TWO_PI = 2.0 * math.pi
        self._phase = (self._phase + 0.08) % (TWO_PI * 100)
        self._dot_phase = (self._dot_phase + 0.12) % TWO_PI
        self.update()

    def closeEvent(self, event) -> None:
        self._anim_timer.stop()
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
