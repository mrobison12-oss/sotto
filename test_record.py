"""Record a 10-second test sentence from the Logi C310 mic to a WAV file."""

import numpy as np
import sounddevice as sd
import wave

SAMPLE_RATE = 16000
CHANNELS = 1
DURATION = 10

print(">>> RECORDING 10 SECONDS — SPEAK NOW <<<")

audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype="float32",
    device=1,
)
sd.wait()
print(">>> DONE <<<")

audio = audio[:, 0]
audio_int16 = (audio * 32767).astype(np.int16)

with wave.open("test_audio.wav", "wb") as wf:
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)
    wf.setframerate(SAMPLE_RATE)
    wf.writeframes(audio_int16.tobytes())

rms = float(np.sqrt(np.mean(audio ** 2)))
print(f"Saved test_audio.wav — {DURATION}s, RMS={rms:.4f}")
if rms < 0.005:
    print("WARNING: Audio appears very quiet — check mic")
else:
    print("Audio level looks good!")
