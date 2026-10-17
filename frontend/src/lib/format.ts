// Formatovaci helpery prenesene z `../sysmon/static/app.js` beze zmeny
// chovani (formatUptime, formatPorts, fmt). Jsou to ciste funkce bez stavu,
// takze se daji testovat i pouzit mimo React.

// Uptime jako "5d 3h" / "3h 12m" / "42m". Ne-konecne cislo (vcetne
// `undefined`, protoze `system.uptime_seconds` je volitelne) je "–".
export function formatUptime(sec: number | undefined): string {
  if (sec === undefined || !Number.isFinite(sec)) return "–";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// Docker vraci `Ports` jako STRING, napr. "0.0.0.0:80->80/tcp, :::443->443/tcp".
// Vystup je "80/tcp  443/tcp": kdyz je host i kontejnerovy port stejny, sipka
// se vynecha; jinak "8080→80/tcp". Duplicity se zahodi.
export function formatPorts(raw?: string): string {
  if (!raw) return "";
  const seen = new Set<string>();
  const out: string[] = [];
  raw.split(",").forEach((p) => {
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
}

// Bajty v base-1024 s jednim desetinnym mistem: 1536 -> "1.5 KB".
export function fmt(bytes: number): string {
  let b = bytes;
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) {
    b /= 1024;
    i++;
  }
  return b.toFixed(1) + " " + u[i];
}
