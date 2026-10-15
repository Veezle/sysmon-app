"""Naslouchajici porty - cte se primo z /proc/net/tcp{,6}, bez shellu.

Proc ne `ss`/`netstat`: zbytecny podproces, a tyhle soubory jsou autoritativni.
Stav 0A = LISTEN. Ktere porty sledovat a ktere zahazovat vi konfigurace -
seznam sledovanych sluzeb je stroj-specificky.
"""

TCP_FILES = ("/proc/net/tcp", "/proc/net/tcp6")

LISTEN_STATE = "0A"


def listening_ports(ignored_ports):
    """Mnozina cisel portu, ktere nekdo posloucha (bez ignored_ports)."""
    ports = set()
    for path in TCP_FILES:
        try:
            with open(path) as f:
                next(f)
                for line in f:
                    parts = line.split()
                    if len(parts) < 4 or parts[3] != LISTEN_STATE:
                        continue
                    try:
                        port_hex = parts[1].rsplit(":", 1)[1]
                        port = int(port_hex, 16)
                    except (IndexError, ValueError):
                        continue
                    if port in ignored_ports:
                        continue
                    ports.add(port)
        except (OSError, StopIteration):
            continue
    return ports


def get_services(watch_ports, ignored_ports):
    """Sledovane porty - nejdriv bezi, pak offline, vzestupne.

    Port, ktery neni ve watch_ports, je neviditelny; watch_ports je jediny
    zdroj pravdy o tom, co karta sluzeb ukazuje.
    """
    listening = listening_ports(ignored_ports)
    items = [
        {"port": port, "label": label, "on": port in listening}
        for port, label in watch_ports.items()
    ]
    items.sort(key=lambda x: (not x["on"], x["port"]))
    return items
