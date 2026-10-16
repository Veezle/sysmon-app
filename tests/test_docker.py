"""Docker kolektor: cteni `docker ps`/`stats`, chovani bez CLI a pri vypadku.

Seskupovani kontejneru se tu neresi - to je v test_docker_grouping. Tady jde
o tridu DockerCollector, ktera byla dosud bez jedineho testu, prestoze ji
Monitor pousti na pozadi.

Docker se nevola: podstrkuje se `shutil.which` a `subprocess.run`, stejne
jako test_rates podstrkuje psutil.
"""

import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from sysmon_app.collectors import docker


def ps_line(name, container_id, labels=""):
    """Jeden radek z `docker ps --format '{{json .}}'`."""
    return json.dumps({"Names": name, "ID": container_id, "Labels": labels})


def stats_line(container, cpu="1.5%"):
    """Jeden radek z `docker stats --no-stream --format '{{json .}}'`."""
    return json.dumps({
        "Container": container, "CPUPerc": cpu,
        "MemUsage": "10MiB / 1GiB", "MemPerc": "0.98%",
    })


class RefreshTest(unittest.TestCase):
    def collector(self, ps_stdout="", stats_stdout="", stats_error=None, run_error=None):
        """Kolektor s podstrcenym CLI i `subprocess.run`."""
        which = mock.patch.object(docker.shutil, "which", return_value="/usr/bin/docker")
        which.start()
        self.addCleanup(which.stop)

        def run(cmd, **kwargs):
            if cmd[:2] == [docker.DOCKER, "stats"]:
                if stats_error is not None:
                    raise stats_error
                return SimpleNamespace(returncode=0, stdout=stats_stdout, stderr="")
            if run_error is not None:
                raise run_error
            return SimpleNamespace(returncode=0, stdout=ps_stdout, stderr="")

        runner = mock.patch.object(docker.subprocess, "run", side_effect=run)
        runner.start()
        self.addCleanup(runner.stop)
        return docker.DockerCollector()

    def test_missing_cli_is_reported_not_raised(self):
        """Bez Docker CLI se karta omluvi - a nikdy to nezvedne vyjimku."""
        which = mock.patch.object(docker.shutil, "which", return_value=None)
        which.start()
        self.addCleanup(which.stop)
        self.assertEqual(
            docker.DockerCollector().refresh(),
            {"available": False, "error": docker.CLI_MISSING, "groups": {}},
        )

    def test_timeout_is_reported(self):
        collector = self.collector(
            run_error=subprocess.TimeoutExpired(cmd="docker ps", timeout=3),
        )
        self.assertEqual(
            collector.refresh(),
            {"available": False, "error": "Docker timeout", "groups": {}},
        )

    def test_broken_json_from_ps_is_reported(self):
        """Rozbity JSON nesmi vyletet ven; chyta se zvlast od OSError."""
        collector = self.collector(ps_stdout="{tohle neni json")
        result = collector.refresh()
        self.assertFalse(result["available"])
        self.assertIn("Chyba při čtení Dockeru", result["error"])

    def test_stats_failure_keeps_the_container_without_numbers(self):
        """Kdyz selze jen `docker stats`, seznam kontejneru zustava - jen bez cisel."""
        collector = self.collector(
            ps_stdout=ps_line("app-1", "abcdef1234567890") + "\n",
            stats_error=OSError("stats zmizely"),
        )
        result = collector.refresh()
        self.assertTrue(result["available"])
        container = result["groups"]["Ostatní"][0]
        self.assertEqual(container["cpu"], "—")
        self.assertEqual(container["memory"], "—")

    def test_stats_are_paired_by_container_name(self):
        collector = self.collector(
            ps_stdout=ps_line("app-1", "abcdef1234567890") + "\n",
            stats_stdout=stats_line("app-1", cpu="7.5%") + "\n",
        )
        container = collector.refresh()["groups"]["Ostatní"][0]
        self.assertEqual(container["cpu"], "7.5%")

    def test_stats_are_paired_by_short_id_when_the_name_differs(self):
        """Docker umi statistiky klicovat i zkracenym ID - fallback to resi.

        Statistiky maji v `Container` zkracene ID, kdezto `docker ps` dava plne.
        Kdyby se parovalo jen podle jmena a plneho ID, zustaly by pomlcky.
        """
        collector = self.collector(
            ps_stdout=ps_line("app-1", "abcdef1234567890") + "\n",
            stats_stdout=stats_line("abcdef123456", cpu="9.9%") + "\n",
        )
        container = collector.refresh()["groups"]["Ostatní"][0]
        self.assertEqual(container["cpu"], "9.9%")

    def test_every_branch_keeps_the_groups_key(self):
        """Klic `groups` musi byt i v chybovych vetvich - je soucasti kontraktu."""
        no_cli = mock.patch.object(docker.shutil, "which", return_value=None)
        no_cli.start()
        self.addCleanup(no_cli.stop)
        self.assertIn("groups", docker.DockerCollector().refresh())

        collector = self.collector(run_error=subprocess.TimeoutExpired(cmd="docker ps", timeout=3))
        self.assertIn("groups", collector.refresh())

    def test_loop_survives_a_raising_refresh(self):
        """Vyjimka z refresh() nesmi zabit obnovovaci vlakno.

        Kdyby vlakno umrelo, karta by tise zamrzla na poslednim snapshotu -
        presne ten rezim, pred kterym varuje CLAUDE.md u net.py.
        """
        collector = self.collector()
        refresh = mock.patch.object(collector, "refresh", side_effect=RuntimeError("vypadek"))
        refresh.start()
        self.addCleanup(refresh.stop)
        sleep = mock.patch.object(docker.time, "sleep", side_effect=[None, StopIteration])
        sleep.start()
        self.addCleanup(sleep.stop)

        with self.assertRaises(StopIteration):
            collector._loop()

        # Sest vykonanych vzorku neni potreba - staci, ze smycka prvni vyjimku
        # prezila a ulozila chybovy stav misto aby spadla.
        self.assertFalse(collector._data["available"])


if __name__ == "__main__":
    unittest.main()
