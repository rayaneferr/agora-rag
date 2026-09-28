import { useEffect, useRef } from "react";
import type { LogEntry } from "../conversation";

const time = (at: number) => new Date(at).toLocaleTimeString("fr-FR", { hour12: false });

export function LogPanel({ logs, onClose, onClear }: { logs: LogEntry[]; onClose: () => void; onClear: () => void }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Accolades nécessaires : scrollIntoView renvoie une Promise dans les Chrome récents,
    // que React prendrait pour une fonction de nettoyage.
    end.current?.scrollIntoView({ block: "end" });
  }, [logs.length]);
  return (
    <aside className="logs" aria-label="Journal technique">
      <header className="logs__head">
        <strong>Journal</strong>
        <span className="muted">{logs.length} événements</span>
        <button type="button" className="ghost small" onClick={onClear}>
          Vider
        </button>
        <button type="button" className="ghost small" onClick={onClose} aria-label="Fermer">
          ✕
        </button>
      </header>
      <div className="logs__list">
        {logs.length === 0 && <p className="muted">Les appels au modèle et aux outils MCP s'afficheront ici.</p>}
        {logs.map((l, i) => (
          <div key={i} className={`log log--${l.level}`}>
            <span className="log__time">{time(l.at)}</span>
            <span className="log__text">{l.text}</span>
            {l.detail && <code className="log__detail">{l.detail}</code>}
          </div>
        ))}
        <div ref={end} />
      </div>
    </aside>
  );
}
