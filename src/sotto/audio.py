"""Audio capture with sounddevice callback and Silero VAD auto-stop.

VAD inference runs on a dedicated worker thread (not the PortAudio callback)
to avoid GIL contention, memory allocation, and callback-timeout risks in
the real-time audio thread.
"""

import logging
import os
import queue
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

# Sentinel value to tell the VAD worker to shut down
_STOP_SENTINEL = None


def _load_vad_model():
    """Load the Silero VAD ONNX model."""
    from silero_vad import load_silero_vad
    return load_silero_vad(onnx=True)


class AudioCapture(QObject):
    """Records audio via sounddevice callback, uses Silero VAD for auto-stop.

    Architecture:
        PortAudio callback → queue → VAD worker thread → flags → QTimer → main thread

    The audio callback only copies data and computes RMS — no ML inference,
    no memory allocation beyond the chunk copy. VAD inference runs on a
    dedicated worker thread that pulls chunks from a queue.

    Signals:
        audio_ready(np.ndarray): Emitted when recording stops (VAD or manual).
            Contains the full recording as float32 mono 16kHz.
        level_changed(float): Emitted per chunk with RMS level (0.0–1.0 range).
    """

    audio_ready = Signal(np.ndarray)
    level_changed = Signal(float)
    error = Signal(str)

    def __init__(self, vad_silence_seconds: float = 2.0,
                 max_record_seconds: float = 120.0, parent=None):
        super().__init__(parent)
        self._vad_model = None
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()

        # Env vars override config (useful for testing/scripting)
        self._env_silence = os.environ.get("SOTTO_VAD_SILENCE")
        self._env_max_record = os.environ.get("SOTTO_MAX_RECORD")
        self.update_thresholds(vad_silence_seconds, max_record_seconds)

        self._recording = False
        self._chunk_count = 0

        # Queue for passing chunks from audio callback to VAD worker
        self._vad_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=64)
        self._vad_thread: threading.Thread | None = None

        # Thread-safe flags set by the VAD worker, polled by QTimer
        # on the main thread. This avoids emitting Qt signals from a non-Qt
        # thread, which is unreliable in PySide6.
        self._pending_stop = False
        self._pending_level: float | None = None
        self._flag_lock = threading.Lock()

        # Poll callback flags every 50ms from the main thread
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_flags)

    def update_thresholds(self, vad_silence_seconds: float, max_record_seconds: float) -> None:
        """Update VAD thresholds. Safe to call while idle — takes effect on next recording."""
        silence_sec = float(self._env_silence) if self._env_silence else vad_silence_seconds
        max_sec = float(self._env_max_record) if self._env_max_record else max_record_seconds
        with self._flag_lock:
            self._silence_threshold = int(silence_sec * SAMPLE_RATE / CHUNK_SAMPLES)
            self._max_chunks = int(max_sec * SAMPLE_RATE / CHUNK_SAMPLES)

    def load_vad(self) -> None:
        """Pre-load VAD model. Call once at startup."""
        self._vad_model = _load_vad_model()

    def start(self) -> None:
        """Begin recording from default input device."""
        with self._flag_lock:
            if self._recording:
                return
            self._chunk_count = 0
            self._pending_stop = False
            self._pending_level = None
            self._recording = True

        if self._vad_model is None:
            logger.warning("VAD model not loaded — auto-stop will not work")

        with self._lock:
            self._chunks = []

        # Drain any stale items from previous recording
        while not self._vad_queue.empty():
            try:
                self._vad_queue.get_nowait()
            except queue.Empty:
                break

        # Start VAD worker thread
        self._vad_thread = threading.Thread(target=self._vad_worker, daemon=True)
        self._vad_thread.start()

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
            with self._flag_lock:
                self._recording = False
            self._vad_queue.put(_STOP_SENTINEL)
            logger.error("Failed to open audio device: %s", e)
            self.error.emit(f"Audio device error: {e}")
            return
        self._poll_timer.start()

    def stop(self) -> None:
        """Stop recording and emit audio_ready. Safe to call from main thread."""
        with self._flag_lock:
            if not self._recording:
                return
            self._recording = False

        self._poll_timer.stop()

        # Signal VAD worker to stop
        self._vad_queue.put(_STOP_SENTINEL)

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning("Error closing audio stream: %s", e)
            self._stream = None

        # Wait for VAD worker to finish (brief — it exits on sentinel)
        if self._vad_thread is not None:
            self._vad_thread.join(timeout=2.0)
            self._vad_thread = None

        with self._lock:
            duration = len(self._chunks) * CHUNK_SAMPLES / SAMPLE_RATE
        logger.info("Recording stopped, %.1fs captured", duration)
        self._emit_audio()

    def _poll_flags(self) -> None:
        """Called by QTimer on the main thread — checks flags set by VAD worker."""
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
        """sounddevice callback — runs on PortAudio real-time thread.

        Kept minimal: copy chunk, compute RMS, enqueue for VAD.
        No ML inference, no locks held longer than necessary.
        """
        with self._flag_lock:
            if not self._recording or self._pending_stop:
                return

        chunk = indata[:, 0].copy()  # mono float32

        with self._lock:
            self._chunks.append(chunk)

        # RMS level for UI — noise gate so ambient sounds don't flicker the waveform.
        # Threshold ~0.008 filters out typical room noise (pets, HVAC, keyboard)
        # while letting any intentional speech through clearly.
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        display_rms = rms if rms > 0.004 else 0.0

        with self._flag_lock:
            self._chunk_count += 1
            if self._chunk_count >= self._max_chunks:
                logger.warning("Max recording duration reached (%.0fs), auto-stopping",
                               self._max_chunks * CHUNK_SAMPLES / SAMPLE_RATE)
                self._pending_stop = True
                return
            self._pending_level = min(display_rms * 25.0, 1.0)

        # Enqueue chunk for VAD worker (non-blocking — drop if queue is full)
        try:
            self._vad_queue.put_nowait(chunk)
        except queue.Full:
            pass  # VAD worker is behind — skip this chunk rather than block RT thread

    def _vad_worker(self) -> None:
        """Dedicated thread for VAD inference. Pulls chunks from queue."""
        if self._vad_model is not None:
            self._vad_model.reset_states()

        speech_detected = False
        silence_chunks = 0

        while True:
            try:
                chunk = self._vad_queue.get(timeout=0.5)
            except queue.Empty:
                # Check if we should exit
                with self._flag_lock:
                    if not self._recording:
                        return
                continue

            if chunk is _STOP_SENTINEL:
                return

            if self._vad_model is None:
                continue

            try:
                speech_prob = self._vad_model(torch.from_numpy(chunk), SAMPLE_RATE).item()
            except Exception as e:
                logger.error("VAD inference failed: %s", e)
                continue

            should_log_stop = False
            with self._flag_lock:
                if not self._recording:
                    return
                if speech_prob > 0.5:
                    speech_detected = True
                    silence_chunks = 0
                elif speech_detected:
                    silence_chunks += 1
                    if silence_chunks >= self._silence_threshold:
                        should_log_stop = True
                        self._pending_stop = True
            if should_log_stop:
                logger.info("VAD silence threshold reached, auto-stopping")
                return

    def _emit_audio(self) -> None:
        """Concatenate buffered chunks and emit signal."""
        with self._lock:
            if not self._chunks:
                return
            audio = np.concatenate(self._chunks)
            self._chunks = []
        self.audio_ready.emit(audio)
