"""Server-side session records: an inventory of logins, and revocation.

Each login gets a random session ID, kept in the signed `user` cookie and in an SQLite file in the config
folder. Revoking a session, or every session of a user, is written at once; every hub instance that
shares the config folder reloads the revocations every REFRESH_SECONDS, so a revoked session is refused
everywhere within that time. When the file cannot be used, revocation still works, on this instance only.
"""
import asyncio
import logging
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

log = logging.getLogger(__name__)

REFRESH_SECONDS = 5
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
                                     role TEXT NOT NULL, created REAL NOT NULL, last_seen REAL NOT NULL,
                                     address TEXT NOT NULL, agent TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS users_revoked (user TEXT PRIMARY KEY, not_before REAL NOT NULL);
"""


def user_key(name, source):
    return f"{source}:{name}"


class SessionStore:
    """Session inventory and revocations, shared through `path` by the instances of one config folder."""

    def __init__(self, path, max_age_days):
        self.path = Path(path)
        self.max_age_days = max_age_days
        self.revoked = set()   # session IDs
        self.not_before = {}   # user_key -> time: sessions issued before it are refused
        self.seen = {}         # session ID -> last request, not saved yet
        self._writes = set()   # writes in progress (settle() waits for them)
        self._warned = False

    # -- checks, on every request (memory only) --
    def allowed(self, sid, key, issued):
        """False for a revoked session, or one issued before its user's sessions were revoked."""
        if sid and sid in self.revoked:
            return False
        return not (key in self.not_before and (issued or 0) < self.not_before[key])

    def is_valid(self, sid, key, issued):
        """`allowed`, and records the request for the inventory's "last seen"."""
        if not self.allowed(sid, key, issued):
            return False
        if sid:
            self.seen[sid] = time.time()
        return True

    # -- changes --
    async def created(self, sid, user, address, agent):
        now = time.time()
        await self._write("INSERT OR REPLACE INTO sessions (id, name, source, role, created, last_seen, address, "
                          "agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (sid, user.name, user.source, user.role, now, now, address or "", (agent or "")[:200]))

    async def revoke(self, sid):
        self.revoked.add(sid)
        await self._write("UPDATE sessions SET revoked = 1 WHERE id = ?", (sid,))

    async def revoke_user(self, name, source):
        """Refuse every session of this user issued until now (also sessions from before 2.2)."""
        key, now = user_key(name, source), time.time()
        self.not_before[key] = now
        await self._write("INSERT OR REPLACE INTO users_revoked (user, not_before) VALUES (?, ?)", (key, now))
        await self._write("UPDATE sessions SET revoked = 1 WHERE name = ? AND source = ?", (name, source))

    @staticmethod
    def new_id():
        return secrets.token_urlsafe(18)

    # -- storage --
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.executescript(SCHEMA)
        return db

    def _failed(self, exc):
        if not self._warned:
            self._warned = True
            log.warning("Session file %s is not usable (%s); revocations apply to this instance only",
                        self.path, exc)

    async def _write(self, sql, params):
        def write():
            with closing(self._connect()) as db, db:
                db.execute(sql, params)
        future = asyncio.get_running_loop().run_in_executor(None, write)
        self._writes.add(future)
        try:
            await future
        except (sqlite3.Error, OSError) as exc:
            self._failed(exc)
        finally:
            self._writes.discard(future)

    async def settle(self):
        """Wait for the writes in progress (at shutdown)."""
        if self._writes:
            await asyncio.wait(list(self._writes))

    def sync(self):
        """Save last-seen times, drop expired records, reload revocations. Blocking: run it in the executor."""
        seen, self.seen = self.seen, {}
        cutoff = time.time() - self.max_age_days * 86400
        try:
            with closing(self._connect()) as db, db:
                db.executemany("UPDATE sessions SET last_seen = ? WHERE id = ?", [(t, s) for s, t in seen.items()])
                db.execute("DELETE FROM sessions WHERE created < ?", (cutoff,))
                db.execute("DELETE FROM users_revoked WHERE not_before < ?", (cutoff,))
                revoked = {row[0] for row in db.execute("SELECT id FROM sessions WHERE revoked = 1")}
                not_before = dict(db.execute("SELECT user, not_before FROM users_revoked"))
        except (sqlite3.Error, OSError) as exc:
            self._failed(exc)
            return
        self.revoked |= revoked
        for key, value in not_before.items():
            self.not_before[key] = max(value, self.not_before.get(key, 0))

    async def refresh(self):
        await asyncio.get_running_loop().run_in_executor(None, self.sync)

    def active(self):
        """Sessions that are neither revoked nor expired, newest first. Blocking: run it in the executor."""
        cutoff = time.time() - self.max_age_days * 86400
        try:
            with closing(self._connect()) as db:
                rows = db.execute("SELECT id, name, source, role, created, last_seen, address, agent FROM sessions "
                                  "WHERE revoked = 0 AND created >= ? ORDER BY last_seen DESC", (cutoff,)).fetchall()
        except (sqlite3.Error, OSError) as exc:
            self._failed(exc)
            return []
        keys = ("id", "name", "source", "role", "created", "last_seen", "address", "agent")
        sessions = [dict(zip(keys, row)) for row in rows]
        return [s for s in sessions if self.allowed(s["id"], user_key(s["name"], s["source"]), s["created"])]
