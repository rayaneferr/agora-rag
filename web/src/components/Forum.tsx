import type { ContextInfo } from "../api";
import type { Settings } from "./Welcome";
import { Emblem } from "./Emblem";
import { Mascot } from "./Mascot";

const fmt = (n: number) => n.toLocaleString("fr-FR");

/** Le forum de l'Agora : chaque contexte est un portail, déjà habillé de son propre thème. */
export function Forum(props: {
  contexts: ContextInfo[] | null;
  settings: Settings;
  onEnter: (id: string) => void;
  onChangeModel: () => void;
}) {
  return (
    <div className="forum">
      <div className="frieze" aria-hidden />
      <header className="forum__head">
        <div className="brand">
          <Mascot size={40} />
          <span className="brand__name">Agora</span>
        </div>
        <button type="button" className="ghost small" onClick={props.onChangeModel}>
          {props.settings.model} · changer
        </button>
      </header>

      <main className="forum__inner">
        <p className="eyebrow">Le forum</p>
        <h1 className="forum__title">Choisis ton guide</h1>
        <p className="muted forum__lede">Chaque guide a son lieu, ses archives et ses outils. Il ne parle que de ce qu'il connaît.</p>

        <div className="portals">
          {props.contexts === null && <p className="muted">Ouverture des portes…</p>}
          {props.contexts?.map((c) => (
            <button key={c.id} type="button" className="portal" data-theme={c.theme} onClick={() => props.onEnter(c.id)}>
              <span className="portal__decor" aria-hidden />
              <span className="portal__emblem">
                <Emblem name={c.emblem} size={72} />
              </span>
              <span className="portal__place">{c.place}</span>
              <span className="portal__agent">
                avec <strong>{c.agent}</strong>
              </span>
              <span className="portal__tagline">{c.tagline}</span>
              <span className="portal__desc">{c.description}</span>
              <span className="portal__meta">
                <span>{c.corpus_label}</span>
                <span>{fmt(c.points)} extraits indexés</span>
                <span>{c.tools.length} outils MCP</span>
              </span>
              <span className="portal__cta">Entrer →</span>
            </button>
          ))}
        </div>
      </main>
    </div>
  );
}
