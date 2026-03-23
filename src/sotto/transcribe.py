"""Transcription backend abstraction and implementations.

To add a custom backend:
1. Subclass TranscriptionBackend
2. Implement load_model(), transcribe(), and unload_model()
3. Register it in BACKENDS below
"""

import abc
import logging
import os
import sys
import time
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("sotto")


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    segments: list
    duration_seconds: float
    processing_seconds: float


class TranscriptionBackend(abc.ABC):
    """Abstract base class for transcription backends.

    Every backend must support three lifecycle methods:
    - load_model(): one-time initialization (download weights, allocate GPU, etc.)
    - transcribe(): convert audio → text
    - unload_model(): release resources
    """

    @abc.abstractmethod
    def load_model(self) -> None:
        """Load the model into memory. Called once at startup."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe a float32 mono audio array to text."""

    @abc.abstractmethod
    def unload_model(self) -> None:
        """Release model from memory."""


# ---------------------------------------------------------------------------
# faster-whisper backend (default)
# ---------------------------------------------------------------------------

class FasterWhisperBackend(TranscriptionBackend):
    """Backend using CTranslate2-accelerated Whisper via faster-whisper."""

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
        self._model = None

    def load_model(self) -> None:
        from faster_whisper import WhisperModel

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

        # Extract plain dicts — avoid retaining CTranslate2 internal objects
        plain_segments = [
            {"text": seg.text, "start": seg.start, "end": seg.end}
            for seg in segments
        ]

        return TranscriptionResult(
            text=text,
            language=info.language,
            segments=plain_segments,
            duration_seconds=duration,
            processing_seconds=elapsed,
        )

    def unload_model(self) -> None:
        self._model = None
        import gc
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Backend registry and factory
# ---------------------------------------------------------------------------

# Maps config name → backend class. Add new backends here.
BACKENDS: dict[str, type[TranscriptionBackend]] = {
    "faster-whisper": FasterWhisperBackend,
}

# Keep the old name as an alias for backwards compat in existing code
WhisperBackend = FasterWhisperBackend


def create_backend(backend_name: str = "faster-whisper", model_size: str | None = None) -> TranscriptionBackend:
    """Create a transcription backend by name.

    Args:
        backend_name: Key in BACKENDS registry. Defaults to 'faster-whisper'.

    Raises:
        NotImplementedError: On unsupported platforms.
        ValueError: If backend_name is not in the registry.
    """
    if sys.platform == "darwin":
        raise NotImplementedError("macOS backend not yet implemented")

    cls = BACKENDS.get(backend_name)
    if cls is None:
        available = ", ".join(sorted(BACKENDS.keys()))
        raise ValueError(
            f"Unknown backend '{backend_name}'. Available: {available}"
        )
    return cls(device="auto", model_size=model_size or None)
