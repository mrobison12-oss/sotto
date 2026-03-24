"""Splash screen shown during model loading."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
_SPLASH_PATH = _ASSETS / "splash.png"


class SplashScreen(QWidget):
    """Frameless splash window shown while the model loads."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splash image
        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if _SPLASH_PATH.exists():
            pixmap = QPixmap(str(_SPLASH_PATH))
            # Scale to reasonable size — max 480px wide
            if pixmap.width() > 480:
                pixmap = pixmap.scaledToWidth(480, Qt.TransformationMode.SmoothTransformation)
            self._image.setPixmap(pixmap)
        else:
            self._image.setText("Sotto")
            self._image.setStyleSheet("color: #e8e8ec; font-size: 24px; padding: 40px;")

        layout.addWidget(self._image)

        # Loading label
        self._status = QLabel("Loading model...")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(
            "color: #8888a0; font-size: 12px; background: #1a1a1e; padding: 8px;"
        )
        layout.addWidget(self._status)

        self.adjustSize()

    def show_centered(self) -> None:
        """Show centered on the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.adjustSize()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()
