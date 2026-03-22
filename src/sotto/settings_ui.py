"""Settings dialog accessible from the system tray."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from sotto.config import SottoConfig


class SettingsDialog(QDialog):
    """Modal settings dialog. Emits config_changed on save."""

    config_changed = Signal(SottoConfig)

    def __init__(self, config: SottoConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sotto Settings")
        self.setMinimumWidth(340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._config = config
        layout = QVBoxLayout(self)

        # -- Dictation group --
        dictation = QGroupBox("Dictation")
        d_layout = QFormLayout(dictation)

        self._auto_paste = QCheckBox("Auto-paste after transcription")
        self._auto_paste.setChecked(config.auto_paste)
        d_layout.addRow(self._auto_paste)

        self._paste_delay = QSpinBox()
        self._paste_delay.setRange(50, 1000)
        self._paste_delay.setSuffix(" ms")
        self._paste_delay.setValue(config.auto_paste_delay_ms)
        d_layout.addRow("Paste delay:", self._paste_delay)

        self._initial_prompt = QLineEdit(config.initial_prompt)
        self._initial_prompt.setPlaceholderText("e.g. Sotto, Claude, Obsidian")
        self._initial_prompt.setToolTip("Comma-separated words to help Whisper recognize proper nouns")
        d_layout.addRow("Vocabulary hints:", self._initial_prompt)

        layout.addWidget(dictation)

        # -- Feedback group --
        feedback = QGroupBox("Feedback")
        f_layout = QFormLayout(feedback)

        self._audio_cues = QCheckBox("Play audio cues")
        self._audio_cues.setChecked(config.audio_cues)
        f_layout.addRow(self._audio_cues)

        self._notifications = QCheckBox("Show desktop notifications")
        self._notifications.setChecked(config.show_notifications)
        f_layout.addRow(self._notifications)

        self._indicator = QCheckBox("Show recording indicator")
        self._indicator.setChecked(config.show_indicator)
        self._indicator.setToolTip("Translucent pill overlay during recording and transcription")
        f_layout.addRow(self._indicator)

        layout.addWidget(feedback)

        # -- History group --
        history = QGroupBox("History")
        h_layout = QFormLayout(history)

        self._history_size = QSpinBox()
        self._history_size.setRange(1, 100)
        self._history_size.setValue(config.history_size)
        h_layout.addRow("History entries:", self._history_size)

        self._fallback_log = QCheckBox("Log transcriptions to file")
        self._fallback_log.setChecked(config.fallback_log)
        h_layout.addRow(self._fallback_log)

        layout.addWidget(history)

        # -- Buttons --
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        new_config = SottoConfig(
            auto_paste=self._auto_paste.isChecked(),
            auto_paste_delay_ms=self._paste_delay.value(),
            audio_cues=self._audio_cues.isChecked(),
            show_notifications=self._notifications.isChecked(),
            history_size=self._history_size.value(),
            fallback_log=self._fallback_log.isChecked(),
            initial_prompt=self._initial_prompt.text().strip(),
            show_indicator=self._indicator.isChecked(),
        )
        new_config.save()
        self.config_changed.emit(new_config)
        self.accept()
