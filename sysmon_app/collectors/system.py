"""System info: uptime, kernel, NVMe teplota, CPU teplota, load average, uzivatel."""

import getpass
import platform
import time

import psutil

# Klic v psutil.sensors_temperatures() se lisi podle hardwaru - bereme prvni shodu.
NVME_TEMP_KEYS = ("nvme", "nvme-pci", "composite")
CPU_TEMP_KEYS = ("k10temp", "coretemp", "zenpower", "acpitz")


def get_system_info():
    boot = psutil.boot_time()
    info = {
        "uptime_seconds": int(time.time() - boot),
        "kernel": platform.release(),
    }
    try:
        temps = psutil.sensors_temperatures()
        for key in NVME_TEMP_KEYS:
            if key in temps and temps[key]:
                info["nvme_temp"] = temps[key][0].current
                break
    except Exception:
        pass
    return info


def get_cpu_temp():
    """Teplota CPU ve stupnich C, nebo None kdyz ji nelze precist."""
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return None
    for key in CPU_TEMP_KEYS:
        if key in temps and temps[key]:
            return temps[key][0].current
    return None


def get_loadavg():
    try:
        l1, l5, l15 = psutil.getloadavg()
        return {"1m": l1, "5m": l5, "15m": l15}
    except Exception:
        return None


def get_user():
    """Prihlasovaci jmeno - hlavicka pak pise `uzivatel@host` jako fastfetch.

    getpass cte hlavne prostredi; kdyz server startuje bez nej (treba ze
    systemd), spadne zpatky na uid. Kdyz selze i to, vratime prazdny retezec:
    hlavicka ukaze jen hostname a /stats kvuli tomu nesmi spadnout.
    """
    try:
        return getpass.getuser()
    except Exception:
        return ""
