"""System tray icon with state-driven colors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from sotto.main import AppState

# State colors
COLORS = {
    "idle": QColor(100, 100, 100),       # Gray — dormant
    "listening": QColor(220, 50, 50),     # Red — recording
    "processing": QColor(50, 150, 220),   # Blue — thinking
}

TOOLTIPS = {
    "idle": "Sotto — Ready (Ctrl+Space)",
    "listening": "Sotto — Listening...",
    "processing": "Sotto — Transcribing...",
}


def _make_icon(color: QColor, level: float = 0.0) -> QIcon:
    """Generate a simple colored circle icon.

    Args:
        color: Fill color for the circle.
        level: Audio level (0.0–1.0) — scales inner circle for visual feedback.
    """
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent background

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    painter.setPen(color.darker(120))

    # Base circle
    margin = 4
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

    # Inner level indicator (brighter, scaled by audio level)
    if level > 0.05:
        inner_size = int((size - 2 * margin) * 0.4 * level)
        if inner_size > 2:
            painter.setBrush(color.lighter(150))
            painter.setPen(color.lighter(150))
            offset = (size - inner_size) // 2
            painter.drawEllipse(offset, offset, inner_size, inner_size)

    painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    """System tray icon with state-driven appearance."""

    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_state = "idle"
        self._level = 0.0

        # Context menu — store reference to prevent GC
        self._menu = QMenu()
        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)
        self.setContextMenu(self._menu)

        # Initial icon
        self.setIcon(_make_icon(COLORS["idle"]))
        self.setToolTip(TOOLTIPS["idle"])

    def update_state(self, state: AppState) -> None:
        """Update icon color and tooltip based on app state."""
        self._current_state = state.value
        self._level = 0.0
        self.setIcon(_make_icon(COLORS[state.value]))
        self.setToolTip(TOOLTIPS[state.value])

    @Slot(float)
    def update_level(self, level: float) -> None:
        """Update icon with audio level (only during LISTENING)."""
        if self._current_state != "listening":
            return
        # Throttle icon updates — only redraw if level changed noticeably
        if abs(level - self._level) > 0.1:
            self._level = level
            self.setIcon(_make_icon(COLORS["listening"], level))
