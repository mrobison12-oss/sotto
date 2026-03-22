"""Audio capture with sounddevice callback and Silero VAD auto-stop."""

import logging
import os
import threading

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal, Qt

logger = logging.getLogger("sotto")

# Silero VAD expects 16kHz mono, 512-sample chunks (32ms)
SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512
CHANNELS = 1


def _load_vad_model():
    """Load the Silero VAD ONNX model."""
    from silero_vad import load_silero_vad
    return load_silero_vad(onnx=True)


class AudioCapture(QObject):
    """Records audio via sounddevice callback, uses Silero VAD for auto-stop.

    Signals:
        audio_ready(np.ndarray): Emitted when recording stops (VAD or manual).
            Contains the full recording as float32 mono 16kHz.
        level_changed(float): Emitted per chunk with RMS level (0.0–1.0 range).
    """

    audio_ready = Signal(np.ndarray)
    level_changed = Signal(float)
    _vad_stopped = Signal()  # internal: defers stream stop from callback to main thread

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vad_model = None
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()

        # VAD state
        self._speech_detected = False
        self._silence_chunks = 0
        self._chunk_count = 0
        silence_sec = float(os.environ.get("SOTTO_VAD_SILENCE", "2.0"))
        self._silence_threshold = int(silence_sec * SAMPLE_RATE / CHUNK_SAMPLES)
        max_sec = float(os.environ.get("SOTTO_MAX_RECORD", "120.0"))
        self._max_chunks = int(max_sec * SAMPLE_RATE / CHUNK_SAMPLES)

        self._recording = False

        # Connect VAD stop signal to main thread via queued connection.
        # The audio callback cannot call stream.stop() directly — PortAudio
        # holds a lock during the callback and stop() would deadlock.
        self._vad_stopped.connect(self.stop, Qt.ConnectionType.QueuedConnection)

    def load_vad(self) -> None:
        """Pre-load VAD model. Call once at startup."""
        self._vad_model = _load_vad_model()

    def start(self) -> None:
        """Begin recording from default input device."""
        if self._recording:
            return

        if self._vad_model is None:
            logger.warning("VAD model not loaded — auto-stop will not work")

        with self._lock:
            self._chunks = []
        self._speech_detected = False
        self._silence_chunks = 0
        self._chunk_count = 0
        self._recording = True

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop recording and emit audio_ready. Safe to call from any thread."""
        if not self._recording:
            return
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._emit_audio()

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """sounddevice callback — runs on PortAudio audio thread.

        IMPORTANT: Must not call stream.stop()/close() from here — PortAudio
        holds a lock during callbacks. Use _vad_stopped signal to defer to main thread.
        """
        if not self._recording:
            return

        chunk = indata[:, 0].copy()  # mono float32

        with self._lock:
            self._chunks.append(chunk)

        # Max recording duration safety — prevents unbounded memory growth
        # if VAD fails or environment is noisy
        self._chunk_count += 1
        if self._chunk_count >= self._max_chunks:
            logger.warning("Max recording duration reached (%.0fs), auto-stopping",
                           self._max_chunks * CHUNK_SAMPLES / SAMPLE_RATE)
            self._recording = False
            self._vad_stopped.emit()
            return

        # RMS level for UI
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        self.level_changed.emit(min(rms * 5.0, 1.0))  # scale up for visibility

        # VAD inference
        if self._vad_model is not None:
            speech_prob = self._vad_model(chunk, SAMPLE_RATE).item()
            if speech_prob > 0.5:
                self._speech_detected = True
                self._silence_chunks = 0
            elif self._speech_detected:
                self._silence_chunks += 1
                if self._silence_chunks >= self._silence_threshold:
                    # Sustained silence after speech — signal main thread to stop.
                    # Set flag immediately to prevent further chunk processing.
                    self._recording = False
                    self._vad_stopped.emit()

    def _emit_audio(self) -> None:
        """Concatenate buffered chunks and emit signal."""
        with self._lock:
            if not self._chunks:
                return
            audio = np.concatenate(self._chunks)
            self._chunks = []
        self.audio_ready.emit(audio)
