import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { getModels, getProviders, type Model, type Provider } from "../api";
import { Mascot } from "./Mascot";

export interface Settings {
  provider: string;
  model: string;
  models: Model[];
}

/** Premier écran : choisir le modèle local qui fera parler les agents. */
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
    <div className="page page--center">
      <main className="welcome">
        <Mascot size={52} />
        <h1>Agora</h1>
        <p className="welcome__lede">Des agents qui cherchent dans leurs archives avant de répondre. Tout tourne sur ta machine.</p>

        {providers.length > 1 && (
          <div className="segmented" role="tablist">
            {providers.map((p) => (
              <button
                key={p.id}
                type="button"
                role="tab"
                aria-selected={provider === p.id}
                className={provider === p.id ? "is-active" : ""}
                onClick={() => setProvider(p.id)}
              >
                {p.name}
              </button>
            ))}
          </div>
        )}

        {status === "error" ? (
          <div className="notice notice--error">
            {error}
            {current?.install_url && (
              <>
                {" "}
                <a href={current.install_url} target="_blank" rel="noreferrer">
                  Installer Ollama
                </a>
              </>
            )}
          </div>
        ) : (
          <div className="options" aria-busy={status === "loading"}>
            {status === "loading" && <p className="muted small">Recherche des modèles installés…</p>}
            {models.map((m) => (
              <button
                key={m.id}
                type="button"
                className={`option ${model === m.id ? "is-active" : ""}`}
                onClick={() => setModel(m.id)}
              >
                <span className="option__name">{m.label}</span>
                {m.size && <span className="option__meta">{m.size}</span>}
                <span className="option__check">{model === m.id && <Check size={16} />}</span>
              </button>
            ))}
          </div>
        )}

        <button
          type="button"
          className="btn btn--primary btn--block"
          disabled={status !== "ready" || !model}
          onClick={() => onReady({ provider, model, models })}
        >
          Continuer
        </button>
        <p className="fine">Seuls les modèles capables d'appeler des outils sont proposés.</p>
      </main>
    </div>
  );
}
