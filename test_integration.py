"""Integration test: feeds WAV through AudioCapture + WhisperBackend via Qt event loop."""

import logging
import sys
import wave

import numpy as np

from sotto.cuda_utils import ensure_cuda_dlls
ensure_cuda_dlls()

logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("integration")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from sotto.audio import AudioCapture, SAMPLE_RATE, CHUNK_SAMPLES
from sotto.transcribe import WhisperBackend

# Load WAV
with wave.open("test_audio.wav", "rb") as wf:
    raw = wf.readframes(wf.getnframes())
    audio_int16 = np.frombuffer(raw, dtype=np.int16)
    test_audio = audio_int16.astype(np.float32) / 32767.0

logger.info("Loaded test_audio.wav: %.1fs", len(test_audio) / SAMPLE_RATE)

app = QApplication(sys.argv)

# Set up components
capture = AudioCapture()
capture.load_vad()
logger.info("VAD loaded")

backend = WhisperBackend()
backend.load_model()
logger.info("Whisper model loaded")

result_text = None

def on_audio_ready(audio):
    global result_text
    logger.info("audio_ready received: %.1fs, %d samples", len(audio) / SAMPLE_RATE, len(audio))
    result = backend.transcribe(audio)
    result_text = result.text
    logger.info("TRANSCRIPTION: '%s'", result.text)
    logger.info("  language=%s, duration=%.1fs, processing=%.2fs",
                result.language, result.duration_seconds, result.processing_seconds)
    app.quit()

capture.audio_ready.connect(on_audio_ready)

# Simulate the PortAudio callback by feeding WAV chunks via a QTimer.
# This tests the full AudioCapture logic (VAD, stop detection, signal emission)
# running on the Qt event loop — exactly as it would in the real app, except
# chunks come from a file instead of the microphone.
chunk_index = 0

def feed_chunk():
    global chunk_index
    if not capture._recording:
        return
    start = chunk_index * CHUNK_SAMPLES
    end = start + CHUNK_SAMPLES
    if start >= len(test_audio):
        logger.info("WAV file exhausted, manual stop")
        capture.stop()
        return
    # Simulate sounddevice callback format: (N, channels) float32
    chunk = test_audio[start:end].reshape(-1, 1)
    capture._audio_callback(chunk, CHUNK_SAMPLES, None, None)
    chunk_index += 1

# Start capture (but override the stream — we'll feed chunks manually)
capture._recording = True
capture._speech_detected = False
capture._silence_chunks = 0
capture._chunk_count = 0
capture._pending_stop = False
capture._pending_level = None
capture._poll_timer.start()

# Feed chunks at ~real-time rate (32ms per chunk)
feed_timer = QTimer()
feed_timer.setInterval(5)  # faster than real-time for testing
feed_timer.timeout.connect(feed_chunk)
feed_timer.start()

# Safety timeout
QTimer.singleShot(30000, lambda: (logger.error("TIMEOUT"), app.quit()))

logger.info("Starting Qt event loop — feeding audio chunks...")
app.exec()

backend.unload_model()

if result_text:
    expected = "the quick brown fox jumps over the lazy dog near a buzzing beehive"
    got = result_text.lower().strip().rstrip(".")
    if got == expected:
        logger.info("PASS — perfect transcription match")
    else:
        logger.warning("MISMATCH — expected: '%s'", expected)
        logger.warning("           got:      '%s'", got)
else:
    logger.error("FAIL — no transcription result")
