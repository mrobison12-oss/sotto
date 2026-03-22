"""Entry point, hotkey registration, state machine, orchestration."""

import ctypes
import ctypes.wintypes
import enum
import logging
import os
import sys

# CTranslate2 needs cublas64_12.dll for CUDA. The nvidia-cublas-cu12 pip
# package installs it under site-packages/nvidia/cublas/bin/ which isn't
# on PATH by default. Add it before any CUDA operations.
def _add_cuda_dll_paths():
    try:
        import importlib.util
        spec = importlib.util.find_spec("nvidia.cublas")
        if spec and spec.submodule_search_locations:
            bin_dir = os.path.join(list(spec.submodule_search_locations)[0], "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

_add_cuda_dll_paths()

import numpy as np
from PySide6.QtCore import QRunnable, QThreadPool, Signal, Slot, QObject, QByteArray, Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from sotto.audio import AudioCapture
from sotto.config import SottoConfig
from sotto.history import TranscriptionHistory
from sotto.paste import simulate_paste
from sotto.transcribe import TranscriptionResult, create_backend
from sotto.tray import SystemTray
from sotto import sounds

logger = logging.getLogger("sotto")

# Windows constants
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
VK_SPACE = 0x20
HOTKEY_ID = 1


class AppState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"


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
                 initial_prompt: str | None = None):
        super().__init__()
        self.backend = backend
        self.audio = audio
        self.signals = signals
        self.initial_prompt = initial_prompt
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.backend.transcribe(self.audio, initial_prompt=self.initial_prompt)
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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sotto")
        self.hide()

        self._config = SottoConfig.load()
        self._state = AppState.IDLE
        self._shutting_down = False
        self._backend = create_backend()
        self._audio = AudioCapture(parent=self)
        self._history = TranscriptionHistory(max_size=self._config.history_size)
        self._tray = SystemTray(history=self._history, parent=self)

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
        self._tray.quit_requested.connect(self._quit)
        self._tray.settings_requested.connect(self._show_settings)

        # Register hotkey: Ctrl+Space
        hwnd = int(self.winId())
        if not ctypes.windll.user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_CONTROL, VK_SPACE):
            logger.error("Failed to register hotkey Ctrl+Space — may be in use by another app")

        # Eager model load
        logger.info("Loading whisper model '%s'...", self._backend.model_size)
        self._backend.load_model()
        self._audio.load_vad()
        logger.info("Model loaded, ready for dictation")

        self._tray.show()
        self._update_state(AppState.IDLE)

    def nativeEvent(self, event_type: QByteArray | bytes, message: int) -> object:
        """Handle WM_HOTKEY from RegisterHotKey."""
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._on_hotkey()
                return True, 0
        return super().nativeEvent(event_type, message)

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
        # If PROCESSING, ignore hotkey

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

        self._update_state(AppState.PROCESSING)

        # Create signals as a standalone object (not owned by the task).
        # Store a reference to prevent GC before the queued signal is delivered.
        signals = TranscriptionSignals()
        signals.finished.connect(self._on_transcription_done)
        signals.error.connect(self._on_transcription_error)
        self._current_signals = signals  # must be set before start() to prevent GC race

        prompt = self._config.initial_prompt if self._config.initial_prompt else None
        task = TranscriptionTask(self._backend, audio, signals, initial_prompt=prompt)
        self._pool.start(task)  # task may complete instantly — signals ref must already be held

    @Slot(TranscriptionResult)
    def _on_transcription_done(self, result: TranscriptionResult) -> None:
        """Write transcription to clipboard, auto-paste, notify."""
        if result.text:
            clipboard = QApplication.clipboard()
            clipboard.setText(result.text)

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

            # Desktop notification
            if self._config.show_notifications:
                preview = result.text[:120] + ("..." if len(result.text) > 120 else "")
                self._tray.show_toast("Sotto", preview)

            # Auto-paste after delay (must run on main thread for SendInput)
            if self._config.auto_paste:
                _paste_after_delay(self._config.auto_paste_delay_ms)

            logger.info(
                "Transcribed %.1fs audio in %.2fs: %s",
                result.duration_seconds,
                result.processing_seconds,
                result.text[:80],
            )
        else:
            logger.info("No speech detected")
        self._current_signals = None
        self._update_state(AppState.IDLE)

    @Slot(str)
    def _on_transcription_error(self, error: str) -> None:
        logger.error("Transcription failed: %s", error)
        if self._config.audio_cues:
            sounds.play("error")
        self._current_signals = None
        self._update_state(AppState.IDLE)

    def _update_state(self, state: AppState) -> None:
        self._state = state
        self._tray.update_state(state)

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
