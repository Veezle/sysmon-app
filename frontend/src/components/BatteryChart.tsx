import { memo, useEffect, useRef } from "react";
import type { BatterySample } from "../types/snapshot";

// Kresleni je imperativni schvalne: pri 1,5s tiku by graf z React elementu
// znamenal prvek na kazdy bod historie. Canvas je mimo React render - meni se
// jen jeho obsah, a to pouze kdyz se zmeni historie.
export const BatteryChart = memo(function BatteryChart({
  history,
}: {
  history: BatterySample[];
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  // Klic posledniho nakresleneho obrazu. Drzi se v refu, ne v modulu: ref
  // neprezije remount, takze nezustane zastaraly klic z jine instance.
  const chartKey = useRef<string | null>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (canvas === null) return;
    drawBatteryChart(canvas, history, chartKey);
  }, [history]);
  return <canvas className="battery-chart" id="battery-chart" ref={ref} />;
});

// Port `drawBatteryChart` z `../sysmon/static/app.js` vcetne `devicePixelRatio`.
// Barvy jsou napevno (zadny `getComputedStyle`) - stejne jako dnes.
function drawBatteryChart(
  canvas: HTMLCanvasElement,
  data: BatterySample[],
  chartKey: { current: string | null },
): void {
  if (data.length < 2) return;

  // Skryty wrap (display:none) ma nulovou velikost - kresleni se preskoci
  // jeste pred zmenou klice, stejne jako v `app.js`.
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  // Prekresluje se jen kdyz se zmenila data nebo velikost platna - jinak by se
  // kazdych 1,5 s zbytecne prekresloval stejny obrazek. Podpis vsech hodnot
  // je v klici proto, ze backend posila `t` relativni k prvnimu vzorku: po
  // naplneni 24h historie zustava `length` i posledni `t` stejne a meni se
  // jen `v` - bez podpisu by graf zamrzl.
  const lastPoint = data[data.length - 1];
  let sig = 0;
  for (const p of data) sig = (Math.imul(sig, 31) + p.v) | 0;
  const key =
    data.length +
    "|" +
    lastPoint.t +
    "|" +
    sig +
    "|" +
    Math.round(rect.width) +
    "x" +
    Math.round(rect.height);
  if (key === chartKey.current) return;
  chartKey.current = key;

  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  ctx.clearRect(0, 0, w, h);

  // Grid lines at 25/50/75%
  ctx.strokeStyle = "rgba(203,213,225,.5)";
  ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach((f) => {
    const y = h - f * h;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  });

  const maxT = data[data.length - 1].t || 1;
  const xFor = (t: number) => (t / maxT) * w;
  const yFor = (v: number) => h - (v / 100) * h;

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
