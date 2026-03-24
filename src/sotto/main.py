"""Entry point, hotkey registration, state machine, orchestration."""

import ctypes
import ctypes.wintypes
import enum
import logging
import os
import sys

from sotto.cuda_utils import ensure_cuda_dlls
ensure_cuda_dlls()

import numpy as np
from PySide6.QtCore import QRunnable, QThreadPool, Signal, Slot, QObject, QByteArray, Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from sotto.audio import AudioCapture
from sotto.config import SottoConfig
from sotto.history import TranscriptionHistory, prune_log
from sotto.paste import simulate_paste
from sotto.transcribe import TranscriptionResult, create_backend
from sotto.indicator import RecordingIndicator
from sotto.preview import PreviewWindow
from sotto.hotkey import parse_hotkey, format_hotkey
from sotto.tray import SystemTray
from sotto import hardware, sounds

logger = logging.getLogger("sotto")

# Windows constants
WM_HOTKEY = 0x0312
HOTKEY_ID = 1


class AppState(enum.Enum):
    LOADING = "loading"
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    CONFIRMING = "confirming"  # Preview window open, waiting for user


class TranscriptionSignals(QObject):
    """Signals for QRunnable (QRunnable can't emit signals directly)."""
    finished = Signal(TranscriptionResult)
    error = Signal(str)


class TranscriptionTask(QRunnable):
    """One-shot transcription worker for QThreadPool.

    Signals are passed in rather than owned, so they survive auto-delete.
    QThreadPool may delete the QRunnable after run() returns — if signals
    were owned by the task, queued signal delivery could reference a
    destroyed QObject.
    """

    def __init__(self, backend, audio: np.ndarray, signals: TranscriptionSignals,
                 initial_prompt: str | None = None, language: str | None = None):
        super().__init__()
        self.backend = backend
        self.audio = audio
        self.signals = signals
        self.initial_prompt = initial_prompt
        self.language = language
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.backend.transcribe(
                self.audio, initial_prompt=self.initial_prompt, language=self.language,
            )
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


def _paste_after_delay(delay_ms: int) -> None:
    """Schedule paste on the main thread after a delay.

    SendInput must run on the main thread (which owns the foreground
    input context). QTimer.singleShot is thread-safe and fires on the
    main thread's event loop.
    """
    from PySide6.QtCore import QTimer

    def _do_paste():
        try:
            simulate_paste()
        except Exception as e:
            logger.warning("Auto-paste failed: %s", e)

    QTimer.singleShot(delay_ms, _do_paste)


class SottoApp(QMainWindow):
    """Hidden main window — exists for nativeEvent hotkey handling."""

    _models_loaded = Signal()
    _model_load_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sotto")
        self.hide()

        self._config = SottoConfig.load()
        self._state = AppState.IDLE
        self._shutting_down = False

        # Parse hotkey early so we can show it in the tray tooltip
        try:
            self._hk_mod, self._hk_vk = parse_hotkey(self._config.hotkey)
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                None, "Sotto — Hotkey Error",
                f"Invalid hotkey '{self._config.hotkey}':\n{e}\n\n"
                f"Fix the 'hotkey' field in ~/.sotto/config.json and restart.",
            )
            sys.exit(1)
        self._hotkey_display = format_hotkey(self._hk_mod, self._hk_vk)

        # Auto-select model on first launch if not configured and no env override
        self._first_launch_message: str | None = None
        if not self._config.model and not os.environ.get("SOTTO_MODEL"):
            profile = hardware.detect_hardware()
            model, description = hardware.select_model(profile)
            self._config.model = model
            self._config.save()
            self._first_launch_message = description
            logger.info("Auto-selected model: %s", description)

        # Prune stale log entries on startup
        if self._config.fallback_log and self._config.log_retention_days > 0:
            prune_log(self._config.log_retention_days)

        self._backend = create_backend(self._config.backend, model_size=self._config.model or None)
        self._audio = AudioCapture(
            vad_silence_seconds=self._config.vad_silence_seconds,
            max_record_seconds=self._config.max_record_seconds,
            parent=self,
        )
        self._history = TranscriptionHistory(max_size=self._config.history_size)
        self._tray = SystemTray(history=self._history, hotkey_display=self._hotkey_display, parent=self)
        self._indicator = RecordingIndicator()
        self._preview = PreviewWindow()
        self._preview.accepted.connect(self._on_preview_accepted)
        self._preview.dismissed.connect(self._on_preview_dismissed)

        # Private thread pool for transcription — avoids polluting Qt's global pool
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)

        # Keep a reference to the current transcription signals to prevent GC
        # while the queued signal is in flight.
        self._current_signals: TranscriptionSignals | None = None
        self._settings_dlg = None

        # Connect signals — audio_ready and level_changed are now emitted
        # from the main thread (via QTimer polling), so direct connection is fine.
        self._audio.audio_ready.connect(self._on_audio_ready)
        self._audio.level_changed.connect(self._tray.update_level)
        self._audio.level_changed.connect(self._indicator.update_level)
        self._audio.error.connect(self._on_audio_error)
        self._models_loaded.connect(self._on_models_loaded)
        self._model_load_failed.connect(self._on_model_load_failed)
        self._tray.quit_requested.connect(self._quit)
        self._tray.settings_requested.connect(self._show_settings)

        # Register hotkey (parsed earlier during init)
        hwnd = int(self.winId())
        if not ctypes.windll.user32.RegisterHotKey(hwnd, HOTKEY_ID, self._hk_mod, self._hk_vk):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                None, "Sotto — Hotkey Error",
                f"Failed to register {self._hotkey_display}.\n\n"
                f"Another application may be using this hotkey.",
            )
            sys.exit(1)
        logger.info("Hotkey registered: %s", self._hotkey_display)

        self._tray.show()
        self._update_state(AppState.LOADING)
        self._tray.show_toast("Sotto — Loading", "Loading transcription model, this may take a moment...")

        # Load models in background so the GUI stays responsive
        import threading
        self._model_load_event = threading.Event()
        threading.Thread(target=self._load_models, daemon=True).start()

        # Watchdog: if model loading hasn't completed in 180s, show error
        from PySide6.QtCore import QTimer
        self._load_watchdog = QTimer(self)
        self._load_watchdog.setSingleShot(True)
        self._load_watchdog.setInterval(180_000)  # 3 minutes
        self._load_watchdog.timeout.connect(self._on_model_load_timeout)
        self._load_watchdog.start()

    def nativeEvent(self, event_type: QByteArray | bytes, message: int) -> object:
        """Handle WM_HOTKEY from RegisterHotKey."""
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._on_hotkey()
                return True, 0
        return super().nativeEvent(event_type, message)

    def _load_models(self) -> None:
        """Load whisper + VAD models (runs on background thread)."""
        try:
            logger.info("Loading whisper model '%s'...", self._backend.model_size)
            self._backend.load_model()
            self._audio.load_vad()
            logger.info("Model loaded, ready for dictation")
            self._model_load_event.set()
            self._models_loaded.emit()
        except Exception as e:
            logger.error("Model loading failed: %s", e)
            self._model_load_event.set()
            self._model_load_failed.emit(str(e))

    @Slot()
    def _on_models_loaded(self) -> None:
        self._load_watchdog.stop()
        self._update_state(AppState.IDLE)
        if self._first_launch_message:
            self._tray.show_toast(
                "Sotto — Model Selected",
                self._first_launch_message,
                duration_ms=8000,
            )
            self._first_launch_message = None

    @Slot()
    def _on_model_load_timeout(self) -> None:
        """Watchdog fires if model loading exceeds timeout."""
        if self._model_load_event.is_set():
            return  # already loaded, watchdog is stale
        logger.error("Model loading timed out after 180s")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Sotto — Loading Timeout",
            "Model loading took too long (>3 minutes).\n\n"
            "This usually means the model is still downloading.\n"
            "Check your internet connection and restart Sotto.\n\n"
            "Model files are cached after the first download.",
        )
        sys.exit(1)

    @Slot(str)
    def _on_model_load_failed(self, error: str) -> None:
        self._load_watchdog.stop()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Sotto — Model Error",
            f"Failed to load transcription model.\n\n{error}",
        )
        sys.exit(1)

    def _on_hotkey(self) -> None:
        """Toggle recording on hotkey press."""
        if self._state == AppState.IDLE:
            self._update_state(AppState.LISTENING)
            if self._config.audio_cues:
                sounds.play("start")
            self._audio.start()
        elif self._state == AppState.LISTENING:
            self._audio.stop()
            if self._config.audio_cues:
                sounds.play("stop")
        # If PROCESSING or CONFIRMING, ignore hotkey

    @Slot(np.ndarray)
    def _on_audio_ready(self, audio: np.ndarray) -> None:
        """Called when audio capture finishes (VAD or manual stop)."""
        # Guard against audio arriving while already processing
        if self._state == AppState.PROCESSING:
            logger.debug("Audio received while processing, ignoring")
            return

        if len(audio) < 1600:  # Less than 0.1s — likely accidental
            logger.debug("Audio too short, ignoring")
            self._update_state(AppState.IDLE)
            return

        # Check if audio is mostly silence — skip transcription to avoid
        # Whisper hallucinating the initial_prompt as output
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.001:
            logger.info("Audio too quiet (RMS=%.4f), skipping transcription", rms)
            self._update_state(AppState.IDLE)
            return

        self._update_state(AppState.PROCESSING)

        # Create signals as a standalone object (not owned by the task).
        # Store a reference to prevent GC before the queued signal is delivered.
        signals = TranscriptionSignals()
        signals.finished.connect(self._on_transcription_done)
        signals.error.connect(self._on_transcription_error)
        self._current_signals = signals  # must be set before start() to prevent GC race

        prompt = self._config.initial_prompt if self._config.initial_prompt else None
        language = self._config.language if self._config.language else None
        task = TranscriptionTask(self._backend, audio, signals, initial_prompt=prompt, language=language)
        self._pool.start(task)  # task may complete instantly — signals ref must already be held

    @Slot(TranscriptionResult)
    def _is_hallucination(self, text: str) -> bool:
        """Detect if Whisper hallucinated the initial prompt instead of real speech."""
        if not self._config.initial_prompt:
            return False
        # Check if output is just the prompt words (possibly reordered/partial)
        prompt_words = {w.strip().lower() for w in self._config.initial_prompt.split(",")}
        text_words = {w.strip(".,!? ").lower() for w in text.split()}
        return len(text_words) > 0 and text_words.issubset(prompt_words)

    @Slot(TranscriptionResult)
    def _on_transcription_done(self, result: TranscriptionResult) -> None:
        """Write transcription to clipboard, auto-paste, notify."""
        if result.text and self._is_hallucination(result.text):
            logger.info("Discarded likely hallucination: %s", result.text)
            self._current_signals = None
            self._update_state(AppState.IDLE)
            return

        if result.text:
            # History + file log
            self._history.add(
                text=result.text,
                duration_seconds=result.duration_seconds,
                processing_seconds=result.processing_seconds,
                log_to_file=self._config.fallback_log,
            )
            self._tray.refresh_history()

            # Audio cue
            if self._config.audio_cues:
                sounds.play("done")

            logger.info(
                "Transcribed %.1fs audio in %.2fs: %s",
                result.duration_seconds,
                result.processing_seconds,
                result.text[:80],
            )

            if self._config.confirmation_mode:
                # Show preview window — user decides whether to paste
                logger.info("Confirmation mode ON — showing preview window")
                self._current_signals = None
                self._update_state(AppState.CONFIRMING)
                self._preview.show_preview(result.text)
                return
            else:
                self._finalize_paste(result.text)
        else:
            logger.info("No speech detected")
        self._current_signals = None
        self._update_state(AppState.IDLE)

    def _finalize_paste(self, text: str) -> None:
        """Copy text to clipboard, optionally auto-paste, and notify."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        if self._config.show_notifications:
            preview = text[:120] + ("..." if len(text) > 120 else "")
            self._tray.show_toast("Sotto", preview)

        if self._config.auto_paste:
            _paste_after_delay(self._config.auto_paste_delay_ms)

    @Slot(str)
    def _on_preview_accepted(self, text: str) -> None:
        """User accepted (possibly edited) text from preview window."""
        logger.info("Preview accepted: %s", text[:80])
        self._finalize_paste(text)
        self._update_state(AppState.IDLE)

    @Slot()
    def _on_preview_dismissed(self) -> None:
        """User dismissed the preview — discard transcription."""
        logger.info("Preview dismissed")
        self._update_state(AppState.IDLE)

    @Slot(str)
    def _on_transcription_error(self, error: str) -> None:
        logger.error("Transcription failed: %s", error)
        if self._config.audio_cues:
            sounds.play("error")
        self._current_signals = None
        self._update_state(AppState.IDLE)

    @Slot(str)
    def _on_audio_error(self, error: str) -> None:
        logger.error("Audio error: %s", error)
        if self._config.audio_cues:
            sounds.play("error")
        if self._config.show_notifications:
            self._tray.show_toast("Sotto — Error", error)
        self._update_state(AppState.IDLE)

    def _update_state(self, state: AppState) -> None:
        self._state = state
        self._tray.update_state(state)
        if self._config.show_indicator:
            self._indicator.show_for_state(state)
        elif state == AppState.IDLE:
            self._indicator.hide()

    def _show_settings(self) -> None:
        """Open the settings dialog (single instance)."""
        if self._settings_dlg is not None:
            self._settings_dlg.raise_()
            self._settings_dlg.activateWindow()
            return
        from sotto.settings_ui import SettingsDialog

        dlg = SettingsDialog(self._config, parent=self)
        dlg.config_changed.connect(self._on_config_changed)
        dlg.finished.connect(self._on_settings_closed)
        self._settings_dlg = dlg
        dlg.show()

    def _on_settings_closed(self) -> None:
        self._settings_dlg = None

    @Slot(SottoConfig)
    def _on_config_changed(self, config: SottoConfig) -> None:
        """Apply updated settings."""
        self._config = config
        self._history.resize(config.history_size)
        self._audio.update_thresholds(config.vad_silence_seconds, config.max_record_seconds)
        if not config.show_indicator:
            self._indicator.hide()
        logger.info("Settings updated")

    def _quit(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID)
        # Stop active recording so no new tasks are submitted
        self._audio.stop()
        # Wait for in-flight transcription before destroying the model
        self._pool.waitForDone(5000)
        self._backend.unload_model()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self._quit()
        event.accept()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if sys.platform != "win32":
        logger.error("Sotto currently only supports Windows")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running with just tray icon

    window = SottoApp()  # noqa: F841 — prevent GC
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
