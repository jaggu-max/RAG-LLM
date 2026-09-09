"""Filesystem watcher — monitors dataset directory for file changes."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.processor import EXTENSION_TO_TYPE, process_file, remove_file

log = get_logger(__name__)


class DatasetEventHandler(FileSystemEventHandler):
    """Handles file create/modify/delete events in the dataset directory."""

    def __init__(self):
        super().__init__()
        self._debounce: dict[str, float] = {}
        self._debounce_seconds = 2.0  # Wait for file writes to complete

    def _should_process(self, path: str) -> bool:
        p = Path(path)
        if p.name.startswith("."):
            return False
        ext = p.suffix.lower()
        return ext in EXTENSION_TO_TYPE

    def _debounced(self, path: str) -> bool:
        now = time.time()
        last = self._debounce.get(path, 0)
        if now - last < self._debounce_seconds:
            return False
        self._debounce[path] = now
        return True

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._should_process(event.src_path) and self._debounced(event.src_path):
            log.info("📁 New file detected: %s", Path(event.src_path).name)
            # Run in thread to avoid blocking the watcher
            threading.Thread(
                target=self._process_safe,
                args=(event.src_path,),
                daemon=True,
            ).start()

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._should_process(event.src_path) and self._debounced(event.src_path):
            log.info("📝 File modified: %s", Path(event.src_path).name)
            threading.Thread(
                target=self._process_safe,
                args=(event.src_path,),
                daemon=True,
            ).start()

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._should_process(event.src_path):
            log.info("🗑️ File deleted: %s", Path(event.src_path).name)
            threading.Thread(
                target=self._remove_safe,
                args=(event.src_path,),
                daemon=True,
            ).start()

    def _process_safe(self, path: str) -> None:
        # Wait a moment for file write to finish
        time.sleep(1)
        try:
            process_file(path)
        except Exception as e:
            log.error("Watcher process error for %s: %s", path, e)

    def _remove_safe(self, path: str) -> None:
        try:
            remove_file(path)
        except Exception as e:
            log.error("Watcher remove error for %s: %s", path, e)


# ── Global watcher state ──────────────────────────────────

_observer: Optional[Observer] = None
_running = False


def start_watcher() -> None:
    """Start watching the dataset directory for changes."""
    global _observer, _running

    if not settings.AUTO_INDEX:
        log.info("Auto-index disabled, skipping watcher")
        return

    dataset_path = Path(settings.DATASET_PATH)
    dataset_path.mkdir(parents=True, exist_ok=True)

    handler = DatasetEventHandler()
    _observer = Observer()
    _observer.schedule(handler, str(dataset_path), recursive=False)
    _observer.daemon = True
    _observer.start()
    _running = True
    log.info("👁️ File watcher started on: %s", dataset_path)


def stop_watcher() -> None:
    global _observer, _running
    if _observer:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
    _running = False
    log.info("File watcher stopped")


def is_watcher_running() -> bool:
    return _running
