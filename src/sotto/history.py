"""Transcription history ring buffer and fallback file log."""

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sotto.config import CONFIG_DIR

logger = logging.getLogger("sotto")

LOG_FILE = CONFIG_DIR / "transcriptions.log"
LOG_MAX_BYTES = 1_000_000  # 1MB — rotate when exceeded


@dataclass(frozen=True)
class HistoryEntry:
    text: str
    timestamp: datetime
    duration_seconds: float
    processing_seconds: float


class TranscriptionHistory:
    """Fixed-size history with optional file logging."""

    def __init__(self, max_size: int = 10):
        self._lock = threading.Lock()
        self._entries: deque[HistoryEntry] = deque(maxlen=max_size)

    @property
    def entries(self) -> list[HistoryEntry]:
        """Most recent first."""
        with self._lock:
            return list(reversed(self._entries))

    def resize(self, max_size: int) -> None:
        """Change capacity, keeping most recent entries."""
        with self._lock:
            self._entries = deque(self._entries, maxlen=max_size)

    def add(self, text: str, duration_seconds: float, processing_seconds: float,
            log_to_file: bool = True) -> HistoryEntry:
        entry = HistoryEntry(
            text=text,
            timestamp=datetime.now(),
            duration_seconds=duration_seconds,
            processing_seconds=processing_seconds,
        )
        with self._lock:
            self._entries.append(entry)

        if log_to_file:
            threading.Thread(target=self._append_log, args=(entry,), daemon=True).start()

        return entry

    def _append_log(self, entry: HistoryEntry) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            # Rotate if over size limit
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
                backup = LOG_FILE.with_suffix(".log.1")
                LOG_FILE.replace(backup)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] ({entry.duration_seconds:.1f}s audio, "
                        f"{entry.processing_seconds:.2f}s processing)\n")
                f.write(f"{entry.text}\n\n")
        except Exception as e:
            logger.warning("Failed to write transcription log: %s", e)
