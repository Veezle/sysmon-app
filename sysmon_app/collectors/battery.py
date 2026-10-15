"""Baterie: stav ze sysfs + 24h historie vzorkovana na pozadi.

Cte se primo /sys/class/power_supply, bez dalsich knihoven.
"""

import os
import threading
import time
from collections import deque

from sysmon_app.config import BATTERY_HISTORY_MAX, BATTERY_HISTORY_SEC

POWER_SUPPLY = "/sys/class/power_supply"

# AC adapter muze byt evidovany pod ruznymi typy (notebook, USB-C, ...)
AC_TYPES = ("mains", "usb", "usb_c", "wireless")

STATUS_LABELS = {
    "Charging": "Nabíjí se",
    "Discharging": "Vybíjí se",
    "Full": "Nabitá",
    "Not charging": "Nenabíjí se",
    "Unknown": "Neznámý stav",
}


class BatteryCollector:
    def __init__(self, interval=BATTERY_HISTORY_SEC, max_samples=BATTERY_HISTORY_MAX):
        self._interval = interval
        self._history = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def read(self):
        """Cte stav baterie z Linux sysfs; nevyzaduje dalsi knihovny."""
        base = POWER_SUPPLY
        if not os.path.isdir(base):
            return {"available": False, "error": "Informace o baterii nejsou dostupné"}

        battery = None
        ac_online = None
        try:
            for name in os.listdir(base):
                item = os.path.join(base, name)
                try:
                    with open(os.path.join(item, "type")) as f:
                        supply_type = f.read().strip().lower()
                except (OSError, IOError):
                    continue

                if supply_type == "battery" and battery is None:
                    battery = item
                elif supply_type in AC_TYPES:
                    try:
                        with open(os.path.join(item, "online")) as f:
                            online = f.read().strip() == "1"
                        ac_online = online if ac_online is None else (ac_online or online)
                    except (OSError, IOError):
                        pass

            if battery is None:
                return {"available": False, "error": "Baterie nebyla nalezena"}

            def read_value(filename):
                try:
                    with open(os.path.join(battery, filename)) as f:
                        return f.read().strip()
                except (OSError, IOError, ValueError):
                    return None

            raw_capacity = read_value("capacity")
            try:
                capacity = max(0, min(100, int(raw_capacity))) if raw_capacity is not None else None
            except ValueError:
                capacity = None

            status = read_value("status") or "Unknown"

            remaining_hours = None
            if status == "Discharging":
                for energy_name, power_name in (
                    ("energy_now", "power_now"),
                    ("charge_now", "current_now"),
                ):
                    try:
                        energy = float(read_value(energy_name))
                        power = float(read_value(power_name))
                        if energy >= 0 and power > 0:
                            remaining_hours = energy / power
                            break
                    except (TypeError, ValueError):
                        continue

            result = {
                "available": capacity is not None or status != "Unknown",
                "percent": capacity,
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "ac_online": ac_online,
                "time_remaining_minutes": (
                    round(remaining_hours * 60) if remaining_hours is not None else None
                ),
            }
            if not result["available"]:
                result["error"] = "Údaje o baterii nejsou dostupné"
            return result
        except OSError as exc:
            return {"available": False, "error": f"Chyba čtení baterie: {exc}"}

    def history(self):
        """Vzorky jako {t, v}, kde t je relativni cas v sekundach od prvniho vzorku."""
        with self._lock:
            if not self._history:
                return []
            t0 = self._history[0][0]
            return [{"t": ts - t0, "v": p} for ts, p in self._history]

    def start_worker(self):
        threading.Thread(
            target=self._loop, name="sysmon-battery-history", daemon=True,
        ).start()

    def _loop(self):
        """Vzorkuje baterii kazde 2 minuty pro 24h graf."""
        while True:
            try:
                b = self.read()
                if b.get("available") and b.get("percent") is not None:
                    with self._lock:
                        self._history.append((int(time.time()), int(b["percent"])))
            except Exception:
                pass
            time.sleep(self._interval)
