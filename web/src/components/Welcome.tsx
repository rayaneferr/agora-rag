import { useEffect, useState } from "react";
import { getModels, getProviders, type Model, type Provider } from "../api";
import { Mascot } from "./Mascot";

export interface Settings {
  provider: string;
  model: string;
  models: Model[];
}

/** Écran d'entrée de l'Agora : quel modèle local fera parler les guides ? */
export function Welcome({ initial, onReady }: { initial: Settings | null; onReady: (s: Settings) => void }) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState(initial?.provider ?? "ollama");
  const [models, setModels] = useState<Model[]>(initial?.models ?? []);
  const [model, setModel] = useState(initial?.model ?? "");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProviders().then(setProviders).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setError(null);
    getModels(provider)
      .then((res) => {
        if (cancelled) return;
        setModels(res.models);
        setModel((current) => (res.models.some((m) => m.id === current) ? current : (res.default ?? "")));
        setStatus("ready");
      })
      .catch((e) => {
        if (cancelled) return;
        setModels([]);
        setStatus("error");
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [provider]);

  const current = providers.find((p) => p.id === provider);

  return (
    <div className="welcome">
      <div className="frieze" aria-hidden />
      <main className="welcome__inner">
        <header className="welcome__hero">
          <Mascot size={132} mood={status === "loading" ? "busy" : "idle"} />
          <p className="eyebrow">Bienvenue sur</p>
          <h1 className="welcome__title">Agora</h1>
          <p className="welcome__lede">
            La place où l'on vient chercher. Des guides spécialisés t'y attendent, chacun avec ses archives —
            et tout se passe sur ta machine.
          </p>
        </header>

        <section className="welcome__card">
          <h2 className="welcome__step">Qui fera parler les guides ?</h2>
          <div className="choice-row">
            {providers.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`choice ${provider === p.id ? "choice--active" : ""}`}
                onClick={() => setProvider(p.id)}
              >
                <span className="choice__name">{p.name}</span>
                <span className="choice__note">{p.note}</span>
              </button>
            ))}
          </div>

          {status === "error" && (
            <div className="notice notice--error">
              {error}
              {current?.install_url && (
                <>
                  {" "}
                  <a href={current.install_url} target="_blank" rel="noreferrer">
                    Installer Ollama ↗
                  </a>
                </>
              )}
            </div>
          )}

          {status !== "error" && (
            <>
              <h2 className="welcome__step">Avec quel modèle ?</h2>
              {status === "loading" ? (
                <p className="muted">Recherche des modèles installés…</p>
              ) : (
                <div className="model-list">
                  {models.map((m) => (
                    <label key={m.id} className={`model ${model === m.id ? "model--active" : ""}`}>
                      <input type="radio" name="model" value={m.id} checked={model === m.id} onChange={() => setModel(m.id)} />
                      <span className="model__name">{m.label}</span>
                      {m.size && <span className="model__size">{m.size}</span>}
                    </label>
                  ))}
                </div>
              )}
              <p className="hint">
                Seuls les modèles capables d'appeler des outils sont listés : c'est ce qui leur permet d'interroger les
                archives via MCP.
              </p>
            </>
          )}

          <button
            type="button"
            className="primary wide"
            disabled={status !== "ready" || !model}
            onClick={() => onReady({ provider, model, models })}
          >
            Entrer sur l'Agora →
          </button>
        </section>
      </main>
    </div>
  );
}
