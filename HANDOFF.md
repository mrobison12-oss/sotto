# Sotto — Session Handoff Instructions

## Context
Sotto is a local speech-to-text dictation tool (formerly LocalWhisper). Phase 1 code is written, code-reviewed, and bug-fixed. No end-to-end test has been done yet. Matt will return in ~30 minutes for the first real test.

## Project Location
`C:\Users\Matt\projects\sotto\`

## Architecture & Memory
- Architecture doc: `C:\Users\Matt\documents\m.robison12@gmail.com\03-personal\projects\Whisper replacement\Whispr replacement.md`
- Progress notes: same folder, `localwhisper-progress-2026-03-22.md`
- Memory: `project_localwhisper.md` in Claude memory (has full context)

## Python Environment
- Python 3.12 via `py` launcher (not `python` — not on PATH)
- Package installed editable: `py -m pip install -e ".[dev]"`
- Run app: `py -m sotto.main`
- Run tests: `py -m pytest tests/ -v`
- Scripts dir not on PATH — always use `py -m` prefix

---

## Independent Work Items (do all of these)

### 1. Run the test suite and fix any failures
```bash
cd /c/Users/Matt/projects/sotto && py -m pytest tests/ -v 2>&1
```
Known risk: `test_stop_emits_audio_ready` uses `qtbot` (pytest-qt) which may not be installed. If pytest-qt is missing, install it (`py -m pip install pytest-qt`) or skip that test.

The env var tests (`test_env_var_override`, `test_silence_threshold_from_env`) were recently fixed from LOCALWHISPER_ → SOTTO_ — confirm they actually pass now.

### 2. Verify silero_vad API compatibility
The code uses:
```python
from silero_vad import load_silero_vad
load_silero_vad(onnx=True)
```
This API may not match silero-vad 6.2.1. Test it:
```bash
py -c "from silero_vad import load_silero_vad; m = load_silero_vad(onnx=True); print(type(m))"
```
If it fails, check what the actual API is (`py -c "import silero_vad; help(silero_vad)"`) and fix `audio.py:_load_vad_model()` accordingly. The fallback is `torch.hub.load('snakers4/silero-vad', 'silero_vad')` but that uses the PyTorch path.

### 3. Complete the model download
The first launch was killed after 8 seconds mid-download. Run the app long enough for the model to fully download (~800MB):
```bash
py -m sotto.main 2>&1
```
Let it run until you see "Model loaded, ready for dictation" in the logs. This is a GUI app — it will block the terminal. Kill it after the model loads successfully (the model is cached in `~/.cache/huggingface/` for future runs).

If the app crashes during model load, capture the error — it's likely a faster-whisper or CTranslate2 CUDA issue that needs debugging before E2E test.

### 4. Delete old localwhisper directory
```bash
rm -rf /c/Users/Matt/projects/localwhisper
```
This is the pre-rename copy. All code now lives in `/c/Users/Matt/projects/sotto/`.

### 5. Create initial git commit
```bash
cd /c/Users/Matt/projects/sotto
git add pyproject.toml .gitignore src/ tests/
git commit -m "Phase 1: working dictation tool (Sotto)

Sotto voce — local speech-to-text replacing Whisper Flow.
- faster-whisper backend (large-v3-turbo, int8, CUDA auto-detect)
- sounddevice + Silero VAD (2.0s silence, 120s max record)
- RegisterHotKey (Ctrl+Space), Qt state machine, QClipboard
- PySide6 system tray with state-driven icons
- Code-reviewed: fixed PortAudio callback deadlock, signal
  lifecycle, cross-thread safety, double-quit guard

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
Do NOT commit HANDOFF.md — it's ephemeral.

### 6. Verify no stale LOCALWHISPER references remain
```bash
grep -ri "localwhisper\|LOCALWHISPER" /c/Users/Matt/projects/sotto/src/ /c/Users/Matt/projects/sotto/tests/
```
Should return nothing. If it finds anything, fix it.

### 7. Update architecture doc with post-review changes
The architecture doc doesn't yet reflect:
- Max recording duration (120s, SOTTO_MAX_RECORD env var)
- The threading fixes from code review (VAD stop via signal, decoupled TranscriptionSignals)

Add a row to the Key Design Decisions table:
| **Max recording duration** | 120s default safety cap. Prevents unbounded memory growth if VAD fails or environment is noisy |

And update the Data Flow section step 3 to mention the max duration alongside VAD.

---

## Do NOT Do (requires Matt)
- End-to-end test (Matt needs to press Ctrl+Space and speak)
- Phase 1.5 implementation (not yet planned in detail)
- Any changes to vault note content outside `Claude/` folder
- Pushing to any remote

## E2E Test Checklist (for when Matt returns)
1. Launch: `py -m sotto.main` — tray icon appears (gray circle)
2. Ctrl+Space — tray turns red, recording starts
3. Speak a sentence naturally
4. Pause 2 seconds — VAD auto-stops, tray turns blue (processing)
5. ~1s later — tray turns gray, text is on clipboard
6. Paste into any text field — verify transcription accuracy
7. Ctrl+Space then Ctrl+Space again quickly — manual stop works
8. Check logs for timing info
