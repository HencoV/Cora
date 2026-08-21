"""
Central Settings helper for per-guild, per-cog configuration.

Usage examples (async):
    from cogs.settings_helper import settings

    # set a value for guild 12345
    await settings.set(12345, 'twitch', 'auto_delete_seconds', 30)

    # read it back (falls back to guild 0/global if not set)
    val = await settings.get(12345, 'twitch', 'auto_delete_seconds', default=0)

Global defaults: use `guild_id=0` to set a default value used when a guild-specific value is not present.

This module provides simple JSON-serialised storage on top of SQLite and async-friendly methods.
"""

import sqlite3
import json
import asyncio
from typing import Any, Optional, List, Tuple


class SettingsManager:
    def __init__(self, db_path: str = 'settings.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self.lock = asyncio.Lock()

    def _init_db(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER NOT NULL,
                cog TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (guild_id, cog, key)
            )
            '''
        )
        self.conn.commit()

    async def set(self, guild_id: Optional[int], cog: str, key: str, value: Any) -> None:
        """Set a value for a guild and cog. Use guild_id=0 for global defaults.

        The value is JSON-serialized before storage.
        """
        if guild_id is None:
            guild_id = 0
        payload = json.dumps(value)

        async with self.lock:
            def _write():
                cur = self.conn.cursor()
                cur.execute(
                    'INSERT OR REPLACE INTO settings (guild_id, cog, key, value) VALUES (?, ?, ?, ?)',
                    (guild_id, cog, key, payload),
                )
                self.conn.commit()

            await asyncio.to_thread(_write)

    async def get(self, guild_id: Optional[int], cog: str, key: str, default: Any = None) -> Any:
        """Retrieve a value. Falls back to global (guild_id=0) if not found for the guild.

        Returns `default` if no value is found.
        """
        if guild_id is None:
            guild_id = 0

        async with self.lock:
            def _read() -> Optional[str]:
                cur = self.conn.cursor()
                cur.execute('SELECT value FROM settings WHERE guild_id = ? AND cog = ? AND key = ?', (guild_id, cog, key))
                row = cur.fetchone()
                if row:
                    return row['value']

                if guild_id != 0:
                    # fallback to global
                    cur.execute('SELECT value FROM settings WHERE guild_id = 0 AND cog = ? AND key = ?', (cog, key))
                    row = cur.fetchone()
                    if row:
                        return row['value']

                return None

            raw = await asyncio.to_thread(_read)

        if raw is None:
            return default

        try:
            return json.loads(raw)
        except Exception:
            return raw

    async def delete(self, guild_id: Optional[int], cog: str, key: str) -> int:
        """Delete a key for a guild/cog. Returns number of rows deleted."""
        if guild_id is None:
            guild_id = 0

        async with self.lock:
            def _del() -> int:
                cur = self.conn.cursor()
                cur.execute('DELETE FROM settings WHERE guild_id = ? AND cog = ? AND key = ?', (guild_id, cog, key))
                self.conn.commit()
                return cur.rowcount

            return await asyncio.to_thread(_del)

    async def all_for_guild(self, guild_id: Optional[int]) -> List[Tuple[str, str, Any]]:
        """Return list of (cog, key, value) for the given guild_id."""
        if guild_id is None:
            guild_id = 0

        async with self.lock:
            def _all():
                cur = self.conn.cursor()
                cur.execute('SELECT cog, key, value FROM settings WHERE guild_id = ?', (guild_id,))
                rows = cur.fetchall()
                return [(r['cog'], r['key'], json.loads(r['value'])) for r in rows]

            return await asyncio.to_thread(_all)

    async def all_for_cog(self, cog: str) -> List[Tuple[int, str, Any]]:
        """Return list of (guild_id, key, value) for the given cog."""
        async with self.lock:
            def _all():
                cur = self.conn.cursor()
                cur.execute('SELECT guild_id, key, value FROM settings WHERE cog = ?', (cog,))
                rows = cur.fetchall()
                return [(r['guild_id'], r['key'], json.loads(r['value'])) for r in rows]

            return await asyncio.to_thread(_all)


# Singleton instance to import from other modules
settings = SettingsManager()
