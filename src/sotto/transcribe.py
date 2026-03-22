"""Transcription backend wrapping faster-whisper."""

import os
import sys
import time
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    segments: list
    duration_seconds: float
    processing_seconds: float


class WhisperBackend:
    """Single-class whisper backend. No ABC until a second implementation exists."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str = "auto",
        compute_type: str = "int8",
    ):
        self.model_size = model_size or os.environ.get(
            "SOTTO_MODEL", "large-v3-turbo"
        )
        self.device = device
        self.compute_type = compute_type
        self._model: WhisperModel | None = None

    def load_model(self) -> None:
        """Load the whisper model into memory. Call once at startup."""
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )

    def transcribe(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> TranscriptionResult:
        """Transcribe audio array to text."""
        if self._model is None:
            raise RuntimeError("Model not loaded — call load_model() first")

        duration = len(audio) / sample_rate
        t0 = time.perf_counter()

        segments_iter, info = self._model.transcribe(
            audio,
            language=os.environ.get("SOTTO_LANGUAGE"),
            beam_size=5,
            word_timestamps=True,
        )
        segments = list(segments_iter)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        elapsed = time.perf_counter() - t0

        return TranscriptionResult(
            text=text,
            language=info.language,
            segments=segments,
            duration_seconds=duration,
            processing_seconds=elapsed,
        )

    def unload_model(self) -> None:
        """Release model from memory."""
        self._model = None


def create_backend() -> WhisperBackend:
    """Factory function. Raises on unsupported platforms."""
    if sys.platform == "darwin":
        raise NotImplementedError("MLX backend not yet implemented")
    return WhisperBackend(device="auto")
