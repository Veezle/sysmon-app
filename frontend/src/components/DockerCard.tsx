import { memo } from "react";
import { formatPorts } from "../lib/format";
import type { ContainerInfo, ContainersInfo } from "../types/snapshot";

// Server posila skupiny uz serazene (abecedne, "Ostatní" posledni). Presto se
// "Ostatní" na konci vynuti: JS radi celociselne klice objektu dopredu, takze
// na poradi `Object.keys` se u skupin s ciselnym nazvem neda spolehat.
const OTHER_PROJECT = "Ostatní";

function DockerRow({ container }: { container: ContainerInfo }) {
  const name = container.Names || container.ID || "";
  const ports = formatPorts(container.Ports);
  return (
    <div className="ctr-row">
      <span className="ctr-dot" />
      <div className="ctr-meta">
        <span className="ctr-name" title={container.Image || ""}>
          {name}
        </span>
        {ports !== "" && (
          <span className="ctr-ports" title={container.Ports}>
            {ports}
          </span>
        )}
      </div>
      <span className="ctr-metrics">
        CPU <b>{container.cpu || "—"}</b> · RAM <b>{container.memory || "—"}</b>
      </span>
    </div>
  );
}

export const DockerCard = memo(function DockerCard({
  containers,
}: {
  containers: ContainersInfo;
}) {
  if (!containers.available) {
    return (
      <div className="card" id="docker-card">
        <div className="row">
          <span className="label">Docker Containers</span>
          <span className="val svc" id="docker-count">
            N/A
          </span>
        </div>
        <div id="docker-containers" className="off">
          {containers.error || "Docker není dostupný"}
        </div>
      </div>
    );
  }

  const groups = containers.groups;
  // Skupina bez beziciho kontejneru se nevykresluje vubec.
  const projects = Object.keys(groups).filter(
    (project) => (groups[project] || []).some((c) => c.State === "running")
  );
  const otherIndex = projects.indexOf(OTHER_PROJECT);
  if (otherIndex !== -1) {
    projects.splice(otherIndex, 1);
    projects.push(OTHER_PROJECT);
  }

  const running = projects.reduce(
    (sum, project) =>
      sum + (groups[project] || []).filter((c) => c.State === "running").length,
    0
  );

  return (
    <div className="card" id="docker-card">
      <div className="row">
        <span className="label">Docker Containers</span>
        <span className="val svc" id="docker-count">
          {`${running} běží`}
        </span>
      </div>
      <div id="docker-containers" className="">
        {running === 0 ? (
          "Žádné běžící kontejnery"
        ) : (
          projects.map((project) => (
            <div className="ctr-group" key={project}>
              <div className="ctr-group-title" title={project}>
                {project}
              </div>
              {(groups[project] || [])
                .filter((c) => c.State === "running")
                .map((c) => (
                  <DockerRow
                    key={`${project}::${c.Names || c.ID || ""}`}
                    container={c}
                  />
                ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
});
