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
from sotto.transcribe import TranscriptionResult, create_backend
from sotto.tray import SystemTray

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

    def __init__(self, backend, audio: np.ndarray, signals: TranscriptionSignals):
        super().__init__()
        self.backend = backend
        self.audio = audio
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.backend.transcribe(self.audio)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class SottoApp(QMainWindow):
    """Hidden main window — exists for nativeEvent hotkey handling."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sotto")
        self.hide()

        self._state = AppState.IDLE
        self._shutting_down = False
        self._backend = create_backend()
        self._audio = AudioCapture(parent=self)
        self._tray = SystemTray(parent=self)
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(1)

        # Keep a reference to the current transcription signals to prevent GC
        # while the queued signal is in flight.
        self._current_signals: TranscriptionSignals | None = None

        # Connect signals — audio_ready and level_changed are now emitted
        # from the main thread (via QTimer polling), so direct connection is fine.
        self._audio.audio_ready.connect(self._on_audio_ready)
        self._audio.level_changed.connect(self._tray.update_level)
        self._tray.quit_requested.connect(self._quit)

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
            self._audio.start()
        elif self._state == AppState.LISTENING:
            self._audio.stop()
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
        self._current_signals = signals

        task = TranscriptionTask(self._backend, audio, signals)
        self._pool.start(task)

    @Slot(TranscriptionResult)
    def _on_transcription_done(self, result: TranscriptionResult) -> None:
        """Write transcription to clipboard on main thread."""
        if result.text:
            clipboard = QApplication.clipboard()
            clipboard.setText(result.text)
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
        self._current_signals = None
        self._update_state(AppState.IDLE)

    def _update_state(self, state: AppState) -> None:
        self._state = state
        self._tray.update_state(state)

    def _quit(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID)
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
