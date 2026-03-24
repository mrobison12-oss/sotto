"""JSON-backed configuration with sensible defaults."""

import dataclasses
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("sotto")

CONFIG_DIR = Path(os.environ.get("SOTTO_CONFIG_DIR", Path.home() / ".sotto"))
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class SottoConfig:
    auto_paste: bool = True
    auto_paste_delay_ms: int = 100
    confirmation_mode: bool = False
    audio_cues: bool = True
    show_notifications: bool = True
    history_size: int = 10
    fallback_log: bool = True
    log_retention_days: int = 30
    initial_prompt: str = "Sotto, Claude, Obsidian"
    show_indicator: bool = True
    model: str = ""  # empty = auto-select on first launch
    backend: str = "faster-whisper"
    hotkey: str = "ctrl+space"
    language: str = ""  # empty = auto-detect
    vad_silence_seconds: float = 2.0
    max_record_seconds: float = 120.0
    start_with_windows: bool = False

    def save(self) -> None:
        """Persist current config to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))
        logger.debug("Config saved to %s", CONFIG_FILE)

    @classmethod
    def load(cls) -> "SottoConfig":
        """Load config from disk, falling back to defaults for missing keys."""
        if not CONFIG_FILE.exists():
            cfg = cls()
            cfg.save()
            return cfg
        try:
            data = json.loads(CONFIG_FILE.read_text())
            # Validate keys and types — ignore stale or mistyped values
            defaults = cls()
            filtered = {}
            for f in dataclasses.fields(cls):
                if f.name not in data:
                    continue
                val = data[f.name]
                expected_type = type(getattr(defaults, f.name))
                # bool is a subclass of int in Python — reject bool for int/float fields
                if isinstance(val, bool) and expected_type is not bool:
                    logger.warning("Config field %r: expected %s, got bool — using default",
                                   f.name, expected_type.__name__)
                elif isinstance(val, expected_type):
                    filtered[f.name] = val
                # JSON has no int/float distinction — accept int for float fields
                elif expected_type is float and isinstance(val, int):
                    filtered[f.name] = float(val)
                else:
                    logger.warning("Config field %r: expected %s, got %s — using default",
                                   f.name, expected_type.__name__, type(val).__name__)
            return cls(**filtered)
        except Exception as e:
            logger.warning("Failed to load config, using defaults: %s", e)
            return cls()
