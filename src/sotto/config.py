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
    audio_cues: bool = True
    show_notifications: bool = True
    history_size: int = 10
    fallback_log: bool = True
    initial_prompt: str = "Sotto, Claude, Obsidian"
    show_indicator: bool = True

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
                if isinstance(val, type(getattr(defaults, f.name))):
                    filtered[f.name] = val
                else:
                    logger.warning("Config field %r: expected %s, got %s — using default",
                                   f.name, f.type, type(val).__name__)
            return cls(**filtered)
        except Exception as e:
            logger.warning("Failed to load config, using defaults: %s", e)
            return cls()
