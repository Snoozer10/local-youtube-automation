"""Deterministic SHA-256 research caching engine for NotebookLM queries.

Guarantees:
- Zero quota waste via SHA-256 content addressing
- Atomic disk writes (tempfile + os.replace)
- UTF-8 encoding across all operating systems
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class ResearchCache:
    """Persistent, atomic disk cache for NotebookLM research responses."""

    def __init__(self, cache_dir: str | Path = "research_cache"):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_hash(notebook_id: str, query: str) -> str:
        """Computes deterministic SHA-256 digest from notebook ID and query text."""
        normalized = f"{notebook_id.strip().lower()}::{query.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _get_entry_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def has(self, notebook_id: str, query: str) -> bool:
        """Checks whether a valid cache entry exists on disk."""
        key = self.compute_hash(notebook_id, query)
        return self._get_entry_path(key).exists()

    def get(self, notebook_id: str, query: str) -> dict[str, Any] | None:
        """Retrieves cached payload if available, else None."""
        key = self.compute_hash(notebook_id, query)
        entry_path = self._get_entry_path(key)
        if not entry_path.exists():
            return None

        try:
            with open(entry_path, encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            return None

    def get_response_text(self, notebook_id: str, query: str) -> str | None:
        """Convenience method to retrieve pure response text."""
        entry = self.get(notebook_id, query)
        if entry and isinstance(entry, dict):
            return entry.get("response")
        return None

    def set(
        self,
        notebook_id: str,
        query: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Atomically stores query response to disk using tempfile + os.replace."""
        key = self.compute_hash(notebook_id, query)
        entry_path = self._get_entry_path(key)

        payload = {
            "cache_key": key,
            "notebook_id": notebook_id,
            "query": query,
            "response": response,
            "timestamp": time.time(),
            "metadata": metadata or {},
        }

        # Atomic disk write
        with tempfile.NamedTemporaryFile(
            "w",
            dir=str(self.cache_dir),
            delete=False,
            encoding="utf-8",
            suffix=".tmp",
        ) as tf:
            json.dump(payload, tf, indent=2, ensure_ascii=False)
            temp_path = tf.name

        os.replace(temp_path, str(entry_path))
        return key

    def clear(self) -> int:
        """Purges all cached entries. Returns number of removed files."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        return count
