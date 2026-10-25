#!/usr/bin/env python3
"""Zmeri pamet okna sysmon-app v case.

Nastroj je zamerne jen stdlib: cte /proc, pocita strom potomku a RSS.
Matematika trendu je v cistych funkcich, aby slo testovat bez /proc.

Kategorie:
    app      - koren proces (Tauri binarka)
    web      - WebKitWebProcess
    network  - WebKitNetworkProcess
    daemon   - sysmon-app-daemon nebo python3 -m sysmon_app
    other    - ostatni potomci v stromu (napr. WebKitGPUProcess)

Navratove kody:
    0 - ploche podle prahu
    1 - prah prekrocen
    2 - mereni neslo (proces zmizel, malo vzorku, chyba vstupu)
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

CATEGORIES = ("app", "web", "network", "daemon", "other")
CSV_HEADER = (
    "elapsed_s,app_kb,web_kb,network_kb,daemon_kb,other_kb,total_kb"
)
KB_PER_MB = 1024.0
SECONDS_PER_HOUR = 3600.0


# --- cista matematika (testovatelna bez /proc) -----------------------------


def slope_mb_per_hour(points: Iterable[tuple[float, float]]) -> float:
    """Linearni regrese bodu (cas_s, rss_kb), vysledek v MB/h.

    Metoda nejmensich ctvercu. ValueError znamena, ze trend nejde spocitat:
    mene nez dva body nebo nulove casove rozpeti.
    """
    data = list(points)
    if len(data) < 2:
        raise ValueError("na trend jsou potřeba aspoň dva vzorky")
    mean_t = sum(t for t, _ in data) / len(data)
    mean_r = sum(r for _, r in data) / len(data)
    denom = sum((t - mean_t) ** 2 for t, _ in data)
    if denom == 0:
        raise ValueError("vzorky mají stejný čas, trend nejde spočítat")
    slope_kb_per_s = sum(
        (t - mean_t) * (r - mean_r) for t, r in data
    ) / denom
    return slope_kb_per_s * SECONDS_PER_HOUR / KB_PER_MB


def median_delta(
    points: Sequence[tuple[float, float]], window_s: float = 600.0
) -> tuple[float, float, float]:
    """Mediany prvnich a poslednich `window_s` sekund a jejich rozdil v MB.

    `points` je (cas_s, rss_kb), nemusi byt setridene. Prvni okno zacina
    prvnim vzorkem, posledni konci poslednim vzorkem.
    """
    data = sorted(points, key=lambda p: p[0])
    if not data:
        raise ValueError("bez vzorků není z čeho počítat medián")
    first_edge = data[0][0] + window_s
    last_edge = data[-1][0] - window_s
    first = [rss for t, rss in data if t <= first_edge]
    last = [rss for t, rss in data if t >= last_edge]
    first_mb = statistics.median(first) / KB_PER_MB
    last_mb = statistics.median(last) / KB_PER_MB
    return first_mb, last_mb, last_mb - first_mb


# --- /proc ----------------------------------------------------------------


def classify_cmdline(argv: Sequence[str]) -> str:
    """Zaradi proces podle cmdline. Koren se sem neposila (je to `app`)."""
    if not argv:
        return "other"
    name = os.path.basename(argv[0])
    if "WebKitWebProcess" in name:
        return "web"
    if "WebKitNetworkProcess" in name:
        return "network"
    if "sysmon-app-daemon" in name:
        return "daemon"
    for index, arg in enumerate(argv):
        if (
            arg == "-m"
            and index + 1 < len(argv)
            and argv[index + 1] == "sysmon_app"
        ):
            return "daemon"
        if arg.startswith("-msysmon_app"):
            return "daemon"
    return "other"


def _read_status(pid: int) -> tuple[int, int, str] | None:
    """Vrati (ppid, rss_kb, state) nebo None, kdyz proces mezitim zmizel."""
    try:
        with open(
            f"/proc/{pid}/status", "r", encoding="utf-8", errors="replace"
        ) as handle:
            ppid = None
            rss_kb = 0
            state = "?"
            for line in handle:
                if line.startswith("PPid:"):
                    ppid = int(line.split()[1])
                elif line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                elif line.startswith("State:"):
                    state = line.split()[1]
            if ppid is None:
                return None
            return ppid, rss_kb, state
    except (OSError, ValueError, IndexError):
        return None


def _read_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [os.fsdecode(part) for part in raw.split(b"\0") if part]


def _read_exe(pid: int) -> str | None:
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None
    return exe.removesuffix(" (deleted)")


def collect_sample(root_pid: int) -> dict[str, int] | None:
    """Posbira RSS stromu pod `root_pid`. None = koren uz neexistuje."""
    statuses: dict[int, tuple[int, int, str]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        status = _read_status(pid)
        if status is not None:
            statuses[pid] = status

    root_status = statuses.get(root_pid)
    if root_status is None or root_status[2] == "Z":
        return None

    children: dict[int, list[int]] = defaultdict(list)
    for pid, (ppid, _, _) in statuses.items():
        children[ppid].append(pid)

    tree: list[int] = []
    seen: set[int] = set()
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        if pid in seen or pid not in statuses:
            continue
        seen.add(pid)
        tree.append(pid)
        stack.extend(children.get(pid, ()))

    totals = {category: 0 for category in CATEGORIES}
    for pid in tree:
        category = "app" if pid == root_pid else classify_cmdline(
            _read_cmdline(pid)
        )
        totals[category] += statuses[pid][1]
    totals["total"] = sum(totals[category] for category in CATEGORIES)
    return totals


def find_sysmon_app_pids() -> list[int]:
    """PIDy procesu, jejichz exe se jmenuje presne `sysmon-app`."""
    found: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        exe = _read_exe(pid)
        if exe is not None and os.path.basename(exe) == "sysmon-app":
            found.append(pid)
    return sorted(found)


# --- mereni ---------------------------------------------------------------


def _write_csv_row(writer, elapsed_s: int, sample: dict[str, int]) -> None:
    writer.writerow(
        [
            elapsed_s,
            sample["app"],
            sample["web"],
            sample["network"],
            sample["daemon"],
            sample["other"],
            sample["total"],
        ]
    )


def _mb(kb: int | float) -> float:
    return kb / KB_PER_MB


def measure(
    root_pid: int,
    duration: float,
    interval: float,
    warmup: float,
    csv_path: str | None,
    slope_limit: float,
    delta_limit: float,
) -> int:
    csv_handle = None
    csv_writer = None
    csv_failed = False
    if csv_path is not None:
        try:
            csv_handle = open(csv_path, "w", encoding="utf-8", newline="")
            csv_writer = csv.writer(csv_handle, lineterminator="\n")
            csv_writer.writerow(CSV_HEADER.split(","))
            csv_handle.flush()
        except OSError as err:
            print(f"CSV nelze zapsat: {err}", file=sys.stderr)
            if csv_handle is not None:
                try:
                    csv_handle.close()
                except OSError:
                    pass
            return 2

    samples: list[dict[str, int]] = []
    start = time.monotonic()
    next_at = interval
    vanished = False
    try:
        while True:
            now = time.monotonic() - start
            sample = collect_sample(root_pid)
            if sample is None:
                print(
                    f"Proces {root_pid} zmizel v čase {now:.0f} s; "
                    "měření končí.",
                    file=sys.stderr,
                )
                vanished = True
                break
            elapsed_s = int(round(now))
            sample["elapsed_s"] = elapsed_s
            samples.append(sample)
            if csv_writer is not None:
                try:
                    _write_csv_row(csv_writer, elapsed_s, sample)
                    csv_handle.flush()
                except OSError as err:
                    print(
                        f"Zápis CSV selhal: {err}; měření končí.",
                        file=sys.stderr,
                    )
                    csv_failed = True
                    break
            print(
                f"t={elapsed_s:4d}s app={_mb(sample['app']):7.1f} "
                f"web={_mb(sample['web']):7.1f} "
                f"net={_mb(sample['network']):6.1f} "
                f"daemon={_mb(sample['daemon']):6.1f} "
                f"other={_mb(sample['other']):6.1f} "
                f"total={_mb(sample['total']):7.1f} MB",
                flush=True,
            )
            if now >= duration:
                break
            elapsed_now = time.monotonic() - start
            delay = min(next_at - elapsed_now, duration - elapsed_now)
            if delay > 0:
                time.sleep(delay)
            next_at += interval
    except KeyboardInterrupt:
        print("\nMěření přerušeno.", file=sys.stderr)
        vanished = True
    finally:
        if csv_handle is not None:
            try:
                csv_handle.close()
            except OSError as err:
                print(f"Zavření CSV selhalo: {err}", file=sys.stderr)
                csv_failed = True

    elapsed_last = samples[-1]["elapsed_s"] if samples else 0
    print(
        f"Měřeno {elapsed_last} s, vzorků: {len(samples)}, "
        f"warmup: {warmup:.0f} s."
    )
    if csv_path is not None:
        print(f"CSV: {csv_path}")

    if not samples:
        print("Žádný vzorek; měření nelze vyhodnotit.", file=sys.stderr)
        return 2
    if vanished:
        return 2
    if csv_failed:
        print(
            "Měření nelze vyhodnotit: zápis CSV selhal.",
            file=sys.stderr,
        )
        return 2

    # Do analyzy jdou jen vzorky po zahrati. Rozhoduje skutecny cas vzorku,
    # ne poradi: interval se muze lehce rozejit se spanim.
    post = [s for s in samples if s["elapsed_s"] >= warmup]
    if len(post) < 2:
        print(
            "Málo vzorků po warmupu; měření nelze vyhodnotit.",
            file=sys.stderr,
        )
        return 2

    web_points = [(s["elapsed_s"], s["web"]) for s in post]
    if any(rss <= 0 for _, rss in web_points):
        print(
            "Kategorie web nebyla po celý čas měření vidět "
            "(WebKitWebProcess chybí); měření nelze vyhodnotit.",
            file=sys.stderr,
        )
        return 2

    daemon_last = post[-1]["daemon"]
    if daemon_last <= 0:
        print(
            "Upozornění: kategorie daemon je nulová – démon neběží "
            "ve stromu okna (možná cizí démon na 8430).",
            file=sys.stderr,
        )

    try:
        slope = slope_mb_per_hour(web_points)
        first_med, last_med, delta = median_delta(web_points)
    except ValueError as err:
        print(f"Trend nelze spočítat: {err}", file=sys.stderr)
        return 2
    total_last = post[-1]["total"]
    web_last = post[-1]["web"]

    flat = slope <= slope_limit and delta <= delta_limit
    verdict = "ploché" if flat else "není ploché"

    print("")
    print(f"web slope: {slope:.2f} MB/h (limit {slope_limit:.1f} MB/h)")
    print(f"web medián prvních 10 min: {first_med:.1f} MB")
    print(f"web medián posledních 10 min: {last_med:.1f} MB")
    print(f"web delta: {delta:.1f} MB (limit {delta_limit:.1f} MB)")
    print(f"web RSS na konci: {_mb(web_last):.1f} MB")
    print(f"celková RSS na konci: {_mb(total_last):.1f} MB")
    print(f"RSS démona na konci: {_mb(daemon_last):.1f} MB")
    print(f"Verdikt: {verdict}")
    return 0 if flat else 1


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"není číslo: {value}") from err
    if number <= 0:
        raise argparse.ArgumentTypeError("hodnota musí být kladná")
    return number


def _non_negative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"není číslo: {value}") from err
    if number < 0:
        raise argparse.ArgumentTypeError("hodnota nesmí být záporná")
    return number


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"není číslo: {value}") from err
    if number <= 0:
        raise argparse.ArgumentTypeError("hodnota musí být kladná")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Změří paměť okna sysmon-app: strom potomků, RSS kategorií "
            "a lineární trend webview."
        )
    )
    parser.add_argument(
        "--pid",
        type=_positive_int,
        help="PID okna; bez něj se hledá proces s exe sysmon-app",
    )
    parser.add_argument(
        "--duration",
        type=_positive_float,
        default=3600.0,
        help="doba měření v sekundách (výchozí 3600)",
    )
    parser.add_argument(
        "--interval",
        type=_positive_float,
        default=10.0,
        help="interval vzorků v sekundách (výchozí 10)",
    )
    parser.add_argument(
        "--warmup",
        type=_non_negative_float,
        default=1200.0,
        help="zahřátí, které do trendu nevstupuje (výchozí 1200)",
    )
    parser.add_argument(
        "--csv",
        metavar="CESTA",
        help="zapsat vzorky do CSV",
    )
    parser.add_argument(
        "--slope-limit",
        type=_non_negative_float,
        default=5.0,
        help="maximální trend web v MB/h (výchozí 5.0)",
    )
    parser.add_argument(
        "--delta-limit",
        type=_non_negative_float,
        default=15.0,
        help="maximální rozdíl mediánů web v MB (výchozí 15.0)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.pid is not None:
        root_pid = args.pid
    else:
        candidates = find_sysmon_app_pids()
        if not candidates:
            print(
                "Nenašel jsem proces s exe `sysmon-app`. "
                "Zadej PID přes --pid.",
                file=sys.stderr,
            )
            return 2
        if len(candidates) > 1:
            print(
                "Nalezeno více kandidátů; zadej --pid:", file=sys.stderr
            )
            for pid in candidates:
                print(f"  {pid} {_read_exe(pid)}", file=sys.stderr)
            return 2
        root_pid = candidates[0]

    if _read_status(root_pid) is None:
        print(f"Proces {root_pid} neexistuje.", file=sys.stderr)
        return 2

    print(
        f"Měření paměti: PID {root_pid}, doba {args.duration:.0f} s, "
        f"interval {args.interval:.0f} s, warmup {args.warmup:.0f} s"
    )
    return measure(
        root_pid,
        args.duration,
        args.interval,
        args.warmup,
        args.csv,
        args.slope_limit,
        args.delta_limit,
    )


if __name__ == "__main__":
    sys.exit(main())
