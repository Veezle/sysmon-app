// Hluboke porovnani JSON-like hodnot (snapshot je cisty JSON bez funkci
// a bez cyklu). Karty ho pouzivaji jako `areEqual` u `memo`: kazdy SSE tik
// prijde s novymi referencemi, takze vychozi melka kontrola by kartu
// prekreslila i kdyz se jeji data nezmenila. Hluboka rovnost necha
// nezmenenou kartu na pokoji a scroll pak nezpomaluje zbytecny prekresl.
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return a === b;
  if (typeof a !== "object") return false;

  const aIsArray = Array.isArray(a);
  if (aIsArray !== Array.isArray(b)) return false;
  if (aIsArray) {
    const aa = a as unknown[];
    const bb = b as unknown[];
    if (aa.length !== bb.length) return false;
    for (let i = 0; i < aa.length; i++) {
      if (!deepEqual(aa[i], bb[i])) return false;
    }
    return true;
  }

  const oa = a as Record<string, unknown>;
  const ob = b as Record<string, unknown>;
  const keysA = Object.keys(oa);
  const keysB = Object.keys(ob);
  if (keysA.length !== keysB.length) return false;
  for (const key of keysA) {
    if (!deepEqual(oa[key], ob[key])) return false;
  }
  return true;
}
