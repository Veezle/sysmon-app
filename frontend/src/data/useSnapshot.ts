import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "../types/snapshot";

// TICK_SEC z Pythonu (config.py) je 1,5 s. Frontend ho potrebuje pro dve veci
// a Python ho nesdeli, takze se hodnota duplikuje VEDOME: kdyby se tik zmenil,
// je to druhe misto k uprave.
export const POLL_MS = 1500; // perioda pollingu, kdyz proud mrtvi
export const STALE_MS = 4500; // ~3 tiky ticha = proud zamrzl

export interface SnapshotState {
  snapshot: Snapshot | null;
  live: boolean;
  error: string | null;
}

export function useSnapshot(): SnapshotState {
  const [state, setState] = useState<SnapshotState>({
    snapshot: null,
    live: true,
    error: null,
  });
  // Cas posledniho SSE ramce. Polling ho NEMENI - jinak by se dalsi poll
  // odlozil o STALE_MS a cadence by byla spatna. Cas je monotonni
  // (performance.now): posun systemovych hodin zpet nesmi fallback vypnout.
  const lastFrame = useRef(0);
  // Poradi uz aplikovanych dat; chrani proti starsi odpovedi, ktera dojde
  // pozdeji nez novy SSE ramec nebo novy poll.
  const appliedSeq = useRef(0);
  const requestSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    // Pri mountu bereme cas za "ziva data": prvni /stats dorazi hned a do
    // STALE_MS se nema pollovat.
    lastFrame.current = performance.now();

    const take = (data: Snapshot, live: boolean) => {
      if (cancelled) return;
      setState({ snapshot: data, live, error: null });
    };

    const fetchStats = () => {
      const started = performance.now();
      const seq = ++requestSeq.current;
      fetch("/stats")
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((data: Snapshot) => {
          // Pozdejsi SSE ramec ma prednost; stare /stats ho nesmi prepsat.
          if (cancelled || lastFrame.current > started) return;
          // A ani dve /stats odpovedi nesmi dojit v opacnem poradi.
          if (seq < appliedSeq.current) return;
          appliedSeq.current = seq;
          take(data, false);
        })
        .catch((e: unknown) => {
          if (!cancelled) setState((s) => ({ ...s, error: String(e) }));
        });
    };

    fetchStats();

    const source = new EventSource("/events");
    source.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as Snapshot;
        // Jedine misto, ktere posouva lastFrame: zivy ramec znamena, ze proud
        // bezi, takze polling nema co delat.
        lastFrame.current = performance.now();
        appliedSeq.current = ++requestSeq.current;
        take(data, true);
      } catch {
        // poskozeny ramec se zahodi; posledni dobry snapshot zustava
      }
    };

    const timer = window.setInterval(() => {
      if (performance.now() - lastFrame.current < STALE_MS) return;
      // Stav se preklopi driv, nez poll vubec dobehne: kdyz proud umlkl, je
      // live false i tehdy, kdyz /stats prave vraci 500. Uspech pollu ho
      // potvrdi, pozdejsi SSE ramec zase prepne na true.
      setState((s) => (s.live ? { ...s, live: false } : s));
      fetchStats();
    }, POLL_MS);

    return () => {
      cancelled = true;
      source.close();
      window.clearInterval(timer);
    };
  }, []);

  return state;
}
