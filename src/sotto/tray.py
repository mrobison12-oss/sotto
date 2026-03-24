"""System tray icon with history and settings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from sotto.history import TranscriptionHistory
    from sotto.main import AppState

# Asset paths
_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
_ICON_64 = _ASSETS / "icon_64.png"
_ICON_16 = _ASSETS / "icon_16.png"


def _make_tooltips(hotkey_display: str = "Ctrl+Space") -> dict[str, str]:
    return {
        "loading": "Sotto — Loading model...",
        "idle": f"Sotto — Ready ({hotkey_display})",
        "listening": "Sotto — Listening...",
        "processing": "Sotto — Transcribing...",
        "confirming": f"Sotto — Review transcription ({hotkey_display})",
    }


def _load_icon() -> QIcon:
    """Load the Sotto icon from assets, falling back to a generated purple circle."""
    if _ICON_64.exists():
        icon = QIcon(str(_ICON_64))
        if _ICON_16.exists():
            icon.addFile(str(_ICON_16))
        return icon
    # Fallback: purple circle (no assets available)
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(140, 80, 220)
        painter.setBrush(color)
        painter.setPen(color.darker(120))
        margin = 4
        painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    finally:
        painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    """System tray icon with history and settings."""

    quit_requested = Signal()
    settings_requested = Signal()

    def __init__(self, history: TranscriptionHistory, hotkey_display: str = "Ctrl+Space", parent=None):
        super().__init__(parent)
        self._current_state = "idle"
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

        # Static icon — pill indicator handles visual feedback
        self.setIcon(_load_icon())
        self.setToolTip(self._tooltips["idle"])

    def update_state(self, state: AppState) -> None:
        """Update tooltip based on app state."""
        self._current_state = state.value
        self.setToolTip(self._tooltips[state.value])

    @Slot(float)
    def update_level(self, level: float) -> None:
        """Accept level updates (pill handles the visual feedback)."""
        pass

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
            text = entry.text
            action.triggered.connect(lambda checked=False, t=text: self._copy_to_clipboard(t))

    def _copy_to_clipboard(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
