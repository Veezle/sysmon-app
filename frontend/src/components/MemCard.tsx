import { memo } from "react";
import { deepEqual } from "../lib/equal";
import { fmt } from "../lib/format";
import type { MemInfo, SwapInfo } from "../types/snapshot";
import { Bar } from "./Bar";

interface MemCardProps {
  mem: MemInfo;
  swap: SwapInfo;
}

export const MemCard = memo(function MemCard({ mem, swap }: MemCardProps) {
  const danger = swap.total > 0 && swap.percent > 20;
  return (
    <div className="card" id="mem-card">
      <div className="row">
        <span className="label">RAM</span>
        <span className="val">
          <span id="mem">{mem.percent.toFixed(0)}</span>
          <span className="unit">%</span>
        </span>
      </div>
      <Bar percent={mem.percent} id="mem-bar" />
      <div className="sub" id="mem-sub">
        {fmt(mem.used)} / {fmt(mem.total)}
      </div>
      <div className={danger ? "sub danger" : "sub"} id="swap-sub">
        {swap.total > 0
          ? `swap  ${fmt(swap.used)} / ${fmt(swap.total)}  (${swap.percent.toFixed(0)}%)`
          : "swap  —"}
      </div>
    </div>
  );
}, deepEqual);
