"""Usage counters: requests per app per hour, kept in SQLite so they survive restarts.

Requests are counted in memory (AppInstance.touch) and written by flush(), in the executor, once a minute
and at shutdown. Each instance keeps its own database in its log folder; sum them for a fleet total.
"""
import asyncio
import logging
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

DB_FILE = "usage.sqlite3"
SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (app_id TEXT NOT NULL, day TEXT NOT NULL, hour INTEGER NOT NULL,
                                  count INTEGER NOT NULL, PRIMARY KEY (app_id, day, hour));
CREATE TABLE IF NOT EXISTS totals (app_id TEXT PRIMARY KEY, count INTEGER NOT NULL);
"""


class AppUsage(dict):
    """{"YYYY-MM-DD": [requests per hour] * 24} of one app, its lifetime total, and what is not saved yet."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total = 0
        self.pending = {}  # (day, hour) -> requests counted since the last flush

    def add(self, when=None):
        when = when or datetime.now()
        day = when.date().isoformat()
        self.setdefault(day, [0] * 24)[when.hour] += 1
        self.total += 1
        self.pending[(day, when.hour)] = self.pending.get((day, when.hour), 0) + 1

    def today(self):
        return self.get(date.today().isoformat(), [0] * 24)


class UsageStore:
    """Every app's AppUsage, loaded from and saved to `path`. `retention_days` 0 keeps every day."""

    def __init__(self, path, retention_days=90):
        self.path = Path(path)
        self.retention_days = retention_days
        self.apps = {}
        self._pruned_on = None

    def for_app(self, app_id):
        """The AppUsage of `app_id`; the same object for every instance of the app."""
        return self.apps.setdefault(app_id, AppUsage())

    def _cutoff(self):
        return (date.today() - timedelta(days=self.retention_days)).isoformat() if self.retention_days else ""

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.executescript(SCHEMA)
        return db

    def load(self):
        """Read the retained days and the totals. Blocking: run it in the executor."""
        try:
            with closing(self._connect()) as db:
                for app_id, day, hour, count in db.execute(
                        "SELECT app_id, day, hour, count FROM usage WHERE day >= ?", (self._cutoff(),)):
                    if 0 <= hour < 24:
                        self.for_app(app_id).setdefault(day, [0] * 24)[hour] += count
                for app_id, count in db.execute("SELECT app_id, count FROM totals"):
                    self.for_app(app_id).total += count
        except sqlite3.Error as exc:
            log.warning("Cannot read usage from %s: %s", self.path, exc)

    def take_pending(self):
        """[(app_id, day, hour, count)] counted since the last flush; the caller must save or restore them."""
        rows = []
        for app_id, usage in self.apps.items():
            pending, usage.pending = usage.pending, {}
            rows += [(app_id, day, hour, count) for (day, hour), count in pending.items()]
        return rows

    def restore_pending(self, rows):
        for app_id, day, hour, count in rows:
            pending = self.for_app(app_id).pending
            pending[(day, hour)] = pending.get((day, hour), 0) + count

    def write(self, rows):
        """Add `rows` to the database and, once a day, drop days past the retention. Blocking."""
        today = date.today()
        with closing(self._connect()) as db, db:
            db.executemany("INSERT INTO usage (app_id, day, hour, count) VALUES (?, ?, ?, ?) "
                           "ON CONFLICT (app_id, day, hour) DO UPDATE SET count = count + excluded.count", rows)
            totals = {}
            for app_id, _, _, count in rows:
                totals[app_id] = totals.get(app_id, 0) + count
            db.executemany("INSERT INTO totals (app_id, count) VALUES (?, ?) "
                           "ON CONFLICT (app_id) DO UPDATE SET count = count + excluded.count", totals.items())
            if self.retention_days and self._pruned_on != today:
                db.execute("DELETE FROM usage WHERE day < ?", (self._cutoff(),))
        if self.retention_days and self._pruned_on != today:
            self._pruned_on = today
            cutoff = self._cutoff()
            for usage in self.apps.values():
                for day in [d for d in usage if d < cutoff]:
                    del usage[day]

    async def flush(self):
        """Save what was counted since the last flush, from the executor; kept for the next try on failure."""
        rows = self.take_pending()
        if not rows and self._pruned_on == date.today():
            return
        try:
            await asyncio.get_running_loop().run_in_executor(None, self.write, rows)
        except (sqlite3.Error, OSError) as exc:
            self.restore_pending(rows)
            log.warning("Cannot save usage to %s: %s", self.path, exc)
