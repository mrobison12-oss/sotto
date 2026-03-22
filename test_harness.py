"""End-to-end test harness using recorded WAV file.

Tests each stage independently, then the full pipeline.
"""

import logging
import sys
import time
import wave

import numpy as np

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_harness")

# Load test audio
with wave.open("test_audio.wav", "rb") as wf:
    assert wf.getnchannels() == 1
    assert wf.getframerate() == 16000
    raw = wf.readframes(wf.getnframes())
    audio_int16 = np.frombuffer(raw, dtype=np.int16)
    audio = audio_int16.astype(np.float32) / 32767.0

logger.info("Loaded test_audio.wav: %.1fs, %d samples, RMS=%.4f",
            len(audio) / 16000, len(audio), float(np.sqrt(np.mean(audio**2))))

# ── Stage 1: VAD ──
logger.info("=== STAGE 1: VAD TEST ===")
import torch
from silero_vad import load_silero_vad

vad = load_silero_vad(onnx=True)

CHUNK = 512
SAMPLE_RATE = 16000
silence_threshold = int(2.0 * SAMPLE_RATE / CHUNK)  # chunks needed for 2s silence

speech_detected = False
silence_chunks = 0
stop_at_chunk = None

for i in range(0, len(audio) - CHUNK, CHUNK):
    chunk = audio[i:i+CHUNK]
    t = torch.from_numpy(chunk)
    prob = vad(t, SAMPLE_RATE).item()
    
    if prob > 0.5:
        speech_detected = True
        silence_chunks = 0
    elif speech_detected:
        silence_chunks += 1
        if silence_chunks >= silence_threshold:
            stop_at_chunk = i // CHUNK
            break
    
    if i // CHUNK % 50 == 0:
        logger.debug("  chunk=%d time=%.1fs prob=%.3f speech=%s silence=%d/%d",
                     i // CHUNK, i / SAMPLE_RATE, prob, speech_detected,
                     silence_chunks, silence_threshold)

if stop_at_chunk:
    stop_time = stop_at_chunk * CHUNK / SAMPLE_RATE
    logger.info("VAD PASSED: auto-stop at chunk %d (%.1fs)", stop_at_chunk, stop_time)
else:
    logger.warning("VAD ISSUE: never triggered auto-stop (speech_detected=%s, final silence=%d/%d)",
                   speech_detected, silence_chunks, silence_threshold)

# ── Stage 2: Transcription ──
logger.info("=== STAGE 2: TRANSCRIPTION TEST ===")

from sotto.cuda_utils import ensure_cuda_dlls
ensure_cuda_dlls()

from sotto.transcribe import WhisperBackend

backend = WhisperBackend()
logger.info("Loading whisper model '%s'...", backend.model_size)
t0 = time.perf_counter()
backend.load_model()
logger.info("Model loaded in %.1fs", time.perf_counter() - t0)

# Transcribe the full audio
result = backend.transcribe(audio)
logger.info("TRANSCRIPTION RESULT: '%s'", result.text)
logger.info("  language=%s, duration=%.1fs, processing=%.2fs",
            result.language, result.duration_seconds, result.processing_seconds)

# Transcribe just the VAD-trimmed portion
if stop_at_chunk:
    trimmed = audio[:stop_at_chunk * CHUNK]
    result2 = backend.transcribe(trimmed)
    logger.info("VAD-TRIMMED RESULT: '%s'", result2.text)

backend.unload_model()
logger.info("=== ALL STAGES COMPLETE ===")
