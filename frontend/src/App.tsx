import { useSnapshot } from "./data/useSnapshot";

export default function App() {
  const { snapshot, live, error } = useSnapshot();
  if (error !== null && snapshot === null) {
    return <main id="dashboard">Chyba: {error}</main>;
  }
  if (snapshot === null) {
    return <main id="dashboard">Načítání…</main>;
  }
  return (
    <main id="dashboard">
      <p id="hostname">{snapshot.host}</p>
      <p id="cpu">{snapshot.cpu.toFixed(0)}</p>
      <p id="live">{live ? "SSE" : "poll"}</p>
    </main>
  );
}
