# Sotto

<p align="center">
  <img src="assets/splash.png" alt="Sotto" width="600">
</p>

Local speech-to-text dictation for Windows. Press a hotkey, speak, and your words appear as text — no cloud, no subscription, no latency.

*Sotto voce* — softly spoken.

## What it does

Sotto runs a Whisper model on your machine and turns it into a system-wide dictation tool:

1. Press **Ctrl+Space** to start recording
2. Speak naturally
3. Sotto auto-stops after a configurable silence threshold (or press Ctrl+Space again)
4. Transcribed text is placed on your clipboard and optionally auto-pasted into the active window

Everything runs locally. Audio never leaves your machine.

## Features

- **Hotkey-driven** — Ctrl+Space toggles recording from any application
- **Quick Note mode** — Ctrl+Shift+Space records with a longer silence threshold and appends to a daily markdown file (built for Obsidian)
- **Local and offline** — runs entirely on your hardware, no internet required after initial model download
- **GPU-accelerated** — auto-detects CUDA for fast transcription via CTranslate2; falls back to CPU
- **Voice Activity Detection** — Silero VAD auto-stops recording after you finish speaking
- **Auto-paste** — transcribed text is pasted directly into the active window
- **Confirmation mode** — optional preview window to review/edit transcription before pasting
- **Waveform indicator** — translucent frosted pill overlay with real-time audio visualization
- **System tray** — custom icon with history menu and settings
- **Audio cues** — procedurally generated sounds for start/stop/done/error
- **Transcription history** — recent results accessible from the tray menu
- **Hallucination guard** — detects and discards Whisper prompt echoes and repetition loops
- **Start with Windows** — optional auto-start via Windows registry
- **Pluggable backends** — swap transcription engines without changing the rest of the app

## Requirements

- **Windows 10/11**
- **Python 3.10+**
- **~800 MB disk** for the default Whisper model (downloaded on first launch)
- **NVIDIA GPU recommended** — transcription is 10-25x faster with CUDA. CPU works but Sotto will automatically select a smaller, faster model to keep latency reasonable.

## Installation

```bash
# Clone the repo
git clone https://github.com/mrobison12-oss/sotto.git
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

Sotto auto-detects CUDA via CTranslate2 (the transcription engine) and falls back to nvidia-smi for VRAM detection. PyTorch CUDA is optional — it's only used by the Silero VAD model.

## Usage

```bash
# Launch from terminal
sotto

# Or run as a module
python -m sotto.main
```

Sotto starts minimized to the system tray with the Sotto icon. Hover over the icon to see the current state.

### Hotkeys

| Hotkey | Action |
|--------|--------|
| **Ctrl+Space** | Toggle dictation — records, transcribes, pastes to active window |
| **Ctrl+Shift+Space** | Quick Note — records with longer silence tolerance, appends to a daily markdown file |

Both hotkeys are configurable in Settings. Changes require a restart.

Hotkey format: one or more modifiers (`ctrl`, `alt`, `shift`, `win`) joined with `+` to a key. Keys can be letters (`a`–`z`), numbers (`0`–`9`), function keys (`f1`–`f24`), or named keys (`space`, `enter`, `tab`, `escape`, etc.).

### Quick Note mode

Quick Note is designed for longer-form voice capture — journal entries, brain dumps, meeting notes. It uses a longer silence threshold (4s default vs 1.4s for dictation) so you can pause to think without Sotto cutting you off.

Output is appended to a daily markdown file with timestamps:

```markdown
# Voice Notes — 2026-03-23

## 10:05 PM

I'm testing the auto note creation feature...

---
```

Configure the file path in Settings. Use `{date}` in the path for automatic daily files:

```
C:/Users/You/Vault/00-inbox/Voice Notes {date}.md
```

Quick Note only activates if a file path is configured.

## Configuration

Settings are stored in `~/.sotto/config.json` and can be edited via the tray menu (**right-click → Settings**).

### Dictation

| Setting | Default | Description |
|---------|---------|-------------|
| `auto_paste` | `true` | Paste transcription into active window after copying to clipboard |
| `auto_paste_delay_ms` | `100` | Delay before auto-paste (ms). Minimum 50 |
| `confirmation_mode` | `false` | Show a preview window to review/edit text before pasting |
| `language` | `""` (auto) | ISO 639-1 language code (e.g. `en`, `es`, `fr`). Empty for auto-detection |
| `initial_prompt` | *(see below)* | Style primer for Whisper — influences punctuation and vocabulary |
| `vad_silence_seconds` | `2.0` | Seconds of silence before auto-stop |
| `max_record_seconds` | `120.0` | Maximum recording duration safety cap |
| `model` | `""` (auto) | Whisper model — auto-selected based on GPU on first launch |
| `hotkey` | `"ctrl+space"` | System-wide hotkey (restart required) |

### Quick Note

| Setting | Default | Description |
|---------|---------|-------------|
| `quick_note_hotkey` | `"ctrl+shift+space"` | Hotkey for quick note recording (restart required) |
| `quick_note_path` | `""` | File path with `{date}` template. Empty disables quick notes |
| `quick_note_silence_seconds` | `4.0` | Longer silence threshold for journal-style dictation |
| `quick_note_max_seconds` | `300.0` | Maximum recording duration for quick notes (5 min) |

### Feedback

| Setting | Default | Description |
|---------|---------|-------------|
| `audio_cues` | `true` | Play sounds on start/stop/done/error |
| `show_notifications` | `true` | Show desktop notification with transcription preview |
| `show_indicator` | `true` | Show the translucent waveform overlay during recording |

### History

| Setting | Default | Description |
|---------|---------|-------------|
| `history_size` | `10` | Number of recent transcriptions in the tray menu |
| `fallback_log` | `true` | Log transcriptions to `~/.sotto/transcriptions.log` |
| `log_retention_days` | `30` | Auto-prune log entries older than this at startup |

### System

| Setting | Default | Description |
|---------|---------|-------------|
| `start_with_windows` | `false` | Launch Sotto automatically on login |

### Initial prompt (vocabulary and style)

The `initial_prompt` field tells Whisper what kind of text to expect. It's not just a word list — Whisper treats it as "text that was just spoken," so it influences punctuation, capitalization, and word choice.

**Default:** A well-punctuated sentence with "Sotto" as a recognized word.

**Customize it** with proper nouns you use often and the punctuation style you want:

```json
{
  "initial_prompt": "I was discussing the project with Sarah, and we reviewed notes in Obsidian. The Sotto transcription captured everything clearly."
}
```

### Environment variables

These override config values for testing or scripting:

| Variable | Description |
|----------|-------------|
| `SOTTO_MODEL` | Override Whisper model selection |
| `SOTTO_VAD_SILENCE` | Override silence threshold (seconds) |
| `SOTTO_MAX_RECORD` | Override max recording duration (seconds) |
| `SOTTO_LANGUAGE` | Force a language code (e.g., `en`, `es`) |
| `SOTTO_CONFIG_DIR` | Config and log directory (default: `~/.sotto/`) |

## Transcription backends

Sotto uses a pluggable backend system. The default backend is `faster-whisper`, which uses CTranslate2-accelerated Whisper models.

| Backend | Engine | GPU support | Notes |
|---------|--------|-------------|-------|
| `faster-whisper` | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + CTranslate2 | CUDA | Default. Fast, efficient, int8 quantization |

### Writing a custom backend

Subclass `TranscriptionBackend` and register it in the `BACKENDS` dict:

```python
from sotto.transcribe import TranscriptionBackend, TranscriptionResult, BACKENDS

class MyBackend(TranscriptionBackend):
    def load_model(self) -> None: ...
    def transcribe(self, audio, sample_rate=16000, initial_prompt=None, language=None):
        # audio is a float32 numpy array, mono, at sample_rate Hz
        return TranscriptionResult(
            text="transcribed text",
            language="en",
            segments=[],
            duration_seconds=len(audio) / sample_rate,
            processing_seconds=elapsed,
        )
    def unload_model(self) -> None: ...

BACKENDS["my-backend"] = MyBackend
```

Set `"backend": "my-backend"` in `~/.sotto/config.json`.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Project structure

```
src/sotto/
├── main.py          — Entry point, hotkey handling, state machine
├── audio.py         — Audio capture with VAD worker thread
├── transcribe.py    — Backend abstraction and faster-whisper implementation
├── hotkey.py        — Hotkey string parsing for Windows RegisterHotKey
├── tray.py          — System tray icon and menu
├── indicator.py     — Frosted pill waveform indicator overlay
├── preview.py       — Confirmation mode preview window
├── config.py        — JSON-backed configuration
├── history.py       — Transcription history ring buffer
├── paste.py         — Windows SendInput for auto-paste
├── settings_ui.py   — Settings dialog
├── sounds.py        — Procedurally generated audio cues
├── startup.py       — Windows startup registry management
├── cuda_utils.py    — CUDA DLL path resolution
└── hardware.py      — GPU/VRAM detection and model auto-selection
assets/
├── icon_64.png      — Tray icon (64x64)
├── icon_16.png      — Tray icon (16x16)
└── splash.png       — Splash screen / README banner
```

## Resource usage

Sotto keeps the Whisper model loaded in VRAM for instant transcription. On first launch, Sotto **automatically detects your hardware** and selects the best model:

| VRAM | Auto-selected model | Accuracy |
|------|---------------------|----------|
| 6+ GB | `large-v3-turbo` | Best |
| 3–6 GB | `distil-large-v3` | Very good |
| No CUDA GPU | `base` | Good (CPU mode) |

You can override the model in Settings or `~/.sotto/config.json`.

VRAM stays allocated while Sotto is running. **If you need GPU memory for gaming or other applications**, quit Sotto from the tray and restart it afterward.

## License

MIT
