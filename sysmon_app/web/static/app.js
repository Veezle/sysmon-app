// --- Token pro akce ---------------------------------------------------------
// Vezme se z ?token= v URL, ulozi do localStorage a z adresy se odstrani,
// aby nevisel v historii. Kdyz chybi, akcni tlacitka jen poradi, co udelat.
const TOKEN_KEY = "sysmon-token";

function captureToken() {
  let fromUrl = null;
  try {
    const params = new URLSearchParams(location.search);
    fromUrl = params.get("token");
    if (fromUrl) {
      try { localStorage.setItem(TOKEN_KEY, fromUrl); } catch (e) { /* privatni rezim */ }
      params.delete("token");
      const rest = params.toString();
      history.replaceState(null, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
    }
  } catch (e) { /* stary prohlizec bez URLSearchParams */ }
  if (fromUrl) return fromUrl;
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
}

const TOKEN = captureToken();

function actionHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (TOKEN) headers["X-Sysmon-Token"] = TOKEN;
  return headers;
}

function missingTokenMessage() {
  return "Chybí token — otevři dashboard s ?token=… "
       + "(token je v ~/.config/sysmon/token).";
}

// Server token odmitl (403) - ulozeny token je nejspis stary. Zapomeneme ho,
// aby pristi otevreni s ?token= fungovalo, a vysvetlime, co udelat.
function forgetToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch (e) { /* privatni rezim */ }
  alert("Server token odmítl (403). Uložený token jsem zapomněl — "
      + "otevři dashboard znovu s ?token= v adrese "
      + "(token najdeš v ~/.config/sysmon/token).");
}

const fmt = b => {
  const u = ["B","KB","MB","GB","TB"]; let i = 0;
  while (b >= 1024 && i < u.length-1) { b /= 1024; i++; }
  return b.toFixed(1) + " " + u[i];
};
const color = p => p < 60 ? "var(--green)" : p < 85 ? "var(--amber)" : "var(--red)";
// Do stranky se zapisuje JEN kdyz se hodnota opravdu zmeni. Necte se pritom
// zpet z DOM - style.background s "var(--green)" se necte spolehlive - ale
// z vlastni cache. Kazdy zapis do stranky stoji renderer pamet a ta se pak
// hromadi, protoze engine nikdy nema klid na uklid (viz CLAUDE.md).
const lastValues = new WeakMap();

function setProp(node, prop, value) {
  let rec = lastValues.get(node);
  if (!rec) { rec = {}; lastValues.set(node, rec); }
  if (rec[prop] === value) return;
  rec[prop] = value;
  if (prop === "text") node.textContent = value;
  else if (prop === "title") node.title = value;
  else node.style[prop] = value;
}

// Presune prvek jen kdyz na danem miste jeste neni. appendChild by ho jinak
// kazdy tick vyndal a znovu vlozil, coz je zbytecny zasah do layoutu.
function placeAt(parent, node, index) {
  if (parent.children[index] !== node) {
    parent.insertBefore(node, parent.children[index] || null);
  }
}

const setBar = (id, p) => {
  const bar = document.getElementById(id);
  setProp(bar, "width", p + "%");
  setProp(bar, "background", color(p));
};

// Drobny helper na stavbu elementu - vsechny karty se pak ctou stejne.
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

const formatUptime = (sec) => {
  if (!Number.isFinite(sec)) return "–";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
};

const formatPorts = (raw) => {
  if (!raw) return "";
  const seen = new Set();
  const out = [];
  raw.split(",").forEach(p => {
    const m = p.trim().match(/(?:[\d.\[\]:]*:)?(\d+)(?:->(\d+))?\/(\w+)/);
    if (!m) return;
    const host = m[1];
    const cont = m[2] || m[1];
    const proto = m[3];
    const key = `${host}->${cont}/${proto}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(host === cont ? `${host}/${proto}` : `${host}→${cont}/${proto}`);
  });
  return out.join("  ");
};

// ---- Battery chart (24h) ----
let chartKey = null;   // co bylo naposledy nakresleno

function drawBatteryChart(data) {
  const canvas = document.getElementById("battery-chart");
  const wrap = document.getElementById("battery-chart-wrap");
  if (!canvas || !wrap) return;
  if (!data || data.length < 2) {
    setProp(wrap, "display", "none");
    return;
  }
  setProp(wrap, "display", "block");

  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  // Prekresluje se jen kdyz se zmenila data nebo velikost platna - jinak by se
  // kazdych 1,5 s zbytecne prekresloval stejny obrazek.
  const key = data.length + "|" + data[data.length - 1].t + "|" +
              Math.round(rect.width) + "x" + Math.round(rect.height);
  if (key === chartKey) return;
  chartKey = key;

  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);

  // Grid lines at 25/50/75%
  ctx.strokeStyle = "rgba(203,213,225,.5)";
  ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach(f => {
    const y = h - f * h;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  });

  const maxT = data[data.length - 1].t || 1;
  const xFor = (t) => (t / maxT) * w;
  const yFor = (v) => h - (v / 100) * h;

  // Fill
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgba(217,119,6,.28)");
  grad.addColorStop(1, "rgba(217,119,6,0)");
  ctx.beginPath();
  ctx.moveTo(xFor(data[0].t), yFor(data[0].v));
  for (let i = 1; i < data.length; i++) {
    ctx.lineTo(xFor(data[i].t), yFor(data[i].v));
  }
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.strokeStyle = "rgba(217,119,6,.95)";
  ctx.lineWidth = 1.8;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.moveTo(xFor(data[0].t), yFor(data[0].v));
  for (let i = 1; i < data.length; i++) {
    ctx.lineTo(xFor(data[i].t), yFor(data[i].v));
  }
  ctx.stroke();

  // Endpoint dot
  const last = data[data.length - 1];
  ctx.beginPath();
  ctx.arc(xFor(last.t), yFor(last.v), 3, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(217,119,6,1)";
  ctx.fill();
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ---- Karty se seznamy: prvky se vyrobi jednou, dal se jen aktualizuji ----
// Driv se kazdy tick zahodily (replaceChildren) a postavily znovu - kolem 90
// prvku kazdych 1,5 s. Renderer Chromia takovou pamet nevraci, takze rostl
// lineairne a bez stropu (zmereno ~15 MB/min jen na teto casti). Proto se
// radky drzi v cache a meni se na nich jen text, barva a vyska pruhu.

const coreNodes = [];       // {core, fill, label} pro kazde jadro
const svcRows = new Map();  // port -> radek
const procRows = [];        // znovupouzivane radky procesu

function renderCores(values) {
  const cc = document.getElementById("cores");
  while (coreNodes.length < values.length) {
    const fill = el("div", "cfill");
    const label = el("span");
    const core = el("div", "core");
    core.append(fill, label);
    coreNodes.push({ core, fill, label });
    cc.appendChild(core);
  }
  while (coreNodes.length > values.length) {
    coreNodes.pop().core.remove();
  }
  values.forEach((v, i) => {
    const { core, fill, label } = coreNodes[i];
    setProp(core, "title", "Jádro " + i + ": " + v.toFixed(0) + "%");
    setProp(fill, "height", v + "%");
    setProp(fill, "background", color(v));
    setProp(label, "text", v.toFixed(0));
  });
}

function renderServices(items) {
  const list = document.getElementById("services-list");
  if (svcRows.size === 0) list.replaceChildren();  // zahodit "Načítání…"
  items.forEach((s, i) => {
    let row = svcRows.get(s.port);
    if (!row) {
      row = el("div", "svc-row");
      row.append(el("span", "svc-dot"), el("span", "svc-port", s.port),
                 el("span", "svc-label", s.label || ""));
      svcRows.set(s.port, row);
    }
    const on = !!s.on;
    if (row.classList.contains("on") !== on) row.classList.toggle("on", on);
    // Poradi ridi server - prvek se jen presune, kdyz na svem miste neni.
    placeAt(list, row, i);
  });
  svcRows.forEach((row, port) => {
    if (!items.some(s => s.port === port)) {
      row.remove();
      svcRows.delete(port);
    }
  });
}

function procRow() {
  const name = el("span", "proc-name");
  const cpu = el("span", "proc-cpu");
  const mem = el("span", "proc-mem");
  const kill = el("button", "proc-kill", "✕");
  kill.type = "button";
  const row = el("div", "proc-row");
  row.append(name, cpu, mem, kill);
  // PID i jmeno se meni kazdy tick, takze je listener cte z data-* - jinak by
  // se musel vyrobit novy closure (a s nim novy prvek) pri kazdem obnoveni.
  kill.addEventListener("click", () => {
    killProcess(Number(kill.dataset.pid), kill.dataset.name, kill);
  });
  return { row, name, cpu, mem, kill };
}

function renderProcesses(procs, nCores) {
  const list = document.getElementById("proc-list");
  if (procRows.length === 0) list.replaceChildren();  // zahodit "Načítání…"
  while (procRows.length < procs.length) {
    const made = procRow();
    procRows.push(made);
    list.appendChild(made.row);
  }
  while (procRows.length > procs.length) {
    procRows.pop().row.remove();
  }
  procs.forEach((p, i) => {
    const { row, name, cpu, mem, kill } = procRows[i];
    const share = p.cpu / nCores;
    setProp(name, "text", p.name);
    setProp(name, "title", `PID ${p.pid} · ${p.name}`);
    setProp(cpu, "text", share.toFixed(1) + "%");
    setProp(cpu, "color", color(share));
    setProp(mem, "text", fmt(p.mem));
    setProp(kill, "title", `Ukončit ${p.name} (PID ${p.pid})`);
    if (kill.dataset.pid !== String(p.pid)) kill.dataset.pid = p.pid;
    if (kill.dataset.name !== p.name) kill.dataset.name = p.name;
    placeAt(list, row, i);
  });
}

// ---- Docker: seskupene kontejnery podle Compose projektu ----
// Skupiny chodi ze serveru uz serazene (abecedne, "Ostatní" posledni), takze
// se tady nesortuje - proste se projde poradi z API.
const dockerGroups = new Map();  // projekt -> {group, title}
const dockerRows = new Map();    // jmeno kontejneru -> radek
let dockerMessage = document.createTextNode("Načítání kontejnerů…");  // text misto karet

function dockerRow(key) {
  const meta = el("div", "ctr-meta");
  const name = el("span", "ctr-name", key);
  meta.appendChild(name);

  const metrics = el("span", "ctr-metrics");
  const cpu = el("b", null, "—");
  const ram = el("b", null, "—");
  metrics.append("CPU ", cpu, " · RAM ", ram);

  const action = el("button", "ctr-action", "↻");
  action.type = "button";
  action.title = "Restart kontejneru";
  action.addEventListener("click", () => restartContainer(action.dataset.name, action));

  const row = el("div", "ctr-row");
  row.append(el("span", "ctr-dot"), meta, metrics, action);
  return { row, meta, name, cpu, ram, action, ports: null };
}

// Misto karet se zobrazuje jedna textova hlaska (nedostupny Docker, zadny
// kontejner). Drzi se porad stejny textovy uzel - nemeni se, dokud se nezmeni
// text, takze se do stranky vubec neszaha.
function showDockerMessage(list, text) {
  if (dockerMessage && dockerMessage.textContent === text) return;
  list.replaceChildren();
  dockerMessage = document.createTextNode(text);
  list.appendChild(dockerMessage);
  dockerGroups.clear();
  dockerRows.clear();
}

function renderDocker(data) {
  const list = document.getElementById("docker-containers");
  const count = document.getElementById("docker-count");

  if (!data.available) {
    setProp(count, "text", "N/A");
    if (list.className !== "off") list.className = "off";
    showDockerMessage(list, data.error || "Docker není dostupný");
    return;
  }

  const groups = data.groups || {};
  if (list.className !== "") list.className = "";
  if (dockerMessage) {
    list.replaceChildren();
    dockerMessage = null;
  }

  let running = 0;
  let groupIndex = 0;
  const usedRows = new Set();
  const usedGroups = new Set();

  Object.keys(groups).forEach(project => {
    const items = (groups[project] || []).filter(c => c.State === "running");
    if (items.length === 0) return;
    running += items.length;
    usedGroups.add(project);

    let g = dockerGroups.get(project);
    if (!g) {
      const title = el("div", "ctr-group-title", project);
      const group = el("div", "ctr-group");
      group.appendChild(title);
      g = { group, title, seen: 1 };
      dockerGroups.set(project, g);
    }
    setProp(g.title, "text", project);
    setProp(g.title, "title", project);
    g.seen = 1;

    items.forEach(c => {
      const key = c.Names || c.ID;
      let r = dockerRows.get(key);
      if (!r) {
        r = dockerRow(key);
        dockerRows.set(key, r);
      }
      usedRows.add(key);

      setProp(r.name, "text", key);
      setProp(r.name, "title", c.Image || "");
      setProp(r.cpu, "text", c.cpu || "—");
      setProp(r.ram, "text", c.memory || "—");
      if (r.action.dataset.name !== key) r.action.dataset.name = key;

      const ports = formatPorts(c.Ports);
      if (ports) {
        if (!r.ports) {
          r.ports = el("span", "ctr-ports");
          r.meta.appendChild(r.ports);
        }
        setProp(r.ports, "text", ports);
        setProp(r.ports, "title", c.Ports);
      } else if (r.ports) {
        r.ports.remove();
        lastValues.delete(r.ports);
        r.ports = null;
      }

      placeAt(g.group, r.row, g.seen++);
    });

    placeAt(list, g.group, groupIndex++);
  });

  dockerRows.forEach((r, key) => {
    if (!usedRows.has(key)) {
      r.row.remove();
      dockerRows.delete(key);
    }
  });
  dockerGroups.forEach((g, project) => {
    if (!usedGroups.has(project)) {
      g.group.remove();
      dockerGroups.delete(project);
    }
  });

  setProp(count, "text", `${running} běží`);
  if (running === 0) showDockerMessage(list, "Žádné běžící kontejnery");
}

// ---- Docker restart ----
async function restartContainer(name, btn) {
  if (!TOKEN) { alert(missingTokenMessage()); return; }
  if (!confirm(`Restartovat kontejner "${name}"?`)) return;
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = "…";
  try {
    const r = await fetch("/action/restart", {
      method: "POST",
      headers: actionHeaders(),
      body: JSON.stringify({ name }),
    });
    const res = await r.json();
    if (r.status === 403) forgetToken();
    else if (!res.ok) alert("Chyba: " + (res.error || "neznámá"));
  } catch (e) {
    alert("Chyba: " + e);
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
    tick();
  }
}

async function killProcess(pid, name, btn) {
  if (!TOKEN) { alert(missingTokenMessage()); return; }
  if (!confirm(`Ukončit "${name}" včetně všech jeho procesů? Posílá se SIGTERM.`)) return;
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = "…";
  try {
    const r = await fetch("/action/kill", {
      method: "POST",
      headers: actionHeaders(),
      body: JSON.stringify({ pid }),
    });
    const res = await r.json();
    if (r.status === 403) forgetToken();
    else if (!res.ok) alert("Chyba: " + (res.error || "neznámá"));
  } catch (e) {
    alert("Chyba: " + e);
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
    tick();
  }
}

async function tick() {
  try {
    const r = await fetch("/stats");
    const d = await r.json();
    setProp(document.getElementById("dot"), "background", "var(--green)");

    // Header - h1 pise `uzivatel@host` jako fastfetch; bez uzivatele jen host
    if (d.host) {
      const machine = (d.user ? d.user + "@" : "") + d.host;
      setProp(document.getElementById("hostname"), "text", machine);
      const title = machine + " — Sysmon";
      if (document.title !== title) document.title = title;
    }
    if (d.system) {
      setProp(document.getElementById("uptime"), "text",
        formatUptime(d.system.uptime_seconds));
    }

    // CPU
    setProp(document.getElementById("cpu"), "text", d.cpu.toFixed(0));
    setBar("cpu-bar", d.cpu);

    // Teplota jde az na konec a bez slova "temp" - staci holé číslo.
    const cpuMeta = [];
    if (d.loadavg) {
      cpuMeta.push(
        `load ${d.loadavg["1m"].toFixed(2)} · ${d.loadavg["5m"].toFixed(2)} · ${d.loadavg["15m"].toFixed(2)}`
      );
    }
    if (d.cpu_temp != null) cpuMeta.push(`${d.cpu_temp.toFixed(0)} °C`);
    setProp(document.getElementById("cpu-meta"), "text", cpuMeta.join(" · "));

    renderCores(d.cpu_cores || []);

    // GPU
    const g = d.gpu;
    const gpuUnit = document.getElementById("gpu-unit");
    const gpuSub = document.getElementById("gpu-sub");
    const gpuOff = gpuSub.firstChild && gpuSub.firstChild.className === "off";
    if (g && g.available) {
      if (gpuOff) {           // zahodit "nedetekováno" a zrusit cache k tomu uzlu
        gpuSub.replaceChildren();
        lastValues.delete(gpuSub);
      }
      setProp(document.getElementById("gpu-label"), "text", "GPU · " + g.vendor);
      setProp(document.getElementById("gpu"), "text",
        (g.util != null ? g.util.toFixed(0) : "–"));
      setProp(gpuUnit, "display", "inline");
      setBar("gpu-bar", g.util || 0);
      const sub = [];
      if (g.mem_used != null && g.mem_total != null)
        sub.push(`${g.mem_used.toFixed(0)} / ${g.mem_total.toFixed(0)} MB`);
      if (g.temp != null) sub.push(`${g.temp.toFixed(0)} °C`);
      setProp(gpuSub, "text", sub.join("  ·  "));
    } else {
      setProp(document.getElementById("gpu"), "text", "—");
      setProp(gpuUnit, "display", "none");
      if (!gpuOff) {
        gpuSub.replaceChildren(el("span", "off", "nedetekováno"));
        lastValues.delete(gpuSub);
      }
      setProp(document.getElementById("gpu-bar"), "width", "0%");
    }

    // RAM + swap
    setProp(document.getElementById("mem"), "text", d.mem.percent.toFixed(0));
    setBar("mem-bar", d.mem.percent);
    setProp(document.getElementById("mem-sub"), "text",
      `${fmt(d.mem.used)} / ${fmt(d.mem.total)}`);
    const swapSub = document.getElementById("swap-sub");
    const danger = !!(d.swap && d.swap.total > 0) && d.swap.percent > 20;
    if (d.swap && d.swap.total > 0) {
      setProp(swapSub, "text",
        `swap  ${fmt(d.swap.used)} / ${fmt(d.swap.total)}  (${d.swap.percent.toFixed(0)}%)`);
    } else {
      setProp(swapSub, "text", "swap  —");
    }
    if (swapSub.classList.contains("danger") !== danger) {
      swapSub.classList.toggle("danger", danger);
    }

    // Battery
    const b = d.battery;
    const batteryCard = document.getElementById("battery-card");
    if (b && b.available && b.percent != null) {
      setProp(batteryCard, "display", "");
      setProp(document.getElementById("battery-percent"), "text", String(b.percent));
      setBar("battery-bar", b.percent);
      setProp(document.getElementById("battery-status"), "text",
        b.status_label || "Stav není dostupný");
      const details = [];
      if (b.ac_online === true) details.push("Připojeno k napájení");
      else if (b.ac_online === false) details.push("Napájení z baterie");
      if (b.time_remaining_minutes != null) {
        const mins = b.time_remaining_minutes;
        details.push(`Zbývá ~${Math.floor(mins / 60)} h ${mins % 60} min`);
      }
      setProp(document.getElementById("battery-power"), "text", details.join(" · "));
      drawBatteryChart(d.battery_history || []);
    } else {
      setProp(batteryCard, "display", "none");
    }

    // Net
    setProp(document.getElementById("net-down"), "text", fmt(d.net.down) + "/s");
    setProp(document.getElementById("net-up"), "text", fmt(d.net.up) + "/s");
    setProp(document.getElementById("net-sub"), "text",
      `celkem  ↓ ${fmt(d.net.total_recv)}  ·  ↑ ${fmt(d.net.total_up)}`);

    // Disk - kapacita a hned vedle teplota NVMe, stejne jako u GPU
    if (d.disk && d.disk.available) {
      setProp(document.getElementById("disk-pct"), "text", d.disk.percent.toFixed(0));
      setBar("disk-bar", d.disk.percent);
      const sub = [`${fmt(d.disk.used)} / ${fmt(d.disk.total)}`];
      const nvme = d.system && d.system.nvme_temp;
      if (nvme != null) sub.push(`${nvme.toFixed(0)} °C`);
      setProp(document.getElementById("disk-sub"), "text", sub.join("  ·  "));
      setProp(document.getElementById("disk-io"), "text",
        `R ${fmt(d.disk.read_rate)}/s  ·  W ${fmt(d.disk.write_rate)}/s`);
    }

    // Listening ports
    if (Array.isArray(d.services)) {
      const items = d.services;
      const onCount = items.filter(s => s.on).length;
      setProp(document.getElementById("svc-count"), "text",
        `${onCount} / ${items.length}`);
      renderServices(items);
    }

    // Top processes
    if (Array.isArray(d.processes)) {
      const nCores = (d.cpu_cores || []).length || 1;
      renderProcesses(d.processes, nCores);
    }

    // Docker (seskupeny podle Compose projektu)
    if (d.containers) renderDocker(d.containers);

  } catch (e) {
    setProp(document.getElementById("dot"), "background", "var(--red)");
  }
}
tick();
setInterval(tick, 1500);

// Uklid pameti. Chromium sbira odpad, jen kdyz ma hlavni vlakno klid - a to
// dashboard, ktery se kazdych 1,5 s aktualizuje, nikdy nema, takze renderer
// roste (~9 MB/min i bez animaci; zmereno v realnem okne). Okno --app proto
// startuje s --js-flags=--expose-gc (viz desktop.py) a tady si o uklid rekneme.
// V prohlizeci window.gc neexistuje, takze se proste nic nedeje.
if (window.gc) setInterval(() => window.gc(), 20000);
