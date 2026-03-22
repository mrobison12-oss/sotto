"""Tests for the transcription backend."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sotto.transcribe import TranscriptionResult, WhisperBackend, create_backend


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


class TestWhisperBackend:
    def test_default_model(self):
        backend = WhisperBackend()
        assert backend.model_size == "large-v3-turbo"
        assert backend.device == "auto"
        assert backend.compute_type == "int8"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("SOTTO_MODEL", "medium")
        backend = WhisperBackend()
        assert backend.model_size == "medium"

    def test_explicit_model_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SOTTO_MODEL", "medium")
        backend = WhisperBackend(model_size="tiny")
        assert backend.model_size == "tiny"

    def test_transcribe_without_load_raises(self):
        backend = WhisperBackend()
        audio = np.zeros(16000, dtype=np.float32)
        with pytest.raises(RuntimeError, match="Model not loaded"):
            backend.transcribe(audio)

    @patch("sotto.transcribe.WhisperModel")
    def test_transcribe_returns_result(self, mock_whisper_cls):
        # Set up mock model
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model

        mock_segment = MagicMock()
        mock_segment.text = " hello world "
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = (iter([mock_segment]), mock_info)

        backend = WhisperBackend()
        backend.load_model()
        audio = np.zeros(16000, dtype=np.float32)
        result = backend.transcribe(audio)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "hello world"
        assert result.language == "en"
        assert result.duration_seconds == 1.0
        assert result.processing_seconds >= 0

    def test_unload_model(self):
        backend = WhisperBackend()
        backend._model = MagicMock()
        backend.unload_model()
        assert backend._model is None


class TestCreateBackend:
    @patch("sotto.transcribe.sys")
    def test_darwin_raises(self, mock_sys):
        mock_sys.platform = "darwin"
        with pytest.raises(NotImplementedError, match="MLX"):
            create_backend()

    def test_returns_backend_on_windows(self):
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        backend = create_backend()
        assert isinstance(backend, WhisperBackend)
        assert backend.device == "auto"
