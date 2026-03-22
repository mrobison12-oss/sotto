"""Audio capture with sounddevice callback and Silero VAD auto-stop."""

import logging
import os
import threading

import numpy as np
import sounddevice as sd
import torch
from PySide6.QtCore import QObject, QTimer, Signal

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
    error = Signal(str)

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

        # Thread-safe flags set by the PortAudio callback, polled by QTimer
        # on the main thread. This avoids emitting Qt signals from a non-Qt
        # thread, which is unreliable in PySide6.
        self._pending_stop = False
        self._pending_level: float | None = None
        self._flag_lock = threading.Lock()

        # Poll callback flags every 50ms from the main thread
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_flags)

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
        self._pending_stop = False
        self._pending_level = None
        self._recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=CHUNK_SAMPLES,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            self._recording = False
            logger.error("Failed to open audio device: %s", e)
            self.error.emit(f"Audio device error: {e}")
            return
        self._poll_timer.start()

    def stop(self) -> None:
        """Stop recording and emit audio_ready. Safe to call from main thread."""
        if not self._recording:
            return
        self._recording = False
        self._poll_timer.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning("Error closing audio stream: %s", e)
            self._stream = None
        duration = len(self._chunks) * CHUNK_SAMPLES / SAMPLE_RATE
        logger.info("Recording stopped, %.1fs captured", duration)
        self._emit_audio()

    def _poll_flags(self) -> None:
        """Called by QTimer on the main thread — checks flags set by callback."""
        with self._flag_lock:
            should_stop = self._pending_stop
            self._pending_stop = False
            level = self._pending_level
            self._pending_level = None

        if level is not None:
            self.level_changed.emit(level)

        if should_stop:
            logger.info("VAD requested stop — processing on main thread")
            self.stop()

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """sounddevice callback — runs on PortAudio audio thread.

        IMPORTANT: Must not call stream.stop()/close() or emit Qt signals
        from here. Sets flags that the main-thread QTimer polls.
        """
        if not self._recording or self._pending_stop:
            return

        chunk = indata[:, 0].copy()  # mono float32

        with self._lock:
            self._chunks.append(chunk)

        # Max recording duration safety
        self._chunk_count += 1
        if self._chunk_count >= self._max_chunks:
            logger.warning("Max recording duration reached (%.0fs), auto-stopping",
                           self._max_chunks * CHUNK_SAMPLES / SAMPLE_RATE)
            with self._flag_lock:
                self._pending_stop = True
            return

        # RMS level for UI — store for main thread to emit
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        with self._flag_lock:
            self._pending_level = min(rms * 25.0, 1.0)

        # VAD inference
        if self._vad_model is not None:
            try:
                speech_prob = self._vad_model(torch.from_numpy(chunk), SAMPLE_RATE).item()
            except Exception as e:
                if self._chunk_count % 100 == 1:
                    logger.error("VAD inference failed: %s", e)
                return
            if speech_prob > 0.5:
                self._speech_detected = True
                self._silence_chunks = 0
            elif self._speech_detected:
                self._silence_chunks += 1
                if self._silence_chunks >= self._silence_threshold:
                    logger.info("VAD silence threshold reached, auto-stopping")
                    with self._flag_lock:
                        self._pending_stop = True

    def _emit_audio(self) -> None:
        """Concatenate buffered chunks and emit signal."""
        with self._lock:
            if not self._chunks:
                return
            audio = np.concatenate(self._chunks)
            self._chunks = []
        self.audio_ready.emit(audio)
