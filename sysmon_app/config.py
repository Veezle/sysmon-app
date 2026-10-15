"""Konfigurace sysmon-app: vychozi hodnoty a volitelny config.toml od uzivatele.

Stroj-specificke veci (ktere porty sledovat, na cem poslouchat) nepatri do
kodu - na cizim stroji by byly nesmysl. Vsechno ostatni jsou konstanty.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8430          # sysmon ma 8420; oba produkty zijou vedle sebe

TICK_SEC = 1.5               # perioda sberneho cyklu = perioda SSE
SSE_KEEPALIVE_SEC = 20.0     # po teto dobe ticha posleme komentar, at spojeni nezivori

DOCKER_POLL_SEC = 5
BATTERY_HISTORY_SEC = 120
BATTERY_HISTORY_MAX = 720    # 24 h pri 2min intervalu
TOP_PROCESSES_N = 5

DEFAULT_WATCH_PORTS = {
    22: "SSH",
    3306: "MySQL",
    5173: "Vite",
    8080: "Backend",
    8081: "Metro",
}
DEFAULT_IGNORED_PORTS = {53, 111, 631, 5353, 1716, 54321}

CONFIG_DIR_NAME = "sysmon-app"
CONFIG_FILE_NAME = "config.toml"

_KNOWN_KEYS = {"host", "port", "watch_ports", "ignored_ports"}


def config_path():
    """Cesta ke konfiguraci. Respektuje XDG_CONFIG_HOME, relativni ignoruje.

    Relativni XDG_CONFIG_HOME by znamenal, ze cesta k tokenu zavisi na
    aktualnim adresari procesu - to XDG basedir spec zakazuje.
    """
    default = os.path.join(os.path.expanduser("~"), ".config")
    base = os.environ.get("XDG_CONFIG_HOME") or default
    if not os.path.isabs(base):
        base = default
    return Path(base) / CONFIG_DIR_NAME / CONFIG_FILE_NAME


@dataclass
class Settings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    watch_ports: dict = field(default_factory=lambda: dict(DEFAULT_WATCH_PORTS))
    ignored_ports: set = field(default_factory=lambda: set(DEFAULT_IGNORED_PORTS))


def _port_number(value, key):
    """Prevede klic/hodnotu na cislo portu, nebo rekne, co je spatne.

    bool se odmita zamerne: v Pythonu je to podtyp int, takze true by se tise
    prevedlo na port 1 - stejna past, jakou v sysmonu resi validate_pid.
    """
    if isinstance(value, bool):
        raise ValueError(f"{key}: '{value}' není číslo portu")
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key}: '{value}' není číslo portu") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"{key}: port {port} je mimo rozsah 1-65535")
    return port


def load_settings(path=None):
    """Nacte Settings. Chybejici soubor znamena vychozi hodnoty.

    Rozbita konfigurace se nepolyka: tise ignorovany preklep by uzivateli
    vzal jeho nastaveni, aniž by se dozvedel proc.
    """
    path = Path(path) if path is not None else config_path()
    if not path.is_file():
        return Settings()

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Konfigurace {path} není platné TOML: {exc}") from None
    except OSError as exc:
        raise ValueError(f"Konfiguraci {path} nelze přečíst: {exc}") from None

    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"Konfigurace {path} obsahuje neznámé klíče: {', '.join(unknown)}. "
            f"Povolené jsou: {', '.join(sorted(_KNOWN_KEYS))}."
        )

    settings = Settings()
    if "host" in raw:
        settings.host = str(raw["host"])
    if "port" in raw:
        settings.port = _port_number(raw["port"], "port")
    if "watch_ports" in raw:
        table = raw["watch_ports"]
        if not isinstance(table, dict):
            raise ValueError(
                f"Konfigurace {path}: watch_ports musí být tabulka "
                '[watch_ports] s porty jako klíči, např. 22 = "SSH".'
            )
        settings.watch_ports = {
            _port_number(port, f"watch_ports.{port}"): str(label)
            for port, label in table.items()
        }
    if "ignored_ports" in raw:
        ports = raw["ignored_ports"]
        if not isinstance(ports, list):
            raise ValueError(
                f"Konfigurace {path}: ignored_ports musí být seznam čísel portů, "
                "např. ignored_ports = [53, 631]."
            )
        settings.ignored_ports = {
            _port_number(port, "ignored_ports") for port in ports
        }
    return settings
