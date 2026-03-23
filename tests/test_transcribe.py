"""Tests for the transcription backend."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sotto.transcribe import (
    BACKENDS,
    FasterWhisperBackend,
    TranscriptionBackend,
    TranscriptionResult,
    WhisperBackend,
    create_backend,
)


class TestTranscriptionResult:
    def test_frozen_dataclass(self):
        result = TranscriptionResult(
            text="hello world",
            language="en",
            segments=[],
            duration_seconds=1.5,
            processing_seconds=0.3,
        )
        assert result.text == "hello world"
        assert result.language == "en"
        assert result.duration_seconds == 1.5
        with pytest.raises(AttributeError):
            result.text = "modified"


class TestBackendABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            TranscriptionBackend()

    def test_faster_whisper_is_subclass(self):
        assert issubclass(FasterWhisperBackend, TranscriptionBackend)

    def test_whisper_backend_alias(self):
        """WhisperBackend is kept as an alias for backwards compat."""
        assert WhisperBackend is FasterWhisperBackend

    def test_backends_registry_contains_faster_whisper(self):
        assert "faster-whisper" in BACKENDS
        assert BACKENDS["faster-whisper"] is FasterWhisperBackend


class TestFasterWhisperBackend:
    def test_default_model(self):
        backend = FasterWhisperBackend()
        assert backend.model_size == "large-v3-turbo"
        assert backend.device == "auto"
        assert backend.compute_type == "int8"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("SOTTO_MODEL", "medium")
        backend = FasterWhisperBackend()
        assert backend.model_size == "medium"

    def test_explicit_model_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SOTTO_MODEL", "medium")
        backend = FasterWhisperBackend(model_size="tiny")
        assert backend.model_size == "tiny"

    def test_transcribe_without_load_raises(self):
        backend = FasterWhisperBackend()
        audio = np.zeros(16000, dtype=np.float32)
        with pytest.raises(RuntimeError, match="Model not loaded"):
            backend.transcribe(audio)

    def test_transcribe_returns_result(self):
        mock_model = MagicMock()

        mock_segment = MagicMock()
        mock_segment.text = " hello world "
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = (iter([mock_segment]), mock_info)

        backend = FasterWhisperBackend()
        backend._model = mock_model  # inject mock directly, skip load_model
        audio = np.zeros(16000, dtype=np.float32)
        result = backend.transcribe(audio)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "hello world"
        assert result.language == "en"
        assert result.duration_seconds == 1.0
        assert result.processing_seconds >= 0

    def test_unload_model(self):
        backend = FasterWhisperBackend()
        backend._model = MagicMock()
        backend.unload_model()
        assert backend._model is None


class TestCreateBackend:
    @patch("sotto.transcribe.sys")
    def test_darwin_raises(self, mock_sys):
        mock_sys.platform = "darwin"
        with pytest.raises(NotImplementedError):
            create_backend()

    def test_returns_faster_whisper_by_default(self):
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        backend = create_backend()
        assert isinstance(backend, FasterWhisperBackend)
        assert backend.device == "auto"

    def test_returns_faster_whisper_by_name(self):
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        backend = create_backend("faster-whisper")
        assert isinstance(backend, FasterWhisperBackend)

    def test_unknown_backend_raises(self):
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        with pytest.raises(ValueError, match="Unknown backend"):
            create_backend("nonexistent")
