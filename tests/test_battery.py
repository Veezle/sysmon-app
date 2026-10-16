"""Baterie: cteni ze sysfs a historie s relativnimi casy.

Skutecny /sys se predstira podstrcenim POWER_SUPPLY - stejny trik, jakym
testy portu podstrkuji TCP_FILES.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from sysmon_app.collectors import battery
from sysmon_app.config import BATTERY_HISTORY_MAX, BATTERY_HISTORY_SEC


class BatteryTest(unittest.TestCase):
    def use_supply(self, files):
        """Postavi falesny sysfs a podstrci ho kolektoru. Uklidi po sobe."""
        root = tempfile.mkdtemp(prefix="fakesys")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for name, attrs in files.items():
            item = os.path.join(root, name)
            os.mkdir(item)
            for attr, value in attrs.items():
                with open(os.path.join(item, attr), "w") as f:
                    # sysfs pise hodnotu s koncovym \n; bez nej by testy
                    # nepoznaly, kdyby z battery.py zmizelo strip()
                    f.write(value + "\n")
        self.use_path(root)

    def use_path(self, path):
        orig = battery.POWER_SUPPLY
        battery.POWER_SUPPLY = path
        self.addCleanup(setattr, battery, "POWER_SUPPLY", orig)

    def read(self):
        return battery.BatteryCollector().read()


class ReadTest(BatteryTest):
    def test_missing_sysfs_is_not_fatal(self):
        self.use_path("/neexistuje/power_supply")
        self.assertFalse(self.read()["available"])

    def test_only_ac_no_battery(self):
        self.use_supply({"AC": {"type": "Mains", "online": "1"}})
        result = self.read()
        self.assertFalse(result["available"])
        self.assertIn("Baterie nebyla nalezena", result["error"])

    def test_energy_series_gives_remaining_time(self):
        """38 Wh pri 10 W = 3,8 h = 228 minut."""
        self.use_supply({
            "BAT0": {
                "type": "Battery", "capacity": "77", "status": "Discharging",
                "energy_now": "38000000", "power_now": "10000000",
            },
            "AC": {"type": "Mains", "online": "0"},
        })
        result = self.read()
        self.assertTrue(result["available"])
        self.assertEqual(result["percent"], 77)
        self.assertEqual(result["status_label"], "Vybíjí se")
        self.assertIs(result["ac_online"], False)
        self.assertEqual(result["time_remaining_minutes"], 228)

    def test_charge_series_is_the_fallback(self):
        """Nektere stroje maji charge_now/current_now misto energy/power."""
        self.use_supply({
            "BAT0": {
                "type": "Battery", "capacity": "50", "status": "Discharging",
                "charge_now": "2000000", "current_now": "1000000",
            },
        })
        self.assertEqual(self.read()["time_remaining_minutes"], 120)

    def test_ac_online_with_several_supplies(self):
        """Realny stroj ma ACAD online=1 a dve USB-C, z toho jednu online=0.

        Staci jediny zapnuty zdroj; pocet zdroju ani poradi, v jakem je
        listdir vrati, nesmi rozhodovat.
        """
        cases = (
            {"ACAD": {"type": "Mains", "online": "1"}},
            {"USBC": {"type": "USB", "online": "1"}},
            {"USBC": {"type": "USB_C", "online": "1"}},
            {"AC1": {"type": "Mains", "online": "1"},
             "AC2": {"type": "Mains", "online": "0"}},
            {"AC1": {"type": "Mains", "online": "0"},
             "AC2": {"type": "Mains", "online": "1"}},
        )
        for extra in cases:
            with self.subTest(supplies=sorted(extra)):
                supplies = dict(extra)
                supplies["BAT0"] = {
                    "type": "Battery", "capacity": "80", "status": "Not charging",
                }
                self.use_supply(supplies)
                self.assertIs(self.read()["ac_online"], True)

    def test_not_charging_has_no_remaining_time(self):
        """Na adapteru se cas do vybiti nepocita - 'Not charging' neni vybijeni.

        power_now je zamerne vetsi nez nula, aby tudy proteklo i pripadne
        zruseni vetve `if status == "Discharging"`.
        """
        self.use_supply({
            "BAT0": {
                "type": "Battery", "capacity": "80", "status": "Not charging",
                "energy_now": "42410000", "power_now": "10000000",
            },
        })
        result = self.read()
        self.assertIsNone(result["time_remaining_minutes"])
        self.assertEqual(result["status_label"], "Nenabíjí se")

    def test_missing_capacity_does_not_break_the_card(self):
        """Nektere baterie `capacity` nemaji; karta se nesmi zrusit ani spadnout."""
        self.use_supply({"BAT0": {"type": "Battery", "status": "Discharging"}})
        result = self.read()
        self.assertTrue(result["available"])
        self.assertIsNone(result["percent"])

    def test_zero_power_now_does_not_raise(self):
        """power_now = 0 je na realnem stroji bezny - guard ho nesmi pustit k deleni.

        Bez guardu `power > 0` by `energy / power` vyhodil ZeroDivisionError
        a ten z `read()` unika: vnitrni `except` chyta jen (TypeError, ValueError),
        vnejsi jen OSError.
        """
        self.use_supply({
            "BAT0": {
                "type": "Battery", "capacity": "50", "status": "Discharging",
                "energy_now": "2000000", "power_now": "0",
            },
        })
        result = self.read()
        self.assertEqual(result["status"], "Discharging")
        self.assertIsNone(result["time_remaining_minutes"])


class HistoryTest(unittest.TestCase):
    def test_empty_history(self):
        self.assertEqual(battery.BatteryCollector().history(), [])

    def test_times_are_relative_to_the_first_sample(self):
        collector = battery.BatteryCollector()
        # _history je privatni, ale plnit ho pres worker by znamenalo cekat
        # na jeho interval - tady jde jen o prevod casu na relativni.
        collector._history.append((1000, 80))
        collector._history.append((1060, 79))
        self.assertEqual(
            collector.history(),
            [{"t": 0, "v": 80}, {"t": 60, "v": 79}],
        )


class ConfigTest(unittest.TestCase):
    def test_defaults_come_from_config(self):
        """Interval i strop historie jdou z konfigurace - kvuli tomu se menil import."""
        collector = battery.BatteryCollector()
        self.assertEqual(collector._interval, BATTERY_HISTORY_SEC)
        self.assertEqual(collector._history.maxlen, BATTERY_HISTORY_MAX)


class WorkerTest(BatteryTest):
    def test_loop_samples_and_honours_maxlen(self):
        """Dvouminutova smycka se neda cekat - podstrci se interval i hodiny.

        Terminatorem je `time.time()` uvnitr tela: `SystemExit` je
        `BaseException`, takze ho vnitrni `except Exception` nespolkne. Kdyby
        smycku ukoncoval jen `sleep`, mutant bez `time.sleep` by test
        zacyklil misto aby ho shodil. Omezeny seznam spanku je zalozni brzda
        pro pripad, ze se `time.time()` v mutovanem kode vubec nezavola.
        """
        self.use_supply({
            "BAT0": {"type": "Battery", "capacity": "50", "status": "Charging"},
        })
        collector = battery.BatteryCollector(interval=0, max_samples=2)
        clock = mock.patch.object(
            battery.time, "time", side_effect=[1000, 1060, 1120, SystemExit]
        )
        clock.start()
        self.addCleanup(clock.stop)
        sleep = mock.patch.object(battery.time, "sleep", side_effect=[None] * 20)
        sleep_mock = sleep.start()
        self.addCleanup(sleep.stop)

        with self.assertRaises(SystemExit):
            collector._loop()

        # Tri vzorky, strop dva: zustaly posledni dva a casy jsou relativni.
        self.assertEqual(collector.history(), [{"t": 0, "v": 50}, {"t": 60, "v": 50}])
        # A mezi vzorky se spi: tri dokoncene vzorky, tri spanky. Bez toho by
        # smycka tocila CPU naprazdno - a test by to jinak nepoznal.
        self.assertEqual(sleep_mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
