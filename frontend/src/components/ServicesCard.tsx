import { memo } from "react";
import type { ServiceInfo } from "../types/snapshot";

// Prazdny seznam neni "vsechno je dole", ale "nic se nesleduje": kdyz uzivatel
// nema ve watch_ports ani jeden port, vraci get_services prazdny seznam a karta
// s "0 / 0" by lhala o vypadku. Port znamena "nesleduji ho", ne "nebezi".
export const ServicesCard = memo(function ServicesCard({
  services,
}: {
  services: ServiceInfo[];
}) {
  const empty = services.length === 0;
  const on = services.filter((s) => s.on).length;

  return (
    <div className="card" id="services-card">
      <div className="row">
        <span className="label">Listening Ports</span>
        <span className="val svc" id="svc-count">
          {empty ? "—" : `${on} / ${services.length}`}
        </span>
      </div>
      <div id="services-list">
        {empty ? (
          <div className="off">
            Nesleduji žádné porty — nastav [watch_ports] v config.toml
          </div>
        ) : (
          // Poradi ridi server (bezi prvni, pak offline, uvnitr podle portu);
          // tady se nese radi.
          services.map((s) => (
            <div className={s.on ? "svc-row on" : "svc-row"} key={s.port}>
              <span className="svc-dot" />
              <span className="svc-port">{s.port}</span>
              <span className="svc-label">{s.label || ""}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
});
