"""Monitor - sklada snapshot ze vsech kolektoru.

Tohle je jedine misto, ktere vi, jak vypada vystup /stats i SSE proudu.
Kolektory o sobe navzajem nevi; Monitor je drzi a orchestrauje.

Zadny kolektor nesmi shodit snapshot. Kdyby vyjimka prosla, feed._loop ji
spolkne (obaluje publish_once do except Exception), _seq prestane rust
a okno i telefon ukazuji zamrzla cisla - tise a bez chyby kdekoli. Proto
je kazde volani kolektoru obalene pres _safe().
"""

import copy
import socket
from functools import partial

import psutil

from sysmon_app.collectors.battery import BatteryCollector
from sysmon_app.collectors.disk import DiskCollector
from sysmon_app.collectors.docker import DockerCollector
from sysmon_app.collectors.gpu import get_gpu
from sysmon_app.collectors.net import NetCollector
from sysmon_app.collectors.ports import get_services
from sysmon_app.collectors.processes import get_top_processes
from sysmon_app.collectors.system import (
    get_cpu_temp, get_loadavg, get_system_info, get_user,
)
from sysmon_app.config import TOP_PROCESSES_N, Settings

# Nahradni tvary pro pripad, ze kolektor vyhodi vyjimku. Tam, kde kolektor ma
# vlastni degradacni tvar (disk, gpu, battery, docker), pouziva se ten - je to
# presne to, co karta vykresli i na stroji bez te veci. `net` zadny nema,
# takze se doplnuje rucne a musi mit stejne klice jako uspesna vetev: render
# pak nemusi rozlisovat, co se pokazilo.
FALLBACKS = {
    "net": {"up": 0.0, "down": 0.0, "total_up": 0, "total_recv": 0},
    "disk": {"available": False},
    "gpu": {"available": False},
    "battery": {"available": False, "error": "Údaje o baterii nejsou dostupné"},
    "battery_history": [],
    "processes": [],
    "services": [],
    "system": {},
    "loadavg": None,
    "containers": {
        "available": False,
        "error": "Docker data nejsou k dispozici",
        "groups": {},
    },
}


def _safe(call, fallback):
    """Zavola kolektor a pri vyjimce vrati kopii nahradniho tvaru.

    Kopie je nutna: tvary jsou modulove konstanty a snapshot se predava dal
    (do JSON pro /stats i do SSE proudu), takze by si je volajici prepsali.

    Volani s argumenty se predava pres `partial`, ne pres `lambda`: jmeno
    funkce se vyhodnoti uz tady, tedy mimo tenhle obal. S lambdou by preklep
    ve jmenu spadl dovnitr, `except` by ho spolkl a karta by zustala prazdna
    navzdy - tise a bez chyby kdekoli, presne to, cemu se obal vyhyba.
    """
    try:
        return call()
    except Exception:
        return copy.deepcopy(fallback)


class Monitor:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.battery = BatteryCollector()
        self.docker = DockerCollector()
        self.net = NetCollector()
        self.disk = DiskCollector()

    def start_background(self):
        """Spusti vlakna, ktera vzorkuji pomale externi veci."""
        self.battery.start_worker()
        self.docker.start_worker()

    def prime(self):
        """Nastavi baseline pro rate-based metriky.

        get_net(), get_disk() a cpu_percent(interval=None) pocitaji z rozdilu
        proti predchozimu cteni - prvni volani vzdy vraci nulu. Zavola se proto
        jeste pred spustenim serveru, aby prvni /stats nebyl samy 0.

        Kolektory jsou i tady obalene: vyjimka pri startu by jinak shodila
        cely demon, i kdyby slo jen o jednu kartu.
        """
        _safe(partial(psutil.cpu_percent, interval=None), None)
        _safe(self.net.read, FALLBACKS["net"])
        _safe(self.disk.read, FALLBACKS["disk"])
        _safe(partial(get_top_processes, TOP_PROCESSES_N), FALLBACKS["processes"])

    def snapshot(self):
        """Kompletni stav systemu - pro GET /stats i pro SSE."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        stats = {
            "host": _safe(socket.gethostname, ""),
            "user": _safe(get_user, ""),
            "cpu": psutil.cpu_percent(interval=None),
            "cpu_cores": psutil.cpu_percent(interval=None, percpu=True),
            "mem": {"percent": mem.percent, "used": mem.used, "total": mem.total},
            "swap": {"percent": swap.percent, "used": swap.used, "total": swap.total},
            "loadavg": _safe(get_loadavg, FALLBACKS["loadavg"]),
            "disk": _safe(self.disk.read, FALLBACKS["disk"]),
            "processes": _safe(
                partial(get_top_processes, TOP_PROCESSES_N), FALLBACKS["processes"]
            ),
            "system": _safe(get_system_info, FALLBACKS["system"]),
            "gpu": _safe(get_gpu, FALLBACKS["gpu"]),
            "battery": _safe(self.battery.read, FALLBACKS["battery"]),
            "battery_history": _safe(self.battery.history, FALLBACKS["battery_history"]),
            "net": _safe(self.net.read, FALLBACKS["net"]),
            "services": _safe(
                partial(
                    get_services,
                    self.settings.watch_ports,
                    self.settings.ignored_ports,
                ),
                FALLBACKS["services"],
            ),
            "containers": _safe(self.docker.snapshot, FALLBACKS["containers"]),
        }
        cpu_temp = _safe(get_cpu_temp, None)
        if cpu_temp is not None:
            stats["cpu_temp"] = cpu_temp
        return stats
