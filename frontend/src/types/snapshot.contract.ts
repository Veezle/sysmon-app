// Jen pro `npm run typecheck` - aplikace tenhle soubor NEIMPORTUJE, aby se
// fixture nezbundlovala do buildu. Kdyz Python zmeni kontrakt a typy se
// neupravi, spadne typecheck.
import fixture from "../../../tests/fixtures/snapshot.json";
import type { Snapshot } from "./snapshot";

// `satisfies` je prisnejsi nez `as`: kdyz fixture nema klic, ktery typ
// vyzaduje, nebo ma hodnotu jineho typu, je to chyba prekladu.
export const contractFixture = fixture satisfies Snapshot;
