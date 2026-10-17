// Jen pro `npm run typecheck` - aplikace tenhle soubor NEIMPORTUJE, aby se
// fixture nezbundlovala do buildu. Kdyz se zmeni fixture a typy se neupravi,
// spadne typecheck.
import fixture from "../../../tests/fixtures/snapshot.json";
import type {
  BatteryInfo, ContainerInfo, ContainersInfo, DiskInfo, GpuInfo, NetInfo,
  ProcessInfo, ServiceInfo, Snapshot, SystemInfo,
} from "./snapshot";

// `satisfies` je prisnejsi nez `as`: kdyz fixture nema klic, ktery typ
// vyzaduje, nebo ma hodnotu jineho typu, je to chyba prekladu.
export const contractFixture = fixture satisfies Snapshot;

// `satisfies` hlida jen hodnoty, ktere fixture obsahuje. Nazvy volitelnych
// poli tim nepinuje: prejmenovani `util` na `percent` by proslo a UI by
// tise cetlo `undefined`. Proto se klicove nazvy tvrdi pres `keyof`.
type Assert<T extends true> = T;

export type _GpuKeys = Assert<
  "vendor" | "util" | "mem_used" | "mem_total" | "temp" extends keyof GpuInfo
    ? true
    : false
>;
export type _BatteryKeys = Assert<
  | "percent"
  | "status"
  | "status_label"
  | "ac_online"
  | "time_remaining_minutes"
  | "error" extends keyof BatteryInfo
    ? true
    : false
>;
export type _ContainerKeys = Assert<
  | "ID"
  | "Names"
  | "Image"
  | "State"
  | "Status"
  | "Labels"
  | "Ports"
  | "cpu"
  | "memory"
  | "memory_percent" extends keyof ContainerInfo
    ? true
    : false
>;
export type _ContainersKeys = Assert<
  "available" | "error" | "groups" extends keyof ContainersInfo ? true : false
>;
export type _DiskKeys = Assert<
  | "percent"
  | "used"
  | "total"
  | "read_rate"
  | "write_rate" extends keyof DiskInfo
    ? true
    : false
>;
export type _SystemKeys = Assert<
  "kernel" | "uptime_seconds" | "nvme_temp" extends keyof SystemInfo
    ? true
    : false
>;
export type _NetKeys = Assert<
  "up" | "down" | "total_up" | "total_recv" extends keyof NetInfo
    ? true
    : false
>;
export type _ProcessKeys = Assert<
  "pid" | "name" | "cpu" | "mem" extends keyof ProcessInfo ? true : false
>;
export type _ServiceKeys = Assert<
  "port" | "label" | "on" extends keyof ServiceInfo ? true : false
>;
export type _SnapshotKeys = Assert<"cpu_temp" extends keyof Snapshot ? true : false>;

// Fixture ma jen uspesne tvary. Kdyby byla volitelnost jen na papire (napr.
// `vendor: string`), fixture by to neuvolnila - degradovany vzorek to pinuje.
// Presne tyhle tvary vraceji fallbacky z `Monitor.snapshot()`.
const degraded = {
  ...fixture,
  system: {},
  disk: { available: false },
  gpu: { available: false },
  battery: { available: false, error: "Údaje o baterii nejsou dostupné" },
  battery_history: [],
  loadavg: null,
  containers: { available: false, error: "Docker data nejsou k dispozici", groups: {} },
  net: { up: 0.0, down: 0.0, total_up: 0, total_recv: 0 },
  processes: [],
  services: [],
};
export const contractDegraded = degraded satisfies Snapshot;
