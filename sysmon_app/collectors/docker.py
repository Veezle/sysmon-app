"""Docker: seznam bezicich kontejneru + statistiky, obnovovane na pozadi.

`s docker stats` je pomaly (klidne i sekundy), proto nikdy nebezi v ceste
pozadavku - delnik ho obnovuje kazdych DOCKER_POLL_SEC a pozadavek si jen
prevezme posledni snapshot. Slib "zadne pomale externi volani v ceste
pozadavku" tim zustava dodrzen i po prechodu na SSE.

Kontejnery se seskupuji podle Compose projektu (`com.docker.compose.project`),
aby bylo videt, co k sobe patri.
"""

import json
import re
import shutil
import subprocess
import threading
import time

from sysmon_app.config import DOCKER_POLL_SEC

DOCKER = "docker"
CLI_MISSING = "Docker CLI nenalezen"

COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
OTHER_PROJECT = "Ostatní"

# Zacatek klice labelu. Docker povoluje ve klíči znaky [a-zA-Z0-9._/-].
_LABEL_START_RE = re.compile(r"(?:^|,)([A-Za-z0-9][A-Za-z0-9._/-]*)=")


def parse_labels(raw):
    """Rozparsuje `Labels` z `docker ps` na dict. Prazdny vstup vraci {}.

    Hodnota labelu muze obsahovat carku (typicky
    `com.docker.compose.depends_on=db:service_healthy:false,assets:service_completed_successfully:false`),
    takze naivni `split(",")` by roztrhl jak hodnotu, tak klíč za ni. Misto
    toho se najdou zacatky vsech klíčů a hodnota saha az k tomu nasledujicimu.
    """
    if not raw:
        return {}
    starts = list(_LABEL_START_RE.finditer(raw))
    labels = {}
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(raw)
        labels[match.group(1)] = raw[match.end():end]
    return labels


def group_by_project(containers):
    """Seskupi kontejnery podle Compose projektu: {projekt: [kontejner, ...]}.

    Kontejner bez labelu (nebo s prazdnym) patri do OTHER_PROJECT. Skupiny jsou
    serazene abecedne a OTHER_PROJECT je vzdy posledni, poradi uvnitr skupiny
    je podle jmena. Kontejnery se nekopiruji ani needituji - predavaji se dal
    tak, jak prisly, aby se cestou neztratilo zadne pole.
    """
    groups = {}
    for container in containers:
        labels = parse_labels(container.get("Labels"))
        project = labels.get(COMPOSE_PROJECT_LABEL) or OTHER_PROJECT
        groups.setdefault(project, []).append(container)
    for items in groups.values():
        items.sort(key=lambda c: c.get("Names") or c.get("ID") or "")
    ordered = sorted(groups, key=lambda p: (p == OTHER_PROJECT, p.casefold()))
    return {project: groups[project] for project in ordered}


class DockerCollector:
    def __init__(self, interval=DOCKER_POLL_SEC):
        self._interval = interval
        self._data = {"available": False, "error": "Docker data se načítají…", "groups": {}}
        self._lock = threading.Lock()

    def refresh(self):
        """Spusti docker ps + stats a vrati cerstvy dict. Nikdy nevyhazuje."""
        if not shutil.which(DOCKER):
            return {"available": False, "error": CLI_MISSING, "groups": {}}

        try:
            result = subprocess.run(
                [DOCKER, "ps", "--format", "{{json .}}"],
                capture_output=True, text=True, timeout=3, check=True,
            )
            containers = [
                json.loads(line)
                for line in result.stdout.splitlines()
                if line.strip()
            ]
        except subprocess.TimeoutExpired:
            return {"available": False, "error": "Docker timeout", "groups": {}}
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or "Docker není dostupný").strip()
            return {"available": False, "error": message, "groups": {}}
        except (OSError, json.JSONDecodeError) as exc:
            return {"available": False, "error": f"Chyba při čtení Dockeru: {exc}", "groups": {}}

        try:
            stats_result = subprocess.run(
                [DOCKER, "stats", "--no-stream", "--format", "{{json .}}"],
                capture_output=True, text=True, timeout=3, check=True,
            )
            stats = [
                json.loads(line)
                for line in stats_result.stdout.splitlines()
                if line.strip()
            ]
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            stats = []

        stats_by_name = {}
        stats_by_id = {}
        for item in stats:
            key = item.get("Container", "")
            if key:
                stats_by_name[key] = item
                stats_by_id[key[:12]] = item

        for container in containers:
            name = container.get("Names", "")
            container_id = container.get("ID", "")
            stat = (
                stats_by_name.get(name)
                or stats_by_name.get(container_id)
                or stats_by_id.get(container_id[:12])
            )
            container["cpu"] = stat.get("CPUPerc", "—") if stat else "—"
            container["memory"] = stat.get("MemUsage", "—") if stat else "—"
            container["memory_percent"] = stat.get("MemPerc", "—") if stat else "—"

        return {"available": True, "error": None, "groups": group_by_project(containers)}

    def snapshot(self):
        with self._lock:
            return dict(self._data)

    def start_worker(self):
        threading.Thread(
            target=self._loop, name="sysmon-docker-monitor", daemon=True,
        ).start()

    def _loop(self):
        while True:
            try:
                data = self.refresh()
            except Exception as exc:
                data = {"available": False, "error": f"Chyba Docker monitoru: {exc}", "groups": {}}
            with self._lock:
                self._data = data
            time.sleep(self._interval)
