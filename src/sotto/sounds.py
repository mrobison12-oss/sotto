"""Cross-platform audio cues using numpy + sounddevice (no external files)."""

import logging
import threading
import time

import numpy as np
import sounddevice as sd

logger = logging.getLogger("sotto")

SAMPLE_RATE = 44100

_play_lock = threading.Lock()


def _tone(freq: float, duration_ms: int, volume: float = 0.3) -> np.ndarray:
    """Generate a sine wave tone with a short fade-in/out to avoid clicks."""
    t = np.linspace(0, duration_ms / 1000.0, int(SAMPLE_RATE * duration_ms / 1000), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t).astype(np.float32) * volume
    # 5ms fade-in/out to prevent click artifacts
    fade = int(SAMPLE_RATE * 0.005)
    if fade > 0 and len(wave) > 2 * fade:
        wave[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        wave[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return wave


def _generate_cues() -> dict[str, np.ndarray]:
    """Pre-generate all audio cues at import time."""
    # Rising two-tone: recording started
    start = np.concatenate([_tone(600, 80), _tone(900, 80)])
    # Falling tone: recording stopped, processing
    stop = np.concatenate([_tone(900, 80), _tone(600, 80)])
    # Quick double beep: transcription done
    gap = np.zeros(int(SAMPLE_RATE * 0.06), dtype=np.float32)
    done = np.concatenate([_tone(800, 60), gap, _tone(800, 60)])
    # Single low tone: error
    error = _tone(300, 200, volume=0.25)
    return {"start": start, "stop": stop, "done": done, "error": error}


_CUES = _generate_cues()


def play(cue_name: str) -> None:
    """Play a named cue on a background thread. Non-blocking, fire-and-forget.

    If a cue is already playing, the new one is silently skipped to avoid
    PortAudio thread-safety issues with concurrent stream open/close.
    """
    audio = _CUES.get(cue_name)
    if audio is None:
        logger.warning("Unknown audio cue: %s", cue_name)
        return

    def _play():
        if not _play_lock.acquire(blocking=False):
            return  # another cue is playing — skip
        try:
            sd.play(audio, samplerate=SAMPLE_RATE)
            # Bounded wait instead of sd.wait() which can hang indefinitely
            time.sleep(len(audio) / SAMPLE_RATE + 0.1)
            sd.stop()
        except Exception as e:
            logger.debug("Audio cue playback failed: %s", e)
        finally:
            _play_lock.release()

    threading.Thread(target=_play, daemon=True).start()
