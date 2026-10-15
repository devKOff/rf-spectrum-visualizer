"""Persistent JSON blocklist manager for RF Spectrum Visualizer."""

import json
import threading
import time
import os
from typing import Set, List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from config import BlocklistConfig
from exceptions import BlocklistError, InvalidChannelError
from models.blocklist_model import BlocklistEntry


class BlocklistManager:
    """Thread-safe JSON-backed persistent blocklist manager.
    
    Provides software-level channel blocking for channel avoidance recommendations.
    IMPORTANT: "BLOCKED IN SOFTWARE" prevents application selection only;
    it does not physically jam or block radio frequencies or disrupt external devices.
    """
    
    def __init__(self, config: Optional[BlocklistConfig] = None):
        self._config = config or BlocklistConfig()
        self._lock = threading.RLock()
        self._blocked_channels: Dict[int, BlocklistEntry] = {}
        self._load()
    
    def _load(self) -> None:
        """Load blocklist from JSON file."""
        path = Path(self._config.file_path)
        if not path.exists():
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                return
                
            data = json.loads(content)
            
            if not isinstance(data, list):
                raise BlocklistError("Blocklist file format invalid: expected array")
            
            loaded = 0
            for entry_data in data:
                try:
                    entry = BlocklistEntry.from_dict(entry_data)
                    if entry.frequency_mhz != 2400 + entry.channel:
                        entry = BlocklistEntry(
                            channel=entry.channel,
                            frequency_mhz=2400 + entry.channel,
                            blocked_at=entry.blocked_at,
                            reason=entry.reason
                        )
                    self._blocked_channels[entry.channel] = entry
                    loaded += 1
                except (KeyError, ValueError, TypeError):
                    continue
            
        except json.JSONDecodeError as e:
            backup_path = path.with_suffix(f'.corrupted.{int(time.time())}.bak')
            try:
                path.rename(backup_path)
            except OSError:
                pass
            raise BlocklistError(f"Corrupted blocklist file, backed up to {backup_path}: {e}")
        except OSError as e:
            raise BlocklistError(f"Failed to read blocklist file: {e}")
    
    def _save(self) -> None:
        """Save blocklist to JSON file atomically."""
        path = Path(self._config.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        entries = [entry.to_dict() for entry in self._blocked_channels.values()]
        entries.sort(key=lambda x: x["channel"])
        
        data = json.dumps(entries, indent=2, separators=(',', ': '))
        
        if self._config.atomic_writes:
            temp_path = path.with_suffix('.tmp')
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(data)
                temp_path.replace(path)
            except OSError as e:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                raise BlocklistError(f"Atomic write failed: {e}")
        else:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(data)
            except OSError as e:
                raise BlocklistError(f"Write failed: {e}")
    
    def block_channel(self, channel: int, reason: str = "User blocked") -> BlocklistEntry:
        """Add a channel to the blocklist.
        
        Args:
            channel: Channel number to block (0-125)
            reason: Reason for blocking
            
        Returns:
            The created BlocklistEntry
            
        Raises:
            InvalidChannelError: If channel is out of range
            BlocklistError: If save fails
        """
        if not (0 <= channel <= 125):
            raise InvalidChannelError(channel)
        
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            entry = BlocklistEntry(
                channel=channel,
                frequency_mhz=2400 + channel,
                blocked_at=now,
                reason=reason
            )
            self._blocked_channels[channel] = entry
            self._save()
            return entry
    
    def unblock_channel(self, channel: int) -> bool:
        """Remove a channel from the blocklist.
        
        Args:
            channel: Channel number to unblock
            
        Returns:
            True if channel was blocked and removed, False if not blocked
            
        Raises:
            InvalidChannelError: If channel is out of range
            BlocklistError: If save fails
        """
        if not (0 <= channel <= 125):
            raise InvalidChannelError(channel)
        
        with self._lock:
            if channel not in self._blocked_channels:
                return False
            del self._blocked_channels[channel]
            self._save()
            return True
    
    def is_blocked(self, channel: int) -> bool:
        """Check if a channel is blocked.
        
        Args:
            channel: Channel number to check
            
        Returns:
            True if blocked, False otherwise
        """
        if not (0 <= channel <= 125):
            raise InvalidChannelError(channel)
        with self._lock:
            return channel in self._blocked_channels
    
    def get_blocked_channels(self) -> List[int]:
        """Get sorted list of blocked channel numbers.
        
        Returns:
            Sorted list of blocked channels
        """
        with self._lock:
            return sorted(self._blocked_channels.keys())
    
    def get_blocked_entries(self) -> List[BlocklistEntry]:
        """Get all blocklist entries sorted by channel.
        
        Returns:
            List of BlocklistEntry objects
        """
        with self._lock:
            return [self._blocked_channels[ch] for ch in sorted(self._blocked_channels.keys())]
    
    def get_entry(self, channel: int) -> Optional[BlocklistEntry]:
        """Get blocklist entry for a channel.
        
        Args:
            channel: Channel number
            
        Returns:
            BlocklistEntry if blocked, None otherwise
        """
        if not (0 <= channel <= 125):
            raise InvalidChannelError(channel)
        with self._lock:
            return self._blocked_channels.get(channel)
    
    def clear(self) -> int:
        """Clear all blocked channels.
        
        Returns:
            Number of channels that were blocked
        """
        with self._lock:
            count = len(self._blocked_channels)
            self._blocked_channels.clear()
            self._save()
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get blocklist statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "total_blocked": len(self._blocked_channels),
                "channels": sorted(self._blocked_channels.keys()),
                "file_path": self._config.file_path,
                "last_modified": self._get_file_mtime()
            }
    
    def _get_file_mtime(self) -> Optional[str]:
        """Get file modification time."""
        path = Path(self._config.file_path)
        if path.exists():
            mtime = path.stat().st_mtime
            return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return None
    
    def reload(self) -> None:
        """Reload blocklist from disk."""
        with self._lock:
            self._blocked_channels.clear()
            self._load()
    
    def export_json(self) -> str:
        """Export blocklist as JSON string.
        
        Returns:
            JSON string representation
        """
        with self._lock:
            entries = [entry.to_dict() for entry in self._blocked_channels.values()]
            entries.sort(key=lambda x: x["channel"])
            return json.dumps({"blocklist": entries}, indent=2)
    
    def import_json(self, json_str: str) -> int:
        """Import blocklist from JSON string.
        
        Args:
            json_str: JSON string with blocklist
            
        Returns:
            Number of entries imported
            
        Raises:
            BlocklistError: If JSON is invalid
        """
        try:
            data = json.loads(json_str)
            entries = data.get("blocklist", data) if isinstance(data, dict) else data
        except json.JSONDecodeError as e:
            raise BlocklistError(f"Invalid JSON: {e}")
        
        with self._lock:
            self._blocked_channels.clear()
            loaded = 0
            for entry_data in entries:
                try:
                    entry = BlocklistEntry.from_dict(entry_data)
                    if not (0 <= entry.channel <= 125):
                        continue
                    if entry.frequency_mhz != 2400 + entry.channel:
                        entry = BlocklistEntry(
                            channel=entry.channel,
                            frequency_mhz=2400 + entry.channel,
                            blocked_at=entry.blocked_at,
                            reason=entry.reason
                        )
                    self._blocked_channels[entry.channel] = entry
                    loaded += 1
                except (KeyError, ValueError, TypeError):
                    continue
            self._save()
            return loaded