"""Disk: zaplneni rootu + rychlost cteni/zapisu (rozdil citacu)."""

import time

import psutil


class DiskCollector:
    def __init__(self, mount="/"):
        self._mount = mount
        self._prev_t = None
        self._prev_read = 0
        self._prev_write = 0

    def read(self):
        try:
            usage = psutil.disk_usage(self._mount)
        except Exception:
            return {"available": False}

        try:
            io = psutil.disk_io_counters()
        except Exception:
            io = None

        now = time.monotonic()
        if io is not None:
            if self._prev_t is None:
                r_rate = w_rate = 0.0
            else:
                dt = now - self._prev_t
                r_rate = (io.read_bytes - self._prev_read) / dt if dt > 0 else 0.0
                w_rate = (io.write_bytes - self._prev_write) / dt if dt > 0 else 0.0
            self._prev_t = now
            self._prev_read = io.read_bytes
            self._prev_write = io.write_bytes
        else:
            r_rate = w_rate = 0.0

        return {
            "available": True,
            "percent": usage.percent,
            "used": usage.used,
            "total": usage.total,
            "read_rate": r_rate,
            "write_rate": w_rate,
        }
