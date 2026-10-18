"""Phase 5 tests for blocker.py

Run on any machine - no pyrf24, no radio, no display required.
Uses a temporary JSON file so no real files are touched.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from rf_spectrum_visualizer.blocker import BlockerManager


def test_blocker_starts_empty_when_no_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm = BlockerManager(filename=path)
        assert bm.excluded_channels == set()


def test_blocker_add_and_remove():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm = BlockerManager(filename=path)

        assert bm.add(5) is True
        assert bm.add(37) is True
        assert bm.add(5) is False  # already added
        assert bm.is_excluded(5) is True
        assert bm.is_excluded(37) is True
        assert bm.is_excluded(100) is False

        assert bm.remove(5) is True
        assert bm.remove(5) is False  # already removed
        assert bm.is_excluded(5) is False
        assert bm.is_excluded(37) is True


def test_blocker_clear():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm = BlockerManager(filename=path)
        bm.add(1)
        bm.add(2)
        bm.add(3)
        assert bm.clear() == 3
        assert bm.excluded_channels == set()


def test_blocker_persists_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm1 = BlockerManager(filename=path)
        bm1.add(12)
        bm1.add(62)

        bm2 = BlockerManager(filename=path)
        assert bm2.is_excluded(12) is True
        assert bm2.is_excluded(62) is True
        assert bm2.is_excluded(100) is False


def test_blocker_rejects_out_of_range():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm = BlockerManager(filename=path)
        assert bm.add(-1) is False
        assert bm.add(126) is False
        assert bm.excluded_channels == set()


def test_blocker_invalid_file_starts_empty():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        bm = BlockerManager(filename=path)
        assert bm.excluded_channels == set()


def test_blocker_set_excluded_replaces():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm = BlockerManager(filename=path)
        bm.add(1)
        bm.set_excluded([5, 10])
        assert bm.excluded_channels == {5, 10}
        assert bm.is_excluded(1) is False


def test_blocker_excluded_channel_list_format():
    """Excluded channels render as 'N - FREQ MHz' for the UI list."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "exclusions.json")
        bm = BlockerManager(filename=path)
        bm.add(5)
        bm.add(100)

        items = [f"{ch} - {2400 + ch} MHz" for ch in sorted(bm.excluded_channels)]
        assert items == ["5 - 2405 MHz", "100 - 2500 MHz"]
