"""System tray icon with state-driven colors, history, and settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from sotto.config import SottoConfig
    from sotto.history import TranscriptionHistory
    from sotto.main import AppState

# State colors
COLORS = {
    "loading": QColor(180, 140, 50),      # Amber — loading
    "idle": QColor(100, 100, 100),        # Gray — dormant
    "listening": QColor(220, 50, 50),     # Red — recording
    "processing": QColor(50, 150, 220),   # Blue — thinking
    "confirming": QColor(100, 100, 100),  # Gray — preview open, functionally idle
}

def _make_tooltips(hotkey_display: str = "Ctrl+Space") -> dict[str, str]:
    return {
        "loading": "Sotto — Loading model...",
        "idle": f"Sotto — Ready ({hotkey_display})",
        "listening": "Sotto — Listening...",
        "processing": "Sotto — Transcribing...",
        "confirming": f"Sotto — Review transcription ({hotkey_display})",
    }

TOOLTIPS = _make_tooltips()


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
    try:
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
    finally:
        painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    """System tray icon with state-driven appearance, history, and settings."""

    quit_requested = Signal()
    settings_requested = Signal()

    def __init__(self, history: TranscriptionHistory, hotkey_display: str = "Ctrl+Space", parent=None):
        super().__init__(parent)
        self._current_state = "idle"
        self._level = 0.0
        self._history = history
        self._tooltips = _make_tooltips(hotkey_display)

        # Build context menu
        self._menu = QMenu()
        self._history_menu = self._menu.addMenu("History")
        self._history_menu.setEnabled(False)
        self._menu.addSeparator()
        settings_action = self._menu.addAction("Settings...")
        settings_action.triggered.connect(self.settings_requested.emit)
        self._menu.addSeparator()
        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)
        self.setContextMenu(self._menu)

        # Initial icon
        self.setIcon(_make_icon(COLORS["idle"]))
        self.setToolTip(self._tooltips["idle"])

    def update_state(self, state: AppState) -> None:
        """Update icon color and tooltip based on app state."""
        self._current_state = state.value
        self._level = 0.0
        self.setIcon(_make_icon(COLORS[state.value]))
        self.setToolTip(self._tooltips[state.value])

    @Slot(float)
    def update_level(self, level: float) -> None:
        """Update icon with audio level (only during LISTENING)."""
        if self._current_state != "listening":
            return
        # Throttle icon updates — only redraw if level changed noticeably
        if abs(level - self._level) > 0.1:
            self._level = level
            self.setIcon(_make_icon(COLORS["listening"], level))

    def show_toast(self, title: str, message: str, duration_ms: int = 3000) -> None:
        """Show a native desktop notification."""
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, duration_ms)

    def refresh_history(self) -> None:
        """Rebuild the history submenu from current entries."""
        self._history_menu.clear()
        entries = self._history.entries
        if not entries:
            self._history_menu.setEnabled(False)
            return

        self._history_menu.setEnabled(True)
        for entry in entries:
            ts = entry.timestamp.strftime("%H:%M:%S")
            label = f"[{ts}] {entry.text[:60]}{'...' if len(entry.text) > 60 else ''}"
            action = self._history_menu.addAction(label)
            # Capture text in closure
            text = entry.text
            action.triggered.connect(lambda checked=False, t=text: self._copy_to_clipboard(t))

    def _copy_to_clipboard(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
