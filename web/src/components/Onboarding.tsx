import { useEffect, useState } from "react";
import { getModels, getProviders, type Model, type Provider } from "../api";
import { Mascot } from "./Mascot";

export interface Settings {
  provider: string;
  apiKey: string;
  model: string;
  models: Model[];
  remember: boolean;
}

export function Onboarding({ initial, onReady }: { initial?: Settings | null; onReady: (s: Settings) => void }) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState(initial?.provider ?? "openai");
  const [apiKey, setApiKey] = useState(initial?.apiKey ?? "");
  const [showKey, setShowKey] = useState(false);
  const [remember, setRemember] = useState(initial?.remember ?? false);
  const [models, setModels] = useState<Model[]>(initial?.models ?? []);
  const [model, setModel] = useState(initial?.model ?? "");
  const [status, setStatus] = useState<"idle" | "checking" | "ok" | "error">(initial?.models.length ? "ok" : "idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProviders().then(setProviders).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const current = providers.find((p) => p.id === provider);
  const needsKey = provider !== "demo";

  async function check() {
    setStatus("checking");
    setError(null);
    try {
      const res = await getModels(provider, apiKey.trim());
      setModels(res.models);
      setModel(res.default ?? res.models[0]?.id ?? "");
      setStatus(res.models.length ? "ok" : "error");
      if (!res.models.length) setError("Aucun modèle de chat disponible pour cette clé.");
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function pickProvider(id: string) {
    setProvider(id);
    setModels([]);
    setModel("");
    setStatus("idle");
    setError(null);
  }

  return (
    <div className="onboarding">
      <div className="onboarding__card">
        <header className="onboarding__hero">
          <Mascot size={88} mood={status === "checking" ? "busy" : "idle"} />
          <h1>Agora</h1>
          <p>
            Ton assistant pour explorer <strong>35 000 films</strong> et les <strong>débats de l'Assemblée nationale</strong>.
            Tout tourne sur ta machine : ta clé ne part que chez ton fournisseur.
          </p>
        </header>

        <section className="step">
          <h2>
            <span className="step__num">1</span> Fournisseur
          </h2>
          <div className="providers">
            {providers.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`provider ${provider === p.id ? "provider--active" : ""}`}
                disabled={!p.available}
                onClick={() => pickProvider(p.id)}
              >
                <span className="provider__name">{p.name}</span>
                <span className="provider__meta">{p.available ? (p.id === "demo" ? "sans clé" : "disponible") : "bientôt"}</span>
              </button>
            ))}
          </div>
          {current?.note && <p className="hint">{current.note}</p>}
        </section>

        {needsKey && (
          <section className="step">
            <h2>
              <span className="step__num">2</span> Clé API
            </h2>
            <div className="key-input">
              <input
                type={showKey ? "text" : "password"}
                placeholder={current?.key_hint ?? "Clé API"}
                value={apiKey}
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setStatus("idle");
                }}
                onKeyDown={(e) => e.key === "Enter" && apiKey.trim() && check()}
              />
              <button type="button" className="ghost" onClick={() => setShowKey((v) => !v)} aria-label="Afficher la clé">
                {showKey ? "Masquer" : "Afficher"}
              </button>
            </div>
            <div className="key-row">
              <label className="check">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                Se souvenir de la clé sur cet appareil
              </label>
              {current?.key_url && (
                <a href={current.key_url} target="_blank" rel="noreferrer">
                  Obtenir une clé ↗
                </a>
              )}
            </div>
          </section>
        )}

        <section className="step">
          <h2>
            <span className="step__num">{needsKey ? 3 : 2}</span> Modèle
          </h2>
          {status !== "ok" ? (
            <button
              type="button"
              className="primary wide"
              disabled={(needsKey && !apiKey.trim()) || status === "checking"}
              onClick={check}
            >
              {status === "checking" ? "Vérification de la clé…" : needsKey ? "Vérifier la clé" : "Continuer"}
            </button>
          ) : (
            <>
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
              <p className="hint ok">✓ Clé valide · {models.length} modèles disponibles</p>
              <button
                type="button"
                className="primary wide"
                disabled={!model}
                onClick={() => onReady({ provider, apiKey: apiKey.trim(), model, models, remember })}
              >
                Commencer
              </button>
            </>
          )}
          {error && <p className="hint error">{error}</p>}
        </section>
      </div>
    </div>
  );
}
