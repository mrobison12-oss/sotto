"""Transcription backend wrapping faster-whisper."""

import logging
import os
import sys
import time
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger("sotto")


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
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as e:
            logger.error("Failed to load model '%s' (device=%s): %s",
                         self.model_size, self.device, e)
            raise RuntimeError(
                f"Could not load whisper model '{self.model_size}': {e}\n"
                f"Check CUDA availability and that the model name is valid."
            ) from e

    def transcribe(
        self, audio: np.ndarray, sample_rate: int = 16000,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio array to text."""
        if self._model is None:
            raise RuntimeError("Model not loaded — call load_model() first")

        duration = len(audio) / sample_rate
        t0 = time.perf_counter()

        try:
            segments_iter, info = self._model.transcribe(
                audio,
                language=os.environ.get("SOTTO_LANGUAGE"),
                beam_size=5,
                word_timestamps=True,
                initial_prompt=initial_prompt or None,
            )
            segments = list(segments_iter)
        except Exception as e:
            raise RuntimeError(
                f"Transcription failed ({duration:.1f}s audio): {e}"
            ) from e
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
