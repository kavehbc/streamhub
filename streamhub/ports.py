"""Internal port leases for apps."""
from streamhub.platform_utils import port_is_free


class PortsExhausted(RuntimeError):
    """Every port in the range is reserved, leased or in use."""


class PortAllocator:
    """Hands out internal ports from a fixed range, skipping reserved and busy ones, and reuses freed ports."""

    def __init__(self, first, last, exceptions=(), is_free=port_is_free):
        self.first = first
        self.last = last
        self.exceptions = set(exceptions)
        self._is_free = is_free
        self._leased = set()

    def allocate(self):
        """Lowest port that is not reserved, not leased, and free on this machine (bind test)."""
        for port in range(self.first, self.last + 1):
            if port in self.exceptions or port in self._leased:
                continue
            if self._is_free(port):
                self._leased.add(port)
                return port
        raise PortsExhausted(f"No free port between {self.first} and {self.last}")

    def release(self, port):
        self._leased.discard(port)

    @property
    def leased(self):
        return frozenset(self._leased)
