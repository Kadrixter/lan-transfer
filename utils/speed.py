"""Pomiar prędkości transferu w przesuwanym oknie czasowym."""
import threading
import time
from collections import deque


class SpeedMeter:
    def __init__(self, window=2.0):
        self.window = window
        self._samples = deque()
        self._lock = threading.Lock()
        self._start = time.monotonic()

    def reset(self):
        with self._lock:
            self._samples.clear()
            self._start = time.monotonic()

    def add(self, n):
        now = time.monotonic()
        with self._lock:
            self._samples.append((now, n))
            self._trim(now)

    def _trim(self, now):
        while self._samples and now - self._samples[0][0] > self.window:
            self._samples.popleft()

    def speed(self):
        """Bajty na sekundę."""
        now = time.monotonic()
        with self._lock:
            self._trim(now)
            total = sum(n for _, n in self._samples)
            span = min(self.window, max(now - self._start, 0.25))
        return total / span
