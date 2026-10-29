import { memo } from "react";
import { deepEqual } from "../lib/equal";
import type { GpuInfo } from "../types/snapshot";
import { Bar } from "./Bar";

// `gpu.error` neexistuje - kolektor vraci jen `{available: false}`, takze
// nedostupny stav je "nedetekováno" stejne jako v dnesnim `app.js`.
export const GpuCard = memo(function GpuCard({ gpu }: { gpu: GpuInfo }) {
  const sub: string[] = [];
  if (gpu.available) {
    if (gpu.mem_used != null && gpu.mem_total != null) {
      sub.push(`${gpu.mem_used.toFixed(0)} / ${gpu.mem_total.toFixed(0)} MB`);
    }
    if (gpu.temp != null) sub.push(`${gpu.temp.toFixed(0)} °C`);
  }
  return (
    <div className="card" id="gpu-card">
      <div className="row">
        <span className="label" id="gpu-label">
          {gpu.available ? "GPU · " + gpu.vendor : "GPU Device"}
        </span>
        <span className="val">
          <span id="gpu">
            {gpu.available ? (gpu.util != null ? gpu.util.toFixed(0) : "–") : "—"}
          </span>
          <span
            className="unit"
            id="gpu-unit"
            style={{ display: gpu.available ? "inline" : "none" }}
          >
            %
          </span>
        </span>
      </div>
      <Bar percent={gpu.available ? gpu.util ?? 0 : 0} id="gpu-bar" />
      <div className="sub" id="gpu-sub">
        {gpu.available ? sub.join("  ·  ") : <span className="off">nedetekováno</span>}
      </div>
    </div>
  );
}, deepEqual);
