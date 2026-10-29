import { memo } from "react";
import { deepEqual } from "../lib/equal";
import { coreColor, fmt } from "../lib/format";
import type { ProcessInfo } from "../types/snapshot";

interface ProcessesCardProps {
  processes: ProcessInfo[];
  // Pocet jader je potreba pro podil CPU; snapshot ho posila v `cpu_cores`.
  coreCount: number;
}

export const ProcessesCard = memo(function ProcessesCard({
  processes,
  coreCount,
}: ProcessesCardProps) {
  const nCores = coreCount || 1;

  return (
    <div className="card" id="proc-card">
      <div className="row">
        <span className="label">Top Processes</span>
        <span className="val svc" id="proc-count">
          top 5
        </span>
      </div>
      <div id="proc-list">
        {processes.map((p) => {
          // CPU je podil z jednoho jadra; proti poctu jader se prevede na
          // podil z celeho stroje (stejne jako `renderProcesses` v app.js).
          const share = p.cpu / nCores;
          return (
            <div className="proc-row" key={p.pid}>
              <span className="proc-name" title={`PID ${p.pid} · ${p.name}`}>
                {p.name}
              </span>
              <span className="proc-cpu" style={{ color: coreColor(share) }}>
                {share.toFixed(1)}%
              </span>
              <span className="proc-mem">{fmt(p.mem)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}, deepEqual);
