import { memo } from "react";
import { deepEqual } from "../lib/equal";
import type { LoadAvg } from "../types/snapshot";
import { Bar } from "./Bar";
import { Cores } from "./Cores";

interface CpuCardProps {
  cpu: number;
  cores: number[];
  cpuTemp?: number;
  loadavg: LoadAvg | null;
}

export const CpuCard = memo(function CpuCard({
  cpu,
  cores,
  cpuTemp,
  loadavg,
}: CpuCardProps) {
  // Teplota jde az na konec a bez slova "temp" - staci hole cislo.
  const meta: string[] = [];
  if (loadavg) {
    meta.push(
      `load ${loadavg["1m"].toFixed(2)} · ${loadavg["5m"].toFixed(2)} · ${loadavg["15m"].toFixed(2)}`
    );
  }
  if (cpuTemp != null) meta.push(`${cpuTemp.toFixed(0)} °C`);
  return (
    <div className="card" id="cpu-card">
      <div className="row">
        <span className="label">CPU Load</span>
        <span className="val">
          <span id="cpu">{cpu.toFixed(0)}</span>
          <span className="unit">%</span>
        </span>
      </div>
      <Bar percent={cpu} id="cpu-bar" />
      <div className="sub" id="cpu-meta">{meta.join(" · ")}</div>
      <Cores values={cores} />
    </div>
  );
}, deepEqual);
