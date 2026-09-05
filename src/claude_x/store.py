"""Append-only JSONL storage for posts, mentions and metrics.

Why JSONL: the records are written once, read in bulk, and occasionally need a
targeted delete. A database would buy nothing at this volume, and a plain text
file stays readable by both the user and an agent.

`delete_where` exists for a specific reason: X's developer agreement requires
that content deleted on X is deleted from local storage too.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class JsonlStore:
    """A single .jsonl file holding one dict per line."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: dict[str, Any]) -> None:
        """Add one record. Creates the file and its parent on first write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Yield records, skipping any line that isn't valid JSON.

        A corrupt line shouldn't make the whole history unreadable — losing one
        record is better than losing all of them.
        """
        if not self.path.is_file():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed

    def read_all(self) -> list[dict[str, Any]]:
        return list(self)

    def find(self, key: str, value: Any) -> list[dict[str, Any]]:
        return [record for record in self if record.get(key) == value]

    def exists(self, key: str, value: Any) -> bool:
        return any(record.get(key) == value for record in self)

    def delete_where(self, key: str, value: Any) -> int:
        """Remove every record whose `key` equals `value`; return how many went.

        Rewrites via a temp file in the same directory so an interrupted delete
        can't truncate the history.
        """
        if not self.path.is_file():
            return 0

        kept: list[dict[str, Any]] = []
        removed = 0
        for record in self:
            if record.get(key) == value:
                removed += 1
            else:
                kept.append(record)

        if removed == 0:
            return 0

        descriptor, temp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=self.path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in kept:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            os.replace(temp_name, self.path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

        return removed
