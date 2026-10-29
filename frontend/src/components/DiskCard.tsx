import { memo } from "react";
import { deepEqual } from "../lib/equal";
import { fmt } from "../lib/format";
import type { DiskInfo } from "../types/snapshot";
import { Bar } from "./Bar";

interface DiskCardProps {
  disk: DiskInfo;
  // `nvme_temp` je v `snapshot.system`, ne v `disk` - proto samostatny prop.
  nvmeTemp?: number;
}

export const DiskCard = memo(function DiskCard({ disk, nvmeTemp }: DiskCardProps) {
  if (!disk.available) {
    // Dnesni kod v tomhle pripade nechava "–", prazdny pruh a prazdne suby.
    return (
      <div className="card" id="disk-card">
        <div className="row">
          <span className="label">Disk /</span>
          <span className="val">
            <span id="disk-pct">–</span>
            <span className="unit">%</span>
          </span>
        </div>
        <Bar percent={0} id="disk-bar" />
        <div className="sub" id="disk-sub"></div>
        <div className="sub" id="disk-io"></div>
      </div>
    );
  }

  const percent = disk.percent ?? 0;
  const sub = [`${fmt(disk.used ?? 0)} / ${fmt(disk.total ?? 0)}`];
  if (nvmeTemp != null) sub.push(`${nvmeTemp.toFixed(0)} °C`);

  return (
    <div className="card" id="disk-card">
      <div className="row">
        <span className="label">Disk /</span>
        <span className="val">
          <span id="disk-pct">{percent.toFixed(0)}</span>
          <span className="unit">%</span>
        </span>
      </div>
      <Bar percent={percent} id="disk-bar" />
      <div className="sub" id="disk-sub">
        {sub.join("  ·  ")}
      </div>
      <div className="sub" id="disk-io">
        {`R ${fmt(disk.read_rate ?? 0)}/s  ·  W ${fmt(disk.write_rate ?? 0)}/s`}
      </div>
    </div>
  );
}, deepEqual);
