"""Matematika a klasifikace mericiho nastroje (`tools/measure_memory.py`).

Testy nedrzi /proc: slope a mediany se pocitaji z rucne zadanych bodu.
Klasifikace se testuje na cmdline retezcich. `--help` se spousti jako
subprocess s `-I`, takze test selze, kdyby nastroj importoval nestandardni
knihovnu.
"""

import subprocess
import sys
import unittest
from pathlib import Path

from tools import measure_memory

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "measure_memory.py"
MB = 1024


class SlopeTest(unittest.TestCase):
    def test_constant_series_is_zero(self):
        points = [(t, 100 * MB) for t in range(0, 3601, 600)]
        self.assertAlmostEqual(
            measure_memory.slope_mb_per_hour(points), 0.0, places=6
        )

    def test_sixty_mb_per_hour(self):
        # 100 MB -> 160 MB za hodinu je presne 60 MB/h.
        points = [(0, 100 * MB), (1800, 130 * MB), (3600, 160 * MB)]
        self.assertAlmostEqual(
            measure_memory.slope_mb_per_hour(points), 60.0, places=6
        )

    def test_negative_slope(self):
        points = [(0, 160 * MB), (3600, 100 * MB)]
        self.assertAlmostEqual(
            measure_memory.slope_mb_per_hour(points), -60.0, places=6
        )

    def test_fewer_than_two_points_raises(self):
        with self.assertRaises(ValueError):
            measure_memory.slope_mb_per_hour([(0, MB)])

    def test_zero_time_span_raises(self):
        with self.assertRaises(ValueError):
            measure_memory.slope_mb_per_hour([(0, MB), (0, 2 * MB)])


class MedianDeltaTest(unittest.TestCase):
    def test_medians_of_first_and_last_ten_minutes(self):
        # Kazdych 100 s jeden vzorek 0..20 MB. Prvni okno 0-600 s ma
        # hodnoty 0..6 MB (median 3), posledni 1400-2000 s ma 14..20 MB
        # (median 17). Rozdil je 14 MB.
        points = [(t, (t // 100) * MB) for t in range(0, 2001, 100)]
        first, last, delta = measure_memory.median_delta(points)
        self.assertAlmostEqual(first, 3.0, places=6)
        self.assertAlmostEqual(last, 17.0, places=6)
        self.assertAlmostEqual(delta, 14.0, places=6)

    def test_even_count_uses_average_of_middle_values(self):
        # Ctyri body po 100 s: prvni okno 0-600 s vezme vsechny ctyri
        # (0, 1, 2, 3 MB), median je 1.5; posledni okno je stejne.
        points = [(t, (t // 100) * MB) for t in range(0, 400, 100)]
        first, last, delta = measure_memory.median_delta(points)
        self.assertAlmostEqual(first, 1.5, places=6)
        self.assertAlmostEqual(last, 1.5, places=6)
        self.assertAlmostEqual(delta, 0.0, places=6)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            measure_memory.median_delta([])


class ClassificationTest(unittest.TestCase):
    def test_webkit_web_process(self):
        self.assertEqual(
            measure_memory.classify_cmdline(
                ["/usr/lib/webkit2gtk-4.1/WebKitWebProcess", "42"]
            ),
            "web",
        )

    def test_webkit_network_process(self):
        self.assertEqual(
            measure_memory.classify_cmdline(
                ["/usr/lib/webkit2gtk-4.1/WebKitNetworkProcess", "43"]
            ),
            "network",
        )

    def test_pyinstaller_daemon(self):
        self.assertEqual(
            measure_memory.classify_cmdline(
                [
                    "/usr/lib/sysmon-app/daemon/sysmon-app-daemon",
                    "--port",
                    "8430",
                ]
            ),
            "daemon",
        )

    def test_python_module_daemon(self):
        self.assertEqual(
            measure_memory.classify_cmdline(
                ["python3", "-m", "sysmon_app", "--port", "8430"]
            ),
            "daemon",
        )

    def test_python_module_daemon_with_versioned_interpreter(self):
        self.assertEqual(
            measure_memory.classify_cmdline(
                ["/usr/bin/python3.13", "-m", "sysmon_app"]
            ),
            "daemon",
        )

    def test_similar_module_is_not_daemon(self):
        self.assertEqual(
            measure_memory.classify_cmdline(
                ["python3", "-m", "sysmon_app_other"]
            ),
            "other",
        )

    def test_unknown_process_is_other(self):
        self.assertEqual(
            measure_memory.classify_cmdline(["/usr/bin/bash"]), "other"
        )
        self.assertEqual(measure_memory.classify_cmdline([]), "other")


class HelpTest(unittest.TestCase):
    def test_help_runs_without_site_packages(self):
        result = subprocess.run(
            [sys.executable, "-I", str(TOOL), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--pid", result.stdout)
        self.assertIn("--duration", result.stdout)
        self.assertIn("--csv", result.stdout)
        self.assertIn("--slope-limit", result.stdout)
        self.assertIn("--delta-limit", result.stdout)


class DefaultsTest(unittest.TestCase):
    def test_default_warmup_is_twenty_minutes(self):
        # Zmena protokolu z 5 na 20 minut musi byt videt i v parseru;
        # jinak by se mohl tise vratit stary default.
        args = measure_memory.build_parser().parse_args([])
        self.assertEqual(args.warmup, 1200.0)


if __name__ == "__main__":
    unittest.main()
