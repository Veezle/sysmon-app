"""Top procesy podle aktualniho CPU."""

import psutil

from sysmon_app.config import TOP_PROCESSES_N


def get_top_processes(n=TOP_PROCESSES_N):
    procs = []
    for p in psutil.process_iter():
        try:
            with p.oneshot():
                procs.append({
                    "pid": p.pid,
                    "name": p.name() or "?",
                    "cpu": p.cpu_percent(interval=None),
                    "mem": p.memory_info().rss,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return procs[:n]
