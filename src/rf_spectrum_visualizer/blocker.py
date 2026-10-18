"""rf_spectrum_visualizer.blocker

Software-level channel exclusion with JSON persistence.

The Blocker excludes a channel from Analysis recommendations only.  It does
NOT physically block RF or prevent transmissions.  Excluded channels stay
visible in Live Spectrum.  The exclusion list is saved to disk and restored
on restart.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Set

DEFAULT_FILENAME = "blocker_exclusions.json"


class BlockerManager:
    """Manages the set of software-excluded channels with JSON persistence."""

    def __init__(self, filename: str = DEFAULT_FILENAME) -> None:
        self.filename = filename
        self._excluded: Set[int] = set()
        self._load()

    # ------------------------------------------------------------------ persistence
    def _load(self) -> None:
        """Load excluded channels from disk.  Missing file = empty set."""
        if not os.path.exists(self.filename):
            self._excluded = set()
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._excluded = {int(c) for c in data if 0 <= int(c) <= 125}
            else:
                self._excluded = set()
        except (json.JSONDecodeError, OSError, ValueError):
            # Corrupt or unreadable file - start fresh, don't crash the app.
            self._excluded = set()

    def _save(self) -> None:
        """Persist excluded channels to disk."""
        data = sorted(self._excluded)
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(data, f)

    # ------------------------------------------------------------------ API
    @property
    def excluded_channels(self) -> Set[int]:
        """Return a copy of the excluded channel set."""
        return set(self._excluded)

    def is_excluded(self, channel: int) -> bool:
        return channel in self._excluded

    def add(self, channel: int) -> bool:
        """Add a channel to exclusions.  Returns True if newly added."""
        if not (0 <= channel <= 125):
            return False
        if channel in self._excluded:
            return False
        self._excluded.add(channel)
        self._save()
        return True

    def remove(self, channel: int) -> bool:
        """Remove a channel from exclusions.  Returns True if removed."""
        if channel not in self._excluded:
            return False
        self._excluded.discard(channel)
        self._save()
        return True

    def clear(self) -> int:
        """Remove all exclusions.  Returns the number removed."""
        count = len(self._excluded)
        self._excluded.clear()
        self._save()
        return count

    def set_excluded(self, channels: Iterable[int]) -> None:
        """Replace the entire exclusion set (validated 0-125)."""
        self._excluded = {int(c) for c in channels if 0 <= int(c) <= 125}
        self._save()
