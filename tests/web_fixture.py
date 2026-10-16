"""Docasny web/ adresar pro testy - ve tvaru, jaky vydava Vite build.

Testy se nesmi opirat o `sysmon_app/web/` v repu: ten je od faze 2 build
a v .gitignore, takze v cerstvem klonu neexistuje. Tvar index.html je tu
zamerne co nejblizsi realnemu Vite vystupu (hashovany asset pod
/static/assets/), aby pin na "zadny spustitelny inline kod" netestoval
neco, co build nikdy nevyrobi.
"""

import contextlib
from pathlib import Path
from tempfile import TemporaryDirectory

# Vite hashuje nazvy; tvar je assets/index-<hash>.js
ASSET_NAME = "assets/index-abc123.js"
INDEX_HTML = """<!doctype html>
<html lang="cs">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="/static/icon.svg" />
    <title>Sysmon</title>
    <script type="module" crossorigin src="/static/assets/index-abc123.js"></script>
    <link rel="stylesheet" crossorigin href="/static/assets/index-def456.css">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
"""


@contextlib.contextmanager
def fake_web(index=INDEX_HTML):
    """Vytvori docasny web/ s index.html, static/ a hashovanym assetem.

    Vraci (root, static, index_path) a po skonceni bloku uklidi.
    """
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        static = root / "static"
        (static / "assets").mkdir(parents=True)
        (static / ASSET_NAME).write_text("console.log(1);\n", encoding="utf-8")
        (static / "style.css").write_text(".a{color:red}\n", encoding="utf-8")
        (static / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
        (root / "index.html").write_text(index, encoding="utf-8")
        yield root, static, root / "index.html"
