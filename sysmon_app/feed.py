"""SnapshotFeed - jeden sberny cyklus pro vsechny odberatele.

Proc takhle: driv cetl kolektory kazdy HTTP pozadavek z vlastniho vlakna,
takze se rate-based kolektory (sit, disk) navzajem rozbilyly - v sysmonu
zapsana a prijata vada. Tady tiká jediny cyklus a odberatele se jen vezou.

Odberatel se prihlasi tim, ze si zapamatuje `snapshot_seq()` a pak ceka
`wait_for(seq, timeout)`. Zadny fronta k odberateli, zadne kopirovani
snapshotu pro kazdeho - vsichni dostanou ten sam dict (jen se v nem nemeni).
"""

import threading

from sysmon_app.config import TICK_SEC


class SnapshotFeed:
    def __init__(self, monitor, interval=TICK_SEC):
        self._monitor = monitor
        self._interval = interval
        self._cond = threading.Condition()
        self._seq = 0
        self._latest = None
        self._stop = threading.Event()
        self._thread = None

    def publish_once(self):
        """Sebrat jeden snapshot a rozeslat ho odberatelum.

        Vzorkovani je zamerne mimo zamek - drzet zamek pres cteni /proc
        a `docker stats` by zastavilo vsechny odberatele.
        """
        snapshot = self._monitor.snapshot()
        with self._cond:
            self._latest = snapshot
            self._seq += 1
            self._cond.notify_all()

    def latest(self):
        """Posledni snapshot, nebo None kdyz jeste zadny nebyl."""
        with self._cond:
            return self._latest

    def snapshot_seq(self):
        with self._cond:
            return self._seq

    def wait_for(self, last_seq, timeout):
        """Pocka na snapshot novejsi nez last_seq. Vraci (seq, snapshot).

        Po timeoutu vraci (last_seq, None) - volatel to bere jako "nic
        noveho", ne jako chybu.
        """
        with self._cond:
            self._cond.wait_for(
                lambda: self._seq != last_seq or self._stop.is_set(), timeout,
            )
            if self._seq == last_seq:
                return last_seq, None
            return self._seq, self._latest

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="sysmon-app-feed", daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _loop(self):
        # Prvni sber hned: jinak by prvni pozadavek cekal cely TICK_SEC.
        while not self._stop.is_set():
            try:
                self.publish_once()
            except Exception:
                # Sber se nesmi rozbit smycku - dalsi tik to zkusi znovu.
                pass
            self._stop.wait(self._interval)
