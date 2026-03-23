"""Transcription history ring buffer and fallback file log."""

import logging
import re
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sotto.config import CONFIG_DIR

logger = logging.getLogger("sotto")

LOG_FILE = CONFIG_DIR / "transcriptions.log"
LOG_MAX_BYTES = 1_000_000  # 1MB — rotate when exceeded

# Matches the timestamp line: [2026-03-22 14:30:00] (...)
_TS_PATTERN = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


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
        self._log_lock = threading.Lock()
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
            self._append_log(entry)

        return entry

    def _append_log(self, entry: HistoryEntry) -> None:
        """Append entry to log file. Synchronous — file I/O is sub-millisecond."""
        with self._log_lock:
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


def prune_log(retention_days: int) -> None:
    """Remove log entries older than retention_days. Call at startup.

    Parses timestamp lines from the log file and rewrites it with only
    entries within the retention window. Also deletes stale backup files.
    """
    if retention_days <= 0 or not LOG_FILE.exists():
        return

    cutoff = datetime.now() - timedelta(days=retention_days)

    # Prune the backup file — if it exists and is entirely older than cutoff, delete it
    backup = LOG_FILE.with_suffix(".log.1")
    if backup.exists():
        try:
            mtime = datetime.fromtimestamp(backup.stat().st_mtime)
            if mtime < cutoff:
                backup.unlink()
                logger.debug("Deleted stale log backup (modified %s)", mtime.date())
        except Exception as e:
            logger.warning("Failed to prune log backup: %s", e)

    # Prune the active log file — keep only entries within retention window
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception as e:
        logger.warning("Failed to read log for pruning: %s", e)
        return

    kept: list[str] = []
    keeping = False
    pruned_count = 0

    for line in lines:
        match = _TS_PATTERN.match(line)
        if match:
            try:
                entry_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                keeping = entry_time >= cutoff
                if not keeping:
                    pruned_count += 1
            except ValueError:
                keeping = True  # keep unparseable entries
        if keeping:
            kept.append(line)

    if pruned_count > 0:
        try:
            LOG_FILE.write_text("".join(kept), encoding="utf-8")
            logger.info("Pruned %d log entries older than %d days", pruned_count, retention_days)
        except Exception as e:
            logger.warning("Failed to write pruned log: %s", e)
