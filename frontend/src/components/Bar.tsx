import { memo } from "react";
import { deepEqual } from "../lib/equal";
import { coreColor } from "../lib/format";

// Pruh se nemeni prestavbou, jen se posune hodnota - proto `width` menime
// pres style a nic neanimujeme (dnesni CSS to dodrzuje). Barvu meni prah,
// stejne jako u jader (`coreColor`).
export const Bar = memo(function Bar(props: { percent: number; id?: string }) {
  return (
    <div className="bar">
      <div
        className="fill"
        id={props.id}
        style={{ width: `${props.percent}%`, background: coreColor(props.percent) }}
      />
    </div>
  );
}, deepEqual);
