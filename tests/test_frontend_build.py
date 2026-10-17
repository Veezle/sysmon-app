"""Piny, ktere meri produkt: build, chovani v prohlizeci a prebuildovavani.

Vsechny tri potrebuji build v `sysmon_app/web/` a `google-chrome-stable`.
Bez nich se preskakuji - sada musi zustat zelena i v cerstvem klonu, ale
v hlaseni tasku musi byt videt, jestli pin opravdu bezel.

Co se tu meri:
  * privacy  - build netahá nic z ciziho originu (zadne CDN, zadny @import),
  * rebuild  - konstantni data neznamenaji prebuildovani seznamu (childList
               mutace = 0, prvni radek je porad tyz objekt),
  * fallback - kdyz /events umre, stranka se i tak aktualizuje pres /stats.

U rebuild pinu se pocitaji i /stats requesty: `mutations=0` pri nule tiku je
planý pin. Proti otevrenemu SSE by `--virtual-time-budget` visel (Chrome ceka
na otevreny fetch), proto oba prohlizecove testy pouzivaji BrokenEventsHandler.
"""

import contextlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from sysmon_app import server
from sysmon_app.feed import SnapshotFeed

CHROME = shutil.which("google-chrome-stable") or shutil.which("chromium")
BUILD_INDEX = server.WEB_DIR / "index.html"
NEEDS_BUILD = unittest.skipUnless(
    BUILD_INDEX.exists(), "chybi build (npm run build ve frontend/)"
)
NEEDS_CHROME = unittest.skipUnless(CHROME, "chybi headless Chrome")

FIXTURE = Path(__file__).parent / "fixtures" / "snapshot.json"

# Seznamy, ktere se ve frontebu prekresluji. Identita prvniho radku je
# citelnejsi nez pocet uzlu: `replaceChildren` se stejnymi daty necha pocet
# uzlu nezmeneny, takze pin na pocet by nic nemeril.
LIST_IDS = ("cores", "services-list", "proc-list", "docker-containers")

# Minimalni pocet /stats requestu za 120 s virtualniho casu. Frontend polluje
# kazdych 1,5 s po STALE_MS=4,5 s ticha, takze se ocekava ~77; 50 je rezerva,
# ktera jeste dokazuje, ze tiky skutecne probehly.
MIN_POLLS = 50


class ConstantMonitor:
    """Porad stejny snapshot - pin meri prebuildovavani, ne zmenu dat."""

    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self._snapshot


def dump_dom(port, budget_ms):
    """Vrati serializovane DOM po `budget_ms` virtualniho casu."""
    out = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         f"--virtual-time-budget={budget_ms}", "--dump-dom",
         f"http://127.0.0.1:{port}/"],
        capture_output=True, text=True, timeout=180, check=True,
    )
    return out.stdout


def _cpu_value(html):
    found = re.search(r'id="cpu"[^>]*>([^<]*)', html)
    return found.group(1) if found else None


@contextlib.contextmanager
def built_web(index_html):
    """Docasny web root s kopii realneho buildu a vlastnim index.html.

    Assety se kopiruji, ne symlinkuji: server je cte pres STATIC_DIR a test
    nesmi nic menit v `sysmon_app/web/`. Index je harness, ktery importuje
    tyz bundle jako produkt - takze se meri skutecny frontend, ne kopie.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(server.STATIC_DIR, root / "static")
        (root / "index.html").write_text(index_html, encoding="utf-8")
        with mock.patch.object(server, "WEB_DIR", root), \
             mock.patch.object(server, "STATIC_DIR", root / "static"):
            yield root


class BrokenEventsHandler(server.Handler):
    """/events vraci 500 - pin fallbacku potrebuje mrtvy proud.

    Zaroven tim drzi `--virtual-time-budget` funkcni: otevrene SSE by
    zastavilo virtualni cas a `dump-dom` by visel do timeoutu.
    """

    def do_GET(self):
        if self._path() == "/events":
            self._send_empty(500)
            return
        super().do_GET()


def serve_with(monitor, feed, handler):
    """serve() cte `Handler` v dobe volani - patch plati jen pro tento server."""
    with mock.patch.object(server, "Handler", handler):
        srv = server.serve(monitor, feed, "127.0.0.1", 0)
    return srv


def start_serving(testcase, srv):
    """Rozjede server ve vlakne a zaregistruje uklid; vraci port."""
    testcase.addCleanup(srv.server_close)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    testcase.addCleanup(srv.shutdown)
    return srv.server_address[1]


def bundle_url():
    """Najde bundle, na ktery odkazuje realny index.html."""
    index = BUILD_INDEX.read_text(encoding="utf-8")
    found = re.search(r'src="/static/(assets/index-[^"]+\.js)"', index)
    if found is None:
        raise AssertionError("build neobsahuje odkaz na hashovany JS bundle")
    return "/static/" + found.group(1)


# Harness: importuje bundle, pocka na prvni vykresleni vsech seznamu, pak
# 120 s virtualniho casu pozoruje childList mutace. Pocita i /stats requesty,
# aby `mutations=0` nebylo plané (nula tiku by jinak prošla).
HARNESS = """<!doctype html>
<html lang="cs"><head><meta charset="utf-8"><title>harness</title></head>
<body>
<div id="root"></div>
<div id="result">pending</div>
<script type="module">
  const LISTS = %(lists)s;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let stats = 0;
  const realFetch = window.fetch.bind(window);
  window.fetch = (...args) => {
    if (String(args[0]).indexOf("/stats") !== -1) stats += 1;
    return realFetch(...args);
  };
  await import("%(bundle)s");
  // Prvni vykresleni: cekej, dokud vsechny ctyri seznamy nemaji radek.
  const deadline = performance.now() + 10000;
  let ready = false;
  while (performance.now() < deadline) {
    if (LISTS.every((id) => {
      const el = document.getElementById(id);
      return el !== null && el.firstElementChild !== null;
    })) { ready = true; break; }
    await sleep(50);
  }
  const seen = LISTS.map((id) => {
    const el = document.getElementById(id);
    return el === null ? null : el.firstElementChild;
  });
  let mutations = 0;
  const observer = new MutationObserver((records) => { mutations += records.length; });
  for (const id of LISTS) {
    const el = document.getElementById(id);
    if (el !== null) observer.observe(el, { childList: true, subtree: true });
  }
  const before = stats;
  await sleep(120000);
  const same = LISTS.map((id, i) => {
    const el = document.getElementById(id);
    const now = el === null ? null : el.firstElementChild;
    return seen[i] === null ? "n/a" : String(now === seen[i]);
  });
  document.getElementById("result").textContent =
    "ready=" + String(ready) +
    " mutations=" + mutations +
    " same=" + same.join(",") +
    " polls=" + (stats - before) +
    " total=" + stats;
</script></body></html>
"""


def parse_result(html):
    """Vytahne obsah #result z dumpnuteho DOM."""
    found = re.search(r'id="result"[^>]*>([^<]*)<', html)
    if found is None:
        raise AssertionError("harness nezapsal #result (stranka nedoběhla)")
    return found.group(1).strip()


class BuildPrivacyTest(unittest.TestCase):
    @NEEDS_BUILD
    def test_build_has_no_external_origins(self):
        index = BUILD_INDEX.read_text(encoding="utf-8").lower()
        for pattern in ('href="http', 'src="http', 'href="//', 'src="//'):
            self.assertNotIn(pattern, index, pattern)
        for css in (server.WEB_DIR / "static" / "assets").glob("*.css"):
            text = css.read_text(encoding="utf-8").lower()
            self.assertNotIn("url(http", text, css.name)
            self.assertNotIn("@import", text, css.name)


class RebuildTest(unittest.TestCase):
    @NEEDS_BUILD
    @NEEDS_CHROME
    def test_constant_snapshot_does_not_rebuild_lists(self):
        base = json.loads(FIXTURE.read_text(encoding="utf-8"))
        monitor = ConstantMonitor(base)
        feed = SnapshotFeed(monitor)
        harness = HARNESS % {
            "lists": json.dumps(list(LIST_IDS)),
            "bundle": bundle_url(),
        }
        with built_web(harness) as _root:
            srv = serve_with(monitor, feed, BrokenEventsHandler)
            self.assertIs(srv.RequestHandlerClass, BrokenEventsHandler,
                          "patch Handler neprosel - /events by drzel SSE otevrene")
            port = start_serving(self, srv)
            html = dump_dom(port, 200000)

        result = parse_result(html)
        self.assertIn("ready=true", result,
                      "harness nezachytil prvni vykresleni seznamu: " + result)
        self.assertNotIn("n/a", result,
                         "nektery seznam zustal prazdny - fixture/harness je vadna: " + result)
        values = dict(part.split("=", 1) for part in result.split() if "=" in part)
        self.assertEqual(values.get("mutations"), "0", result)
        self.assertEqual(values.get("same"), "true,true,true,true", result)
        polls = int(values.get("polls", "0"))
        self.assertGreaterEqual(polls, MIN_POLLS,
                                "za 120 s probehlo malo tiku (%d) - pin nic nemeri" % polls)


class PollingFallbackTest(unittest.TestCase):
    @NEEDS_BUILD
    @NEEDS_CHROME
    def test_page_still_updates_without_sse(self):
        base = json.loads(FIXTURE.read_text(encoding="utf-8"))
        counter = {"n": 0}

        class CountingMonitor:
            def snapshot(self):
                counter["n"] += 1
                return {**base, "cpu": float(counter["n"])}

        monitor = CountingMonitor()
        feed = SnapshotFeed(monitor)
        srv = serve_with(monitor, feed, BrokenEventsHandler)
        self.assertIs(srv.RequestHandlerClass, BrokenEventsHandler)
        port = start_serving(self, srv)

        first = dump_dom(port, 4000)
        later = dump_dom(port, 20000)
        self.assertNotEqual(_cpu_value(first), _cpu_value(later),
                            "stranka se bez /events neaktualizovala")


if __name__ == "__main__":
    unittest.main()
