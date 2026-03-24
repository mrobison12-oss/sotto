"""Confirmation preview window — review/edit transcription before pasting."""

import logging

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent

logger = logging.getLogger("sotto")
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PreviewWindow(QWidget):
    """Floating preview that lets the user review, edit, or discard transcription.

    Signals:
        accepted(str): User confirmed — text (possibly edited) should be pasted.
        dismissed(): User cancelled — discard the transcription.
    """

    accepted = Signal(str)
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sotto — Preview")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(400)
        self.setMaximumWidth(600)

        self.setStyleSheet("""
            PreviewWindow {
                background: #1a1a1e;
                border: 1px solid #3a3a42;
                border-radius: 8px;
            }
            QTextEdit {
                background: #24242a;
                color: #e8e8ec;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                padding: 8px;
                font-size: 14px;
            }
            QLabel {
                color: #8888a0;
                font-size: 11px;
            }
            QPushButton {
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#accept_btn {
                background: #2a7a3a;
                color: #e8e8ec;
                border: 1px solid #3a9a4a;
            }
            QPushButton#accept_btn:hover { background: #3a9a4a; }
            QPushButton#dismiss_btn {
                background: #3a3a42;
                color: #a8a8b0;
                border: 1px solid #4a4a52;
            }
            QPushButton#dismiss_btn:hover { background: #4a4a52; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        hint = QLabel("Review transcription — Enter to paste, Shift+Enter for newline, Escape to discard")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont("Segoe UI", 13))
        self._text_edit.setAcceptRichText(False)
        self._text_edit.setMaximumHeight(150)
        # Install event filter to intercept Enter before QTextEdit consumes it
        self._text_edit.installEventFilter(self)
        layout.addWidget(self._text_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        dismiss_btn = QPushButton("Discard")
        dismiss_btn.setObjectName("dismiss_btn")
        dismiss_btn.clicked.connect(self._dismiss)
        btn_row.addWidget(dismiss_btn)

        accept_btn = QPushButton("Paste")
        accept_btn.setObjectName("accept_btn")
        accept_btn.clicked.connect(self._accept)
        accept_btn.setDefault(True)
        btn_row.addWidget(accept_btn)

        layout.addLayout(btn_row)

    def show_preview(self, text: str) -> None:
        """Show the preview window with the given text, positioned near cursor."""
        logger.info("Preview: showing window for %d chars at cursor", len(text))
        self._text_edit.setPlainText(text)
        self._text_edit.selectAll()
        self._position_near_cursor()
        self.show()
        self.raise_()
        self.activateWindow()
        self._text_edit.setFocus()
        logger.info("Preview: window visible=%s, pos=(%d,%d), size=(%d,%d)",
                     self.isVisible(), self.x(), self.y(), self.width(), self.height())

    def eventFilter(self, obj, event: QEvent) -> bool:
        """Intercept key events on the QTextEdit before it processes them."""
        if obj is self._text_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self._dismiss()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    return False  # let QTextEdit insert newline
                self._accept()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keys when focus is not in the text editor."""
        if event.key() == Qt.Key.Key_Escape:
            self._dismiss()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def _accept(self) -> None:
        text = self._text_edit.toPlainText().strip()
        self.hide()
        if text:
            self.accepted.emit(text)
        else:
            self.dismissed.emit()

    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()

    def _position_near_cursor(self) -> None:
        """Position above the system cursor, centered horizontally."""
        from PySide6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()

        # Size hint for positioning
        self.adjustSize()
        w = self.width()
        h = self.height()

        # Center horizontally on cursor, above it vertically
        x = max(geo.x(), min(cursor_pos.x() - w // 2, geo.x() + geo.width() - w))
        y = max(geo.y(), cursor_pos.y() - h - 20)

        self.move(x, y)
