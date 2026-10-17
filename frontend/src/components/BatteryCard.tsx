import { memo } from "react";
import type { BatteryInfo, BatterySample } from "../types/snapshot";
import { Bar } from "./Bar";
import { BatteryChart } from "./BatteryChart";

interface BatteryCardProps {
  battery: BatteryInfo;
  history: BatterySample[];
}

// Nedostupna baterie (nebo baterie bez `capacity`) kartu vubec nevykresli -
// presne dnešní `batteryCard.style.display = "none"`.
export const BatteryCard = memo(function BatteryCard({
  battery,
  history,
}: BatteryCardProps) {
  if (!battery.available || battery.percent == null) return null;

  const details: string[] = [];
  if (battery.ac_online === true) details.push("Připojeno k napájení");
  else if (battery.ac_online === false) details.push("Napájení z baterie");
  if (battery.time_remaining_minutes != null) {
    const mins = battery.time_remaining_minutes;
    details.push(`Zbývá ~${Math.floor(mins / 60)} h ${mins % 60} min`);
  }

  // Wrap zustava v DOM i skryty (jako dnes); meni se jen `display`.
  return (
    <div className="card" id="battery-card">
      <div className="row">
        <span className="label">Battery</span>
        <span className="val">
          <span id="battery-percent">{String(battery.percent)}</span>
          <span className="unit">%</span>
        </span>
      </div>
      <Bar percent={battery.percent} id="battery-bar" />
      <div className="sub" id="battery-status">
        {battery.status_label || "Stav není dostupný"}
      </div>
      <div className="sub" id="battery-power">
        {details.join(" · ")}
      </div>
      <div
        className="battery-chart-wrap"
        id="battery-chart-wrap"
        style={{ display: history.length < 2 ? "none" : "block" }}
      >
        <div className="battery-chart-label">Posledních 24 h</div>
        <BatteryChart history={history} />
      </div>
    </div>
  );
});
