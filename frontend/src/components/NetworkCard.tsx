import { memo } from "react";
import { fmt } from "../lib/format";
import type { NetInfo } from "../types/snapshot";

export const NetworkCard = memo(function NetworkCard({ net }: { net: NetInfo }) {
  return (
    <div className="card" id="network-card">
      <div className="row">
        <span className="label">Net Down</span>
        <span className="val" id="net-down">
          {fmt(net.down)}/s
        </span>
      </div>
      <div className="row" style={{ marginBottom: "6px" }}>
        <span className="label">Net Up</span>
        <span className="val" id="net-up">
          {fmt(net.up)}/s
        </span>
      </div>
      <div className="sub" id="net-sub">
        {`celkem  ↓ ${fmt(net.total_recv)}  ·  ↑ ${fmt(net.total_up)}`}
      </div>
    </div>
  );
});
