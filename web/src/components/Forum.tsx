import { ArrowRight, ChevronDown } from "lucide-react";
import type { ContextInfo, Health } from "../api";
import { ContextIcon } from "./ContextIcon";
import { Mascot } from "./Mascot";
import { SetupBanner } from "./SetupBanner";
import type { Settings } from "./Welcome";

/** Choix de l'agent : un contexte = une base indexée + son serveur MCP. */
export function Forum(props: {
  contexts: ContextInfo[] | null;
  settings: Settings;
  health: Health | null;
  onEnter: (id: string) => void;
  onChangeModel: () => void;
}) {
  return (
    <div className="page">
      <header className="topbar">
        <span className="brand">
          <Mascot size={24} />
          Agora
        </span>
        <button type="button" className="btn btn--ghost btn--sm" onClick={props.onChangeModel}>
          {props.settings.model}
          <ChevronDown size={14} />
        </button>
      </header>

      <main className="forum">
        <h1>Avec qui veux-tu parler ?</h1>
        <SetupBanner health={props.health} />
        <div className="agents">
          {props.contexts === null && <p className="muted">Chargement…</p>}
          {props.contexts?.map((c) => (
            <button
              key={c.id}
              type="button"
              className="agent"
              data-context={c.theme}
              onClick={() => props.onEnter(c.id)}
            >
              <ContextIcon emblem={c.emblem} size={40} />
              <span className="agent__text">
                <span className="agent__name">{c.place}</span>
                <span className="agent__desc">{c.tagline}</span>
                {c.coverage && <span className="agent__coverage">{c.coverage}</span>}
              </span>
              <ArrowRight className="agent__go" size={18} />
            </button>
          ))}
        </div>
      </main>
    </div>
  );
}
