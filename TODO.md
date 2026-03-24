# Sotto — Feature Backlog

Brainstormed 2026-03-23. Evaluate next session.

---

## High Priority

### 1. Append mode / dictation sessions
Hold hotkey (or double-tap) to enter "session mode" where multiple dictation chunks accumulate into a single buffer. Paste the full result when done. Solves the "dictating a long email in chunks" use case where each chunk currently replaces the clipboard.

### 2. Undo last paste
After auto-pasting, show a brief toast with an "Undo" hotkey (e.g. within 3 seconds). Restores previous clipboard contents and sends Ctrl+Z to the target app. Prevents the "Whisper pasted garbage" scenario when confirmation mode is off.

### 3. Post-processing pipeline
After Whisper returns text, run it through a configurable chain: capitalize sentences → strip filler words (um, uh, like) → custom regex replacements. Users could define their own rules in config. Start simple — built-in filler word removal + sentence capitalization.

---

## Medium Priority

### 4. Configurable indicator position
Currently hardcoded to center-lower-third. Add a dropdown in settings: top-center, bottom-center, bottom-right, top-right. Simple enum → small change to `indicator.py:_position_on_active_screen()`.

### 5. Sound volume control
Audio cues are currently on/off with no volume control. Add a volume slider (0.0–1.0) to settings and multiply the generated waveforms in `sounds.py` by the volume factor.

### 6. Indicator size/opacity
Fixed size and opacity may not work for all displays/accessibility needs. Add settings for scale factor and opacity level.

### 7. Noise gate / minimum audio level
Don't start VAD processing if ambient RMS is below a threshold. Prevents accidental triggers in quiet rooms where keyboard clicks or fan noise might trip VAD. Configurable threshold in settings.

### 8. Per-application profiles
Different `initial_prompt` or `language` per foreground application. Detect active window title/process → look up profile. Useful for: technical vocabulary in code editors, language switching for multilingual users.

---

## Low Priority / Future

### 9. Update mechanism
No auto-update, no version check, no "new version available" notification. For a tray app that's supposed to be invisible, manual updates are friction. Could check PyPI for new versions on startup or periodically.

### 10. Crash reporting / diagnostics
If Sotto dies silently (tray apps love to do this), user has no idea why. Add: (a) a "View logs" option in tray menu that opens the log file, (b) unhandled exception handler that writes to a crash log and shows a notification before exit.

### 11. Accessibility
Screen reader compatibility, high-contrast mode for the indicator, keyboard-only tray navigation. Dictation tools are especially valuable for users with motor impairments — and those users may also need accessibility features.

### 12. macOS support (Phase 3)
Apple Silicon portability. Requires: CoreAudio backend, different hotkey registration (CGEvent), different paste simulation, different tray icon API. Architecture is already abstracted for this.

### 13. API server / iOS client (Phase 3)
Local HTTP endpoint for transcription requests from other devices on the network. Could enable an iOS shortcut that streams audio to the desktop and gets text back.
