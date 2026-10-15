"""Sit: rychlost odvozena z rozdilu citacu mezi dvema ctenimi.

Stav je v instanci (driv module-level _net_prev). Prvni cteni vzdy vraci
nulovou rychlost, protoze neni baseline - proto se v main() vola prime().
"""

import time

import psutil


class NetCollector:
    def __init__(self):
        self._prev_t = None
        self._prev_sent = 0
        self._prev_recv = 0

    def read(self):
        io = psutil.net_io_counters()
        now = time.monotonic()
        if self._prev_t is None:
            up = down = 0.0
        else:
            dt = now - self._prev_t
            up = (io.bytes_sent - self._prev_sent) / dt if dt > 0 else 0.0
            down = (io.bytes_recv - self._prev_recv) / dt if dt > 0 else 0.0
        self._prev_t = now
        self._prev_sent = io.bytes_sent
        self._prev_recv = io.bytes_recv
        return {
            "up": up, "down": down,
            "total_up": io.bytes_sent, "total_recv": io.bytes_recv,
        }
