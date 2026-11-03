"""Daily job on the IOLoop, in a configurable time zone (no extra thread)."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tornado.ioloop import IOLoop

log = logging.getLogger(__name__)


def next_run(at, tz=None, now=None):
    """Next datetime (aware) for the daily time `at` ("HH:MM") in zone `tz` (None = local)."""
    zone = ZoneInfo(tz) if tz else None
    now = now or datetime.now(zone).astimezone(zone)
    hour, minute = (int(x) for x in at.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


class DailyJob:
    """Runs `callback` every day at `at`; it re-arms itself after each run, even a failed one."""

    def __init__(self, at, tz, callback):
        self.at = at
        self.tz = tz
        self.callback = callback
        self._handle = None

    def start(self):
        self.cancel()
        when = next_run(self.at, self.tz)
        delay = (when - datetime.now(when.tzinfo)).total_seconds()
        self._handle = IOLoop.current().call_later(max(delay, 1), self._fire)  # recomputed daily, so DST-safe
        log.info("Memory clean scheduled at %s", when.isoformat(timespec="minutes"))

    def cancel(self):
        if self._handle is not None:
            IOLoop.current().remove_timeout(self._handle)
            self._handle = None

    async def _fire(self):
        self._handle = None
        try:
            await self.callback()
        except Exception:
            log.exception("Scheduled job failed")
        finally:
            self.start()
