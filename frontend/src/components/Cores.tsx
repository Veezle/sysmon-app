import { memo } from "react";
import { coreColor } from "../lib/format";

// Jadra musi mit stabilni key (index), aby React menil jen text a vysku
// pruhu. Prebuildovani ~90 prvku kazdy tik bylo to, co driv rostlo v pameti.
export const Cores = memo(function Cores({ values }: { values: number[] }) {
  return (
    <div className="cores" id="cores">
      {values.map((v, i) => (
        <div className="core" key={i} title={`Jádro ${i}: ${v.toFixed(0)}%`}>
          <div
            className="cfill"
            style={{ height: `${v}%`, background: coreColor(v) }}
          />
          <span>{v.toFixed(0)}</span>
        </div>
      ))}
    </div>
  );
});
