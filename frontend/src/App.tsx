import { BatteryCard } from "./components/BatteryCard";
import { CpuCard } from "./components/CpuCard";
import { DiskCard } from "./components/DiskCard";
import { GpuCard } from "./components/GpuCard";
import { Header } from "./components/Header";
import { MemCard } from "./components/MemCard";
import { NetworkCard } from "./components/NetworkCard";
import { useSnapshot } from "./data/useSnapshot";
import { describeError } from "./lib/format";

export default function App() {
  const { snapshot, live, error } = useSnapshot();
  // Bez snapshotu nema dashboard co kreslit; text roztahneme pres celou
  // mrizku, aby nevisel v prvnim sloupci.
  if (error !== null && snapshot === null) {
    return (
      <main id="dashboard" style={{ gridColumn: "1 / -1" }}>
        {describeError(error)}
      </main>
    );
  }
  if (snapshot === null) {
    return (
      <main id="dashboard" style={{ gridColumn: "1 / -1" }}>
        Načítání…
      </main>
    );
  }
  // Fragment, ne <main>: body je dvanactisloupcova mrizka a karty musi byt
  // jejimi primymi potomky (viz `display: contents` na #root v main.tsx).
  return (
    <>
      <Header
        host={snapshot.host}
        user={snapshot.user}
        uptimeSeconds={snapshot.system.uptime_seconds}
        live={live}
        error={error}
      />
      <CpuCard
        cpu={snapshot.cpu}
        cores={snapshot.cpu_cores}
        cpuTemp={snapshot.cpu_temp}
        loadavg={snapshot.loadavg}
      />
      <GpuCard gpu={snapshot.gpu} />
      <MemCard mem={snapshot.mem} swap={snapshot.swap} />
      <BatteryCard battery={snapshot.battery} history={snapshot.battery_history} />
      <NetworkCard net={snapshot.net} />
      <DiskCard disk={snapshot.disk} nvmeTemp={snapshot.system.nvme_temp} />
    </>
  );
}
