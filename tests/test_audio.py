"""Tests for audio capture lifecycle."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sotto.audio import AudioCapture, SAMPLE_RATE, CHUNK_SAMPLES


class TestAudioCapture:
    @patch("sotto.audio.sd")
    def test_start_creates_stream(self, mock_sd):
        capture = AudioCapture()
        capture.start()

        mock_sd.InputStream.assert_called_once_with(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
            callback=capture._audio_callback,
        )
        mock_sd.InputStream.return_value.start.assert_called_once()

    @patch("sotto.audio.sd")
    def test_start_idempotent(self, mock_sd):
        capture = AudioCapture()
        capture.start()
        capture.start()  # Should not create a second stream
        assert mock_sd.InputStream.call_count == 1

    @patch("sotto.audio.sd")
    def test_stop_emits_audio_ready(self, mock_sd, qtbot):
        capture = AudioCapture()
        capture.start()

        # Simulate buffered audio
        chunk = np.random.randn(CHUNK_SAMPLES).astype(np.float32)
        capture._chunks = [chunk, chunk]

        with qtbot.waitSignal(capture.audio_ready, timeout=1000):
            capture.stop()

    @patch("sotto.audio.sd")
    def test_stop_without_start_is_noop(self, mock_sd):
        capture = AudioCapture()
        capture.stop()  # Should not raise

    @patch("sotto.audio.sd")
    def test_callback_buffers_audio(self, mock_sd):
        capture = AudioCapture()
        capture._recording = True
        chunk = np.random.randn(CHUNK_SAMPLES, 1).astype(np.float32)

        capture._audio_callback(chunk, CHUNK_SAMPLES, None, None)

        assert len(capture._chunks) == 1
        assert capture._chunks[0].shape == (CHUNK_SAMPLES,)

    def test_silence_threshold_from_env(self, monkeypatch):
        monkeypatch.setenv("SOTTO_VAD_SILENCE", "3.0")
        capture = AudioCapture()
        expected = int(3.0 * SAMPLE_RATE / CHUNK_SAMPLES)
        assert capture._silence_threshold == expected

    def test_default_silence_threshold(self):
        capture = AudioCapture()
        expected = int(2.0 * SAMPLE_RATE / CHUNK_SAMPLES)
        assert capture._silence_threshold == expected
