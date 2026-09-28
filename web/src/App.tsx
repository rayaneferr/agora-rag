import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, streamChat, type Health } from "./api";
import { LogPanel } from "./components/LogPanel";
import { Mascot } from "./components/Mascot";
import { MessageView } from "./components/MessageView";
import { Onboarding, type Settings } from "./components/Onboarding";
import { Sidebar } from "./components/Sidebar";
import { type AssistantMessage, type LogEntry, type Message, applyEvent, newAssistant, uid } from "./conversation";
import { applyTheme, loadTheme } from "./themes";

const SETTINGS_KEY = "agora.settings";

// La clé reste dans l'onglet (sessionStorage) ; dans localStorage seulement si l'utilisateur le demande.
function loadSettings(): Settings | null {
  try {
    const raw = sessionStorage.getItem(SETTINGS_KEY) ?? localStorage.getItem(SETTINGS_KEY);
    return raw ? (JSON.parse(raw) as Settings) : null;
  } catch {
    return null;
  }
}

function saveSettings(s: Settings | null) {
  try {
    sessionStorage.removeItem(SETTINGS_KEY);
    localStorage.removeItem(SETTINGS_KEY);
    if (s) (s.remember ? localStorage : sessionStorage).setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* stockage indisponible : réglages valables jusqu'au rechargement */
  }
}

const SUGGESTIONS = [
  { label: "Un film où un homme revit la même journée", kind: "Films" },
  { label: "Qu'a dit Éric Coquerel sur la dette publique ?", kind: "Débats" },
  { label: "Des films de science-fiction réalisés par Ridley Scott", kind: "Films" },
  { label: "Comment les députés ont-ils débattu de l'intelligence artificielle ?", kind: "Débats" },
];

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(loadSettings);
  const [editingSettings, setEditingSettings] = useState(false);
  const [theme, setTheme] = useState(loadTheme);
  const [health, setHealth] = useState<Health | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [input, setInput] = useState("");
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Santé du backend : index prêt ? outils MCP connectés ? (re-vérifie tant que ce n'est pas prêt)
  useEffect(() => {
    let timer: number;
    const poll = () =>
      getHealth()
        .then((h) => {
          setHealth(h);
          if (h.index.status !== "ready" || !h.tools.length) timer = window.setTimeout(poll, 3000);
        })
        .catch(() => (timer = window.setTimeout(poll, 3000)));
    poll();
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const log = useCallback((entry: LogEntry) => setLogs((l) => [...l.slice(-499), entry]), []);

  async function send(text: string) {
    const content = text.trim();
    if (!content || !settings || busy) return;
    setInput("");
    const history = messages
      .filter((m) => m.role === "user" || (m.status === "done" && m.content))
      .map((m) => ({ role: m.role, content: m.content }));
    const user: Message = { id: uid(), role: "user", content };
    let current: AssistantMessage = newAssistant();
    setMessages((ms) => [...ms, user, current]);
    log({ at: Date.now(), level: "info", text: `Question envoyée à ${settings.model}`, detail: content });

    const update = (next: AssistantMessage) => {
      current = next;
      setMessages((ms) => ms.map((m) => (m.id === next.id ? next : m)));
    };

    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    try {
      await streamChat(
        { provider: settings.provider, model: settings.model, api_key: settings.apiKey, message: content, history },
        (ev) => {
          const { msg, log: entry } = applyEvent(current, ev);
          update(msg);
          if (entry) log(entry);
        },
        controller.signal,
      );
      if (current.status !== "done" && current.status !== "error") {
        update({ ...current, status: "error", error: "La connexion au serveur s'est interrompue." });
      }
    } catch (e) {
      if (controller.signal.aborted) {
        update({ ...current, status: "stopped" });
        log({ at: Date.now(), level: "warn", text: "Génération arrêtée par l'utilisateur" });
      } else {
        const message = e instanceof Error ? e.message : String(e);
        update({ ...current, status: "error", error: message });
        log({ at: Date.now(), level: "error", text: "Échec de la requête", detail: message });
      }
    } finally {
      abort.current = null;
      setBusy(false);
    }
  }

  function onReady(s: Settings) {
    saveSettings(s);
    setSettings(s);
    setEditingSettings(false);
    log({ at: Date.now(), level: "ok", text: `Connecté · ${s.provider} · ${s.model}` });
  }

  if (!settings || editingSettings) {
    return <Onboarding initial={editingSettings ? settings : null} onReady={onReady} />;
  }

  return (
    <div className={`layout ${showLogs ? "layout--logs" : ""}`}>
      <Sidebar
        settings={settings}
        health={health}
        theme={theme}
        open={sidebarOpen}
        onTheme={setTheme}
        onModel={(model) => {
          const next = { ...settings, model };
          saveSettings(next);
          setSettings(next);
          log({ at: Date.now(), level: "info", text: `Modèle : ${model}` });
        }}
        onNewChat={() => {
          abort.current?.abort();
          setMessages([]);
          setSidebarOpen(false);
        }}
        onChangeKey={() => setEditingSettings(true)}
        onClose={() => setSidebarOpen(false)}
      />

      <main className="chat">
        <header className="chat__head">
          <button type="button" className="ghost small menu-btn" onClick={() => setSidebarOpen(true)} aria-label="Menu">
            ☰
          </button>
          <div className="chat__title">
            <span className="model-pill">{settings.model.replace(/^[^/]+\//, "")}</span>
          </div>
          <button
            type="button"
            className={`ghost small ${showLogs ? "active" : ""}`}
            onClick={() => setShowLogs((v) => !v)}
          >
            Journal {logs.length > 0 && <span className="count">{logs.length}</span>}
          </button>
        </header>

        <div className="chat__scroll" ref={scroller}>
          {messages.length === 0 ? (
            <div className="empty">
              <Mascot size={96} />
              <h2>Que veux-tu explorer ?</h2>
              <p className="muted">
                Je cherche dans les synopsis de films et dans les comptes rendus de l'Assemblée, puis je te réponds en
                citant mes sources.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s.label} type="button" className="suggestion" onClick={() => send(s.label)}>
                    <span className="suggestion__kind">{s.kind}</span>
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="thread">
              {messages.map((m) => (
                <MessageView key={m.id} msg={m} />
              ))}
            </div>
          )}
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <textarea
            value={input}
            rows={1}
            placeholder="Pose ta question sur un film ou un débat…"
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send(input);
              }
            }}
          />
          {busy ? (
            <button type="button" className="send send--stop" onClick={() => abort.current?.abort()} aria-label="Arrêter">
              ■
            </button>
          ) : (
            <button type="submit" className="send" disabled={!input.trim()} aria-label="Envoyer">
              ↑
            </button>
          )}
        </form>
        <p className="composer__hint muted">Entrée pour envoyer · Maj + Entrée pour aller à la ligne</p>
      </main>

      {showLogs && <LogPanel logs={logs} onClose={() => setShowLogs(false)} onClear={() => setLogs([])} />}
      {sidebarOpen && <div className="backdrop" onClick={() => setSidebarOpen(false)} />}
    </div>
  );
}
