"""Kontrakt snapshotu - jedina vec, na ktere stoji UI i telefon.

Kolektory se nepredstiraji - na stroji bez Dockeru nebo baterie se karty
proste vykresli v degradovanem tvaru, coz je presne to, co ma kontrakt
dovolit. Predstira se jen vyjimka, aby slo overit, ze ji Monitor spolkne.
"""

import itertools
import unittest
from types import SimpleNamespace
from unittest import mock

from sysmon_app.collectors.processes import get_top_processes
from sysmon_app.config import TOP_PROCESSES_N, Settings
from sysmon_app.monitor import Monitor

# 16 klicek, ktere musi byt ve snapshotu vzdy. cpu_temp je navic a jen
# kdyz ho stroj umi precist - jeho nepritomnost je platny stav.
ALWAYS_PRESENT = (
    "host", "user", "cpu", "cpu_cores", "mem", "swap", "loadavg", "disk",
    "processes", "system", "gpu", "battery", "battery_history", "net",
    "services", "containers",
)

# Hodnota je (atribut na Monitoru, nebo None pro funkci v modulu, jmeno).
COLLECTOR_CALLS = {
    "net": ("net", "read"),
    "disk": ("disk", "read"),
    "battery": ("battery", "read"),
    "battery_history": ("battery", "history"),
    "containers": ("docker", "snapshot"),
    "loadavg": (None, "get_loadavg"),
    "processes": (None, "get_top_processes"),
    "system": (None, "get_system_info"),
    "gpu": (None, "get_gpu"),
    "services": (None, "get_services"),
}
COLLECTORS = tuple(COLLECTOR_CALLS)

# Kolektory, ktere protaci prime(). cpu_percent je tu zamerne chybi: je to
# prime psutil, ne kolektor, a podstrcit ho by rozbilo i snapshot().
PRIMED = ("net", "disk", "processes")


def failure(key, monitor):
    """Kontextovy manazer, ktery donuti kolektor pro dany klic vyhodit."""
    attr, name = COLLECTOR_CALLS[key]
    if attr is None:
        return mock.patch(f"sysmon_app.monitor.{name}", side_effect=RuntimeError(key))
    return mock.patch.object(getattr(monitor, attr), name, side_effect=RuntimeError(key))


class SnapshotContractTest(unittest.TestCase):
    def test_has_all_always_present_keys(self):
        snapshot = Monitor(Settings()).snapshot()
        self.assertEqual(set(ALWAYS_PRESENT) - set(snapshot), set())
        # A presne 16: cpu_temp je jediny klic, ktery smi byt navic.
        self.assertEqual(set(snapshot) - {"cpu_temp"}, set(ALWAYS_PRESENT))

    def test_cpu_temp_is_added_only_when_available(self):
        monitor = Monitor(Settings())
        with mock.patch("sysmon_app.monitor.get_cpu_temp", return_value=42.0):
            self.assertEqual(monitor.snapshot()["cpu_temp"], 42.0)
        with mock.patch("sysmon_app.monitor.get_cpu_temp", return_value=None):
            self.assertNotIn("cpu_temp", monitor.snapshot())

    def test_watch_ports_from_settings_reach_services(self):
        settings = Settings(watch_ports={12345: "Testovaci"})
        services = Monitor(settings).snapshot()["services"]
        self.assertEqual([s["port"] for s in services], [12345])

    def test_ports_outside_watch_list_are_invisible(self):
        """Port, ktery neni ve watch_ports, se na karte sluzeb neobjevi."""
        settings = Settings(watch_ports={})
        self.assertEqual(Monitor(settings).snapshot()["services"], [])

    def test_prime_establishes_baseline_for_rate_collectors(self):
        """Bez protoceni by prvni cteni bylo vzdy nula - proto se prime() vola.

        `_prev_t` je privatni, ale je to presne ten stav, ktery baseline
        znamena. Pres verejne rozhrani se protoceni poznat neda: prvni i druhe
        cteni vraci float, jen to prvni je vzdy nulove, a nula je na klidnem
        stroji i spravna odpoved.

        Citace disku se podstrkuji: `disk.py` posune baseline jen v uspesne
        vetvi, takze na stroji bez citelnych I/O statistik by tenhle test
        spadel - a to je stav, se kterym `disk.py` pocita.
        """
        monitor = Monitor(Settings())
        self.assertIsNone(monitor.net._prev_t)
        self.assertIsNone(monitor.disk._prev_t)
        io = SimpleNamespace(read_bytes=100, write_bytes=200)
        with mock.patch("sysmon_app.collectors.disk.psutil.disk_io_counters",
                        return_value=io), \
             mock.patch("sysmon_app.collectors.disk.time.monotonic",
                        return_value=100.0):
            monitor.prime()
        self.assertIsNotNone(monitor.net._prev_t)
        self.assertIsNotNone(monitor.disk._prev_t)

    def test_prime_cycles_cpu_and_top_processes(self):
        """AC mluvi i o CPU a komentar u prime() i o procesech - oboji musi nastat.

        Vyjimkovy mechanismus `PRIMED` na to nestaci: `psutil.cpu_percent`
        podstrcit nejde, protoze v `snapshot()` obalene neni a podstrceni by
        rozbilo i jeho.
        """
        monitor = Monitor(Settings())
        with mock.patch("sysmon_app.monitor.psutil.cpu_percent") as cpu, \
             mock.patch("sysmon_app.monitor.get_top_processes") as procs:
            monitor.prime()
        cpu.assert_called_once_with(interval=None)
        procs.assert_called_once_with(TOP_PROCESSES_N)

    def test_prime_makes_the_first_snapshot_nonzero(self):
        """Tentyz nalez z druhe strany: prvni /stats nesmi byt sama nula."""
        monitor = Monitor(Settings())
        sent = itertools.count(1000, 1000)
        recv = itertools.count(2000, 2000)
        clock = itertools.count(100.0, 1.0)

        def counters():
            return SimpleNamespace(bytes_sent=next(sent), bytes_recv=next(recv))

        with mock.patch("sysmon_app.collectors.net.psutil.net_io_counters",
                        side_effect=counters), \
             mock.patch("sysmon_app.collectors.net.time.monotonic",
                        side_effect=lambda: next(clock)):
            monitor.prime()
            net = monitor.snapshot()["net"]

        self.assertGreater(net["up"], 0)
        self.assertGreater(net["down"], 0)

    def test_snapshot_has_no_action_results(self):
        """Produkt jen zobrazuje - v kontraktu nesmi byt stopy po akcich."""
        monitor = Monitor(Settings())
        for method in ("restart_container", "kill_process"):
            self.assertFalse(hasattr(monitor, method))

    def test_prime_survives_a_failing_collector(self):
        """Vyjimka pri startu nesmi shodit demona - a to u kterehokoli z protocenych."""
        for key in PRIMED:
            with self.subTest(collector=key):
                monitor = Monitor(Settings())
                with failure(key, monitor):
                    monitor.prime()
                self.assertEqual(set(ALWAYS_PRESENT) - set(monitor.snapshot()), set())

    def test_any_collector_failure_keeps_the_contract(self):
        """Vypadek kterehokoli kolektoru snapshot neshodi ani neubira klic."""
        for key in COLLECTORS:
            with self.subTest(collector=key):
                monitor = Monitor(Settings())
                with failure(key, monitor):
                    snapshot = monitor.snapshot()
                self.assertEqual(set(ALWAYS_PRESENT) - set(snapshot), set())

    def test_net_failure_has_the_same_keys_as_success(self):
        """Net je jediny kolektor bez vlastni degradacni cesty.

        U ostatnich staci jejich vlastni tvar (available: False), ktery karta
        umi vykreslit i na stroji bez te veci. U netu by ale chybejici klice
        rozbily render, takze je sklada Monitor a musi sedet s uspesnou vetvi.
        """
        monitor = Monitor(Settings())
        with failure("net", monitor):
            failed = monitor.snapshot()["net"]
        self.assertEqual(failed, {"up": 0.0, "down": 0.0, "total_up": 0, "total_recv": 0})
        self.assertEqual(set(failed), set(Monitor(Settings()).snapshot()["net"]))

    def test_fallback_has_the_same_type_as_the_success_branch(self):
        """Zamena tvary ve FALLBACKS musi byt videt.

        Klic a jeho nahradni tvar k sobe nic mechanicky nevaze, takze se
        v tabulce daji prehodit dve hodnoty, ktere obe nejak vypadaji. Testy
        na pritomnost klicu to nepoznaji - a frontend na to doplati: `{}`
        v `loadavg` je truthy a spadne na `["1m"].toFixed`, dict v `processes`
        projde pres `Array.isArray` a karta tise zamrzne.

        Oracle je nezavisly: srovnava se tvar nahradni hodnoty s tvarem, ktery
        uspesne vratil kolektor. `loadavg` je vyjmuty - jeho kolektor vraci
        `None` i sam, takze typ uspesne vetve o nem nic nerika.
        """
        for key in COLLECTORS:
            if key == "loadavg":
                continue
            with self.subTest(collector=key):
                monitor = Monitor(Settings())
                good = monitor.snapshot()[key]
                with failure(key, monitor):
                    bad = monitor.snapshot()[key]
                self.assertIs(type(bad), type(good))

    def test_loadavg_fallback_is_none(self):
        """`loadavg` ma jako jediny fallback `None`; `{}` rozbije cely render."""
        monitor = Monitor(Settings())
        with failure("loadavg", monitor):
            self.assertIsNone(monitor.snapshot()["loadavg"])

    def test_failure_of_one_collector_leaves_the_rest_working(self):
        """Zbytek dashboardu se dal aktualizuje - nezamrzne cely."""
        monitor = Monitor(Settings())
        with failure("net", monitor):
            snapshot = monitor.snapshot()
        self.assertEqual(snapshot["net"]["up"], 0.0)
        self.assertIsInstance(snapshot["cpu"], float)
        self.assertGreater(len(snapshot["cpu_cores"]), 0)
        self.assertIsInstance(snapshot["mem"]["percent"], float)
        self.assertIsInstance(snapshot["disk"]["read_rate"], float)

    def test_fallback_shape_is_not_shared_between_snapshots(self):
        """Nahradni tvar se vraci jako kopie - jinak by si ho odberatele prepsali."""
        monitor = Monitor(Settings())
        with failure("containers", monitor):
            first = monitor.snapshot()["containers"]
            second = monitor.snapshot()["containers"]
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        # A do hloubky: vnoreny `groups` taky nesmi byt sdileny.
        self.assertIsNot(first["groups"], second["groups"])

    def test_top_processes_have_the_expected_shape(self):
        """Kontraktni test kontroluje jen pritomnost klicu, tohle ma vlastni."""
        processes = get_top_processes(TOP_PROCESSES_N)
        self.assertGreater(len(processes), 0)
        self.assertLessEqual(len(processes), TOP_PROCESSES_N)
        for proc in processes:
            self.assertEqual(set(proc), {"pid", "name", "cpu", "mem"})

    def test_processes_reach_the_snapshot_untruncated(self):
        """Monitor preda seznam procesu dal - ne fallback a ne zkraceny.

        Kolektor se podstrkuje, aby test nezavisel na tom, co zrovna bezi:
        `psutil.process_iter()` je v `processes.py` mimo vnitrni `try`, takze
        na stroji s necitelnym /proc by seznam prisel prazdny a test by tvrdil
        neco o hostiteli, ne o `Monitoru`.

        Chyti i zkraceny seznam: `partial(get_top_processes, 3)` se podstrcenym
        kolektorem projevi jen v argumentu, ktery se tu kontroluje.
        """
        fake = [{"pid": 1, "name": "x", "cpu": 0.0, "mem": 0}]
        monitor = Monitor(Settings())
        with mock.patch("sysmon_app.monitor.get_top_processes",
                        return_value=fake) as procs:
            self.assertEqual(monitor.snapshot()["processes"], fake)
        procs.assert_called_once_with(TOP_PROCESSES_N)


if __name__ == "__main__":
    unittest.main()
