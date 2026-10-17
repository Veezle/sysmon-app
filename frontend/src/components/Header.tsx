import { memo } from "react";
import { describeError, formatUptime } from "../lib/format";

interface HeaderProps {
  host: string;
  user: string;
  uptimeSeconds: number | undefined;
  live: boolean;
  error: string | null;
}

export const Header = memo(function Header({
  host,
  user,
  uptimeSeconds,
  live,
  error,
}: HeaderProps) {
  // Hlavicka pise `uzivatel@host` jako fastfetch; bez uzivatele jen host.
  const machine = host ? (user ? user + "@" : "") + host : "–";
  // Stale/chybovy stav nese barva tecky, text zustava "Online".
  const dotColor =
    error !== null ? "var(--red)" : live ? "var(--green)" : "var(--amber)";
  return (
    <header className="topbar">
      <div className="brand">
        <h1 id="hostname">{machine}</h1>
        <div className="hostline">
          <span>
            UP <b id="uptime">{formatUptime(uptimeSeconds)}</b>
          </span>
          {error !== null && (
            <span>poslední známá data · {describeError(error)}</span>
          )}
        </div>
      </div>
      <div className="system-status">
        <span className="dot" id="dot" style={{ background: dotColor }} />
        <span>Online</span>
      </div>
    </header>
  );
});
