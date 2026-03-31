"""Settings dialog accessible from the system tray."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from sotto.config import SottoConfig
from sotto.hotkey import parse_hotkey
from sotto.startup import set_startup_enabled


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

        self._confirmation_mode = QCheckBox("Show preview before pasting")
        self._confirmation_mode.setChecked(config.confirmation_mode)
        self._confirmation_mode.setToolTip("Review and optionally edit transcription before it's pasted")
        d_layout.addRow(self._confirmation_mode)

        self._language = QLineEdit(config.language)
        self._language.setPlaceholderText("auto-detect (or e.g. en, es, fr, de)")
        self._language.setToolTip("ISO 639-1 language code. Leave empty for auto-detection.")
        d_layout.addRow("Language:", self._language)

        self._initial_prompt = QLineEdit(config.initial_prompt)
        self._initial_prompt.setPlaceholderText("e.g. Sotto, Claude, Obsidian")
        self._initial_prompt.setToolTip("Comma-separated words to help Whisper recognize proper nouns")
        d_layout.addRow("Vocabulary hints:", self._initial_prompt)

        self._vad_silence = QDoubleSpinBox()
        self._vad_silence.setRange(0.5, 10.0)
        self._vad_silence.setSingleStep(0.5)
        self._vad_silence.setSuffix(" s")
        self._vad_silence.setValue(config.vad_silence_seconds)
        self._vad_silence.setToolTip("Seconds of silence before auto-stop")
        d_layout.addRow("Silence threshold:", self._vad_silence)

        self._max_record = QDoubleSpinBox()
        self._max_record.setRange(10.0, 600.0)
        self._max_record.setSingleStep(10.0)
        self._max_record.setSuffix(" s")
        self._max_record.setValue(config.max_record_seconds)
        self._max_record.setToolTip("Maximum recording duration safety cap")
        d_layout.addRow("Max recording:", self._max_record)

        self._model_combo = QComboBox()
        _MODELS = [
            ("large-v3-turbo", "large-v3-turbo (best, needs 6+ GB VRAM)"),
            ("distil-large-v3", "distil-large-v3 (fast, needs 3+ GB VRAM)"),
            ("base", "base (CPU-friendly, lower accuracy)"),
        ]
        for value, label in _MODELS:
            self._model_combo.addItem(label, value)
        # Select current model
        idx = self._model_combo.findData(config.model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        else:
            # Custom model name — add it as-is
            self._model_combo.addItem(config.model, config.model)
            self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
        self._model_combo.setToolTip("Whisper model size (restart required)")
        d_layout.addRow("Model:", self._model_combo)

        self._hotkey = QLineEdit(config.hotkey)
        self._hotkey.setPlaceholderText("e.g. ctrl+space, alt+shift+r")
        self._hotkey.setToolTip("Modifier(s) + key, separated by '+' (restart required)")
        d_layout.addRow("Hotkey:", self._hotkey)

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

        self._retention_days = QSpinBox()
        self._retention_days.setRange(1, 365)
        self._retention_days.setSuffix(" days")
        self._retention_days.setValue(config.log_retention_days)
        self._retention_days.setToolTip("Entries older than this are pruned at startup")
        h_layout.addRow("Log retention:", self._retention_days)

        layout.addWidget(history)

        # -- Quick Note group --
        qn = QGroupBox("Quick Note")
        qn_layout = QFormLayout(qn)

        self._qn_path = QLineEdit(config.quick_note_path)
        self._qn_path.setPlaceholderText("e.g. C:/Users/You/Vault/00-inbox/Voice Notes {date}.md")
        self._qn_path.setToolTip("File path for voice notes. {date} expands to YYYY-MM-DD. Leave empty to disable.")
        qn_layout.addRow("Note path:", self._qn_path)

        self._qn_hotkey = QLineEdit(config.quick_note_hotkey)
        self._qn_hotkey.setPlaceholderText("e.g. ctrl+shift+space")
        self._qn_hotkey.setToolTip("Hotkey to start a quick note recording (restart required)")
        qn_layout.addRow("Hotkey:", self._qn_hotkey)

        self._qn_silence = QDoubleSpinBox()
        self._qn_silence.setRange(1.0, 30.0)
        self._qn_silence.setSingleStep(0.5)
        self._qn_silence.setSuffix(" s")
        self._qn_silence.setValue(config.quick_note_silence_seconds)
        self._qn_silence.setToolTip("Longer silence threshold for journal-style dictation")
        qn_layout.addRow("Silence threshold:", self._qn_silence)

        self._qn_max = QDoubleSpinBox()
        self._qn_max.setRange(30.0, 600.0)
        self._qn_max.setSingleStep(30.0)
        self._qn_max.setSuffix(" s")
        self._qn_max.setValue(config.quick_note_max_seconds)
        self._qn_max.setToolTip("Maximum recording duration for quick notes")
        qn_layout.addRow("Max recording:", self._qn_max)

        layout.addWidget(qn)

        # -- System group --
        system = QGroupBox("System")
        s_layout = QFormLayout(system)

        self._start_with_windows = QCheckBox("Start Sotto with Windows")
        self._start_with_windows.setChecked(config.start_with_windows)
        self._start_with_windows.setToolTip("Launch Sotto automatically when you log in")
        s_layout.addRow(self._start_with_windows)

        layout.addWidget(system)

        # -- Buttons --
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        # Validate hotkey before saving
        hotkey_str = self._hotkey.text().strip()
        if hotkey_str:
            try:
                parse_hotkey(hotkey_str)
            except ValueError as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Invalid Hotkey",
                    f"Could not parse hotkey '{hotkey_str}':\n{e}\n\n"
                    f"Examples: ctrl+space, alt+shift+r, ctrl+f10",
                )
                return

        # Validate quick note hotkey before saving
        qn_hotkey_str = self._qn_hotkey.text().strip()
        if qn_hotkey_str:
            try:
                parse_hotkey(qn_hotkey_str)
            except ValueError as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Invalid Quick Note Hotkey",
                    f"Could not parse quick note hotkey '{qn_hotkey_str}':\n{e}\n\n"
                    f"Examples: ctrl+shift+space, alt+shift+r, ctrl+f10",
                )
                return

        new_config = SottoConfig(
            auto_paste=self._auto_paste.isChecked(),
            auto_paste_delay_ms=self._paste_delay.value(),
            confirmation_mode=self._confirmation_mode.isChecked(),
            audio_cues=self._audio_cues.isChecked(),
            show_notifications=self._notifications.isChecked(),
            history_size=self._history_size.value(),
            fallback_log=self._fallback_log.isChecked(),
            log_retention_days=self._retention_days.value(),
            initial_prompt=self._initial_prompt.text().strip(),
            show_indicator=self._indicator.isChecked(),
            model=self._model_combo.currentData(),
            backend=self._config.backend,
            hotkey=hotkey_str or self._config.hotkey,
            language=self._language.text().strip(),
            vad_silence_seconds=self._vad_silence.value(),
            max_record_seconds=self._max_record.value(),
            start_with_windows=self._start_with_windows.isChecked(),
            quick_note_hotkey=self._qn_hotkey.text().strip() or self._config.quick_note_hotkey,
            quick_note_path=self._qn_path.text().strip(),
            quick_note_silence_seconds=self._qn_silence.value(),
            quick_note_max_seconds=self._qn_max.value(),
        )

        # Apply startup change immediately via registry
        if new_config.start_with_windows != self._config.start_with_windows:
            if not set_startup_enabled(new_config.start_with_windows):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Startup Error",
                    "Failed to update Windows startup setting.\n"
                    "Check the logs for details.",
                )
                # Revert to previous value so config doesn't store a lie
                from dataclasses import asdict
                new_config = SottoConfig(
                    **{
                        **asdict(new_config),
                        "start_with_windows": self._config.start_with_windows,
                    }
                )

        new_config.save()
        self.config_changed.emit(new_config)
        self.accept()
