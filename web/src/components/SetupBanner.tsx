import { CircleAlert, Download as DownloadIcon } from "lucide-react";
import type { Download, Health } from "../api";
import { formatBytes } from "../conversation";

function Line({ label, dl, hint }: { label: string; dl: Download; hint: string }) {
  if (dl.status === "ready") return null;
  if (dl.status === "error") {
    return (
      <div className="setup__line setup__line--error">
        <CircleAlert size={15} />
        <span>
          {label} indisponible{dl.error ? ` : ${dl.error}` : ""}. {hint}
        </span>
      </div>
    );
  }
  const known = dl.done_bytes !== null && dl.total_bytes !== null && dl.total_bytes > 0;
  const pct = known ? Math.min(100, Math.round((100 * (dl.done_bytes as number)) / (dl.total_bytes as number))) : null;
  return (
    <div className="setup__line">
      <DownloadIcon size={15} />
      <span className="setup__text">
        {dl.status === "downloading"
          ? `Téléchargement : ${label.toLowerCase()}`
          : `Vérification : ${label.toLowerCase()}`}
        {known && ` · ${formatBytes(dl.done_bytes as number)} / ${formatBytes(dl.total_bytes as number)}`}
      </span>
      <span
        className="setup__bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
      >
        <span
          className={`setup__fill ${pct === null ? "is-indeterminate" : ""}`}
          style={pct === null ? undefined : { width: `${pct}%` }}
        />
      </span>
    </div>
  );
}

/**
 * Premier lancement : les archives (~900 Mo) et le modèle d'embeddings (~2,3 Go) se téléchargent une fois.
 * Tant que ce n'est pas fini, on le dit, avec la progression, au lieu de laisser la première question tourner dans le vide.
 */
export function SetupBanner({ health }: { health: Health | null }) {
  if (health === null) {
    return (
      <div className="setup" aria-live="polite">
        <div className="setup__line">
          <span className="setup__text muted">Connexion au serveur local…</span>
        </div>
      </div>
    );
  }
  const pending = [health.index, health.embedder].some((d) => d.status !== "ready");
  if (!pending) return null;
  return (
    <div className="setup" aria-live="polite">
      <Line label="Archives" dl={health.index} hint="Relance avec `uv run agora-index import`." />
      <Line
        label="Modèle d'embeddings (bge-m3)"
        dl={health.embedder}
        hint="Il sera chargé à la première recherche, si possible."
      />
      {health.index.status === "downloading" && (
        <p className="setup__note">Une seule fois : ensuite tout fonctionne hors ligne.</p>
      )}
    </div>
  );
}
