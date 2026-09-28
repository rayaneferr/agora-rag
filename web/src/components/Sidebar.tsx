import type { Health } from "../api";
import { THEMES } from "../themes";
import { Mascot } from "./Mascot";
import type { Settings } from "./Onboarding";

const fmt = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("fr-FR"));

export function Sidebar(props: {
  settings: Settings;
  health: Health | null;
  theme: string;
  open: boolean;
  onTheme: (id: string) => void;
  onModel: (id: string) => void;
  onNewChat: () => void;
  onChangeKey: () => void;
  onClose: () => void;
}) {
  const { settings, health, theme } = props;
  const idx = health?.index;
  return (
    <aside className={`sidebar ${props.open ? "sidebar--open" : ""}`}>
      <div className="brand">
        <Mascot size={36} />
        <div>
          <div className="brand__name">Agora</div>
          <div className="brand__tag">Cinéma &amp; Assemblée</div>
        </div>
        <button type="button" className="ghost small sidebar__close" onClick={props.onClose} aria-label="Fermer le menu">
          ✕
        </button>
      </div>

      <button type="button" className="primary wide" onClick={props.onNewChat}>
        + Nouvelle conversation
      </button>

      <section className="panel">
        <h3>Modèle</h3>
        <select value={settings.model} onChange={(e) => props.onModel(e.target.value)}>
          {settings.models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        <button type="button" className="link" onClick={props.onChangeKey}>
          Changer de fournisseur ou de clé
        </button>
      </section>

      <section className="panel">
        <h3>Bases indexées</h3>
        {idx?.status === "downloading" && <p className="hint">Téléchargement de l'index…</p>}
        {idx?.status === "error" && <p className="hint error">Index indisponible : {idx.error}</p>}
        <ul className="corpus">
          <li>
            <span className="dot dot--films" /> Films <span className="muted">{fmt(idx?.points.films)} extraits</span>
          </li>
          <li>
            <span className="dot dot--debats" /> Débats AN <span className="muted">{fmt(idx?.points.debats)} extraits</span>
          </li>
        </ul>
        <p className="hint">{health ? `${health.tools.length} outils MCP connectés` : "Connexion au serveur…"}</p>
      </section>

      <section className="panel">
        <h3>Ambiance</h3>
        <div className="themes">
          {THEMES.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`theme ${theme === t.id ? "theme--active" : ""}`}
              onClick={() => props.onTheme(t.id)}
              title={t.mood}
            >
              <span className="theme__swatches">
                {t.swatches.map((c) => (
                  <i key={c} style={{ background: c }} />
                ))}
              </span>
              <span className="theme__name">{t.name}</span>
            </button>
          ))}
        </div>
        <p className="hint">{THEMES.find((t) => t.id === theme)?.mood}</p>
      </section>

      <footer className="sidebar__foot muted">
        Données : Wikipédia (CC BY-SA) · Assemblée nationale (Licence Ouverte)
      </footer>
    </aside>
  );
}
