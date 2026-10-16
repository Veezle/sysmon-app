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

# Vite hashuje nazvy; tvar je assets/index-<hash>.{js,css}. Hash je na jednom
# miste proto, ze na nej odkazuje index - kdyby se mel a nesedel, fixture by
# tise ukazovala na soubor, ktery neexistuje, a nic by si toho nevsimlo.
HASH = "abc123"
ASSET_NAME = f"assets/index-{HASH}.js"
STYLE_NAME = f"assets/index-{HASH}.css"

INDEX_HTML = f"""<!doctype html>
<html lang="cs">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="/static/icon.svg" />
    <title>Sysmon</title>
    <script type="module" crossorigin src="/static/{ASSET_NAME}"></script>
    <link rel="stylesheet" crossorigin href="/static/{STYLE_NAME}">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
"""


@contextlib.contextmanager
def fake_web(index=None):
    """Vytvori docasny web/ s index.html, static/ a hashovanymi assety.

    Vraci (root, static, index_path) a po skonceni bloku uklidi. Vznikaji
    oba soubory, na ktere vychozi index odkazuje (`.js` i `.css`) - odkaz
    na neexistujici asset je presne ta chyba, ktera se nacte bez vzhledu
    a v jednotkovych testech nema jak zaznit.
    """
    index = INDEX_HTML if index is None else index
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        static = root / "static"
        (static / "assets").mkdir(parents=True)
        (static / ASSET_NAME).write_text("console.log(1);\n", encoding="utf-8")
        (static / STYLE_NAME).write_text(".a{color:red}\n", encoding="utf-8")
        (static / "style.css").write_text(".a{color:red}\n", encoding="utf-8")
        (static / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
        (root / "index.html").write_text(index, encoding="utf-8")
        yield root, static, root / "index.html"
