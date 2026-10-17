// Kontrakt snapshotu - to, co `Monitor.snapshot()` posila na /stats i do SSE.
// Tvary vychazeji z kolektoru (`sysmon_app/collectors/*.py`), ne z nazvu
// klicu: kde kolektor pada zpatky na degradovany tvar, je pole volitelne.
// Klicovou sadu pinuje Python test v `tests/`, tvary tenhle soubor pres
// kontrolni soubor v tomto adresari a fixture.

export type CoreLoad = number;

export interface MemInfo {
  percent: number;
  used: number;
  total: number;
}

export interface SwapInfo {
  percent: number;
  used: number;
  total: number;
}

export interface LoadAvg {
  "1m": number;
  "5m": number;
  "15m": number;
}

// `disk.py` vraci pri chybe `disk_usage` jen `{available: false}`, takze
// ostatni pole existuji jen v uspesne vetvi.
export interface DiskInfo {
  available: boolean;
  percent?: number;
  used?: number;
  total?: number;
  read_rate?: number;
  write_rate?: number;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu: number;
  mem: number;
}

// `Monitor` pada na `{}` (stejne jako pri vyjimce `get_system_info()`) a
// `nvme_temp` je jen na strojich, ktere ho umi precist - proto jsou vsechna
// pole volitelna.
export interface SystemInfo {
  kernel?: string;
  uptime_seconds?: number;
  nvme_temp?: number;
}

// Fallback je `{available: false}`; `error` kolektor nikdy nevraci.
export interface GpuInfo {
  available: boolean;
  vendor?: string;
  util?: number;
  mem_used?: number;
  mem_total?: number;
  temp?: number;
}

export interface BatterySample {
  t: number;
  v: number;
}

export interface BatteryInfo {
  available: boolean;
  percent?: number | null;
  status?: string;
  status_label?: string;
  ac_online?: boolean | null;
  time_remaining_minutes?: number | null;
  error?: string;
}

export interface NetInfo {
  up: number;
  down: number;
  total_up: number;
  total_recv: number;
}

export interface ServiceInfo {
  port: number;
  label: string;
  on: boolean;
}

// Podmnozina poli z `docker ps --format '{{json .}}'`, ktera UI pouziva, plus
// statistiky z `docker stats`. Hodnoty jsou prevazne retezce (`Platform` je
// ale objekt), a vsechna pole mohou chybet.
export interface ContainerInfo {
  ID?: string;
  Names?: string;
  Image?: string;
  State?: string;
  Status?: string;
  Labels?: string;
  Ports?: string;
  cpu?: string;
  memory?: string;
  memory_percent?: string;
}

// `groups` je objekt klicovany nazvem Compose projektu, hodnoty jsou pole
// kontejneru - ne pole skupin.
export interface ContainersInfo {
  available: boolean;
  error: string | null;
  groups: Record<string, ContainerInfo[]>;
}

export interface Snapshot {
  host: string;
  user: string;
  cpu: number;
  cpu_cores: CoreLoad[];
  cpu_temp?: number;
  mem: MemInfo;
  swap: SwapInfo;
  loadavg: LoadAvg | null;
  disk: DiskInfo;
  processes: ProcessInfo[];
  system: SystemInfo;
  gpu: GpuInfo;
  battery: BatteryInfo;
  battery_history: BatterySample[];
  net: NetInfo;
  services: ServiceInfo[];
  containers: ContainersInfo;
}
