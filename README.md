# Sotto

Local speech-to-text dictation for Windows. Press a hotkey, speak, and your words appear as text — no cloud, no subscription, no latency.

*Sotto voce* — softly spoken.

## What it does

Sotto runs a Whisper model on your machine and turns it into a system-wide dictation tool:

1. Press **Ctrl+Space** to start recording
2. Speak naturally
3. Sotto auto-stops after 2 seconds of silence (or press Ctrl+Space again)
4. Transcribed text is placed on your clipboard and optionally auto-pasted into the active window

Everything runs locally. Audio never leaves your machine.

## Features

- **Hotkey-driven** — Ctrl+Space toggles recording from any application
- **Local and offline** — runs entirely on your hardware, no internet required after initial model download
- **GPU-accelerated** — auto-detects CUDA for fast transcription via CTranslate2; falls back to CPU
- **Voice Activity Detection** — Silero VAD auto-stops recording after you finish speaking
- **Auto-paste** — transcribed text is pasted directly into the active window
- **Waveform indicator** — translucent overlay with real-time audio visualization
- **System tray** — state-driven icon (loading/idle/recording/processing) with history menu
- **Audio cues** — procedurally generated sounds for start/stop/done/error
- **Desktop notifications** — shows a preview of each transcription
- **Transcription history** — recent results accessible from the tray menu
- **Pluggable backends** — swap transcription engines without changing the rest of the app

## Requirements

- **Windows 10/11**
- **Python 3.10+**
- **~800 MB disk** for the default Whisper model (downloaded on first launch)
- **NVIDIA GPU recommended** — transcription is 10-25x faster with CUDA. CPU works but Sotto will automatically select a smaller, faster model to keep latency reasonable.

## Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/sotto.git
cd sotto

# Install (editable mode for development)
pip install -e ".[dev]"

# Or install without dev dependencies
pip install -e .
```

### CUDA setup

If you have an NVIDIA GPU, install the CUDA-enabled version of PyTorch:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

Sotto will auto-detect CUDA availability and use it if present.

## Usage

```bash
# Launch from terminal
sotto

# Or run as a module
python -m sotto.main
```

Sotto starts minimized to the system tray. The icon color indicates state:

| Color | State |
|-------|-------|
| Amber | Loading model (first launch takes ~30s) |
| Gray | Ready — press Ctrl+Space to record |
| Red | Listening — speak now |
| Blue | Processing — transcribing your audio |

### Hotkey

**Ctrl+Space** (default) — toggles recording. Press once to start, press again to stop early (or let VAD auto-stop after 2s of silence).

To change the hotkey, edit `~/.sotto/config.json` or use **Settings → Hotkey**:

```json
{
  "hotkey": "alt+shift+r"
}
```

Format: one or more modifiers (`ctrl`, `alt`, `shift`, `win`) joined with `+` to a key. Keys can be letters (`a`–`z`), numbers (`0`–`9`), function keys (`f1`–`f24`), or named keys (`space`, `enter`, `tab`, `escape`, etc.). Restart required after changing.

## Configuration

Settings are stored in `~/.sotto/config.json` and can be edited via the tray menu (**right-click → Settings**).

| Setting | Default | Description |
|---------|---------|-------------|
| `auto_paste` | `true` | Paste transcription into active window after copying to clipboard |
| `auto_paste_delay_ms` | `100` | Delay before auto-paste (ms) |
| `audio_cues` | `true` | Play sounds on start/stop/done/error |
| `show_notifications` | `true` | Show desktop notification with transcription preview |
| `show_indicator` | `true` | Show the translucent waveform overlay during recording |
| `history_size` | `10` | Number of recent transcriptions to keep in the tray menu |
| `fallback_log` | `true` | Log transcriptions to `~/.sotto/transcriptions.log` |
| `log_retention_days` | `30` | Auto-prune log entries older than this at startup |
| `initial_prompt` | `"Sotto, Claude, Obsidian"` | Comma-separated vocabulary hints for Whisper (helps with proper nouns) |
| `model` | `""` (auto) | Whisper model — auto-selected based on GPU on first launch. Set manually to override |
| `backend` | `"faster-whisper"` | Transcription backend (see below) |
| `hotkey` | `"ctrl+space"` | System-wide hotkey to toggle recording (restart required) |

### Environment variables

These override config for advanced use or scripting:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOTTO_MODEL` | `large-v3-turbo` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo`) |
| `SOTTO_VAD_SILENCE` | `2.0` | Seconds of silence before auto-stop |
| `SOTTO_MAX_RECORD` | `120.0` | Maximum recording duration (safety cap) |
| `SOTTO_LANGUAGE` | auto-detect | Force a language code (e.g., `en`, `es`, `fr`) |
| `SOTTO_CONFIG_DIR` | `~/.sotto/` | Config and log directory |

## Transcription backends

Sotto uses a pluggable backend system. The default backend is `faster-whisper`, which uses CTranslate2-accelerated Whisper models.

### Available backends

| Backend | Engine | GPU support | Notes |
|---------|--------|-------------|-------|
| `faster-whisper` | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + CTranslate2 | CUDA | Default. Fast, efficient, supports int8 quantization |

### Writing a custom backend

To add your own transcription engine, subclass `TranscriptionBackend` and register it:

```python
# my_backend.py
from sotto.transcribe import TranscriptionBackend, TranscriptionResult, BACKENDS

class MyBackend(TranscriptionBackend):
    def load_model(self) -> None:
        # Initialize your model here
        ...

    def transcribe(self, audio, sample_rate=16000, initial_prompt=None):
        # audio is a float32 numpy array, mono, at sample_rate Hz
        # Return a TranscriptionResult
        ...
        return TranscriptionResult(
            text="transcribed text",
            language="en",
            segments=[],
            duration_seconds=len(audio) / sample_rate,
            processing_seconds=elapsed,
        )

    def unload_model(self) -> None:
        # Clean up resources
        ...

# Register it
BACKENDS["my-backend"] = MyBackend
```

Then set `"backend": "my-backend"` in your `~/.sotto/config.json`.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_transcribe.py -v
```

### Project structure

```
src/sotto/
├── main.py          — Entry point, hotkey handling, state machine
├── audio.py         — Audio capture with Silero VAD
├── transcribe.py    — Backend abstraction and faster-whisper implementation
├── hotkey.py        — Hotkey string parsing for Windows RegisterHotKey
├── tray.py          — System tray icon and menu
├── indicator.py     — Waveform recording indicator overlay
├── config.py        — JSON-backed configuration
├── history.py       — Transcription history ring buffer
├── paste.py         — Windows SendInput for auto-paste
├── settings_ui.py   — Settings dialog
├── sounds.py        — Procedurally generated audio cues
├── cuda_utils.py    — CUDA DLL path resolution
└── hardware.py      — GPU detection and model auto-selection
```

## Resource usage

Sotto keeps the Whisper model loaded in VRAM (GPU memory) for instant transcription. On first launch, Sotto **automatically detects your hardware** and selects the best model for your GPU — you'll see a notification confirming what was chosen.

| VRAM | Auto-selected model | Accuracy |
|------|---------------------|----------|
| 6+ GB | `large-v3-turbo` | Best |
| 3–6 GB | `distil-large-v3` | Very good |
| No CUDA GPU | `base` | Good (CPU mode) |

This VRAM stays allocated as long as Sotto is running. **If you're gaming or running other GPU-intensive applications**, close Sotto from the system tray (right-click → Quit) before launching demanding games, and restart it afterward.

To manually override model selection, set `"model"` in `~/.sotto/config.json` or use the `SOTTO_MODEL` environment variable.

## License

MIT
