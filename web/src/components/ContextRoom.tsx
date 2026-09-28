import { useEffect, useRef, useState } from "react";
import { type ContextInfo, streamChat } from "../api";
import { type AssistantMessage, type LogEntry, type Message, applyEvent, newAssistant, uid } from "../conversation";
import { Emblem } from "./Emblem";
import { LogPanel } from "./LogPanel";
import { MessageView } from "./MessageView";
import type { Settings } from "./Welcome";

const fmt = (n: number) => n.toLocaleString("fr-FR");

export interface Room {
  messages: Message[];
  logs: LogEntry[];
}

/** Un contexte ouvert : son identité à gauche, la conversation avec son agent au centre. */
export function ContextRoom(props: {
  context: ContextInfo;
  settings: Settings;
  room: Room;
  onRoom: (update: (r: Room) => Room) => void;
  onModel: (model: string) => void;
  onLeave: () => void;
}) {
  const { context: ctx, settings, room, onRoom } = props;
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [room.messages]);

  useEffect(() => () => abort.current?.abort(), []); // quitter la salle arrête la génération

  const log = (entry: LogEntry) => onRoom((r) => ({ ...r, logs: [...r.logs.slice(-499), entry] }));

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    setInput("");
    const history = room.messages
      .filter((m) => m.role === "user" || (m.status === "done" && m.content))
      .map((m) => ({ role: m.role, content: m.content }));
    let current: AssistantMessage = newAssistant();
    onRoom((r) => ({ ...r, messages: [...r.messages, { id: uid(), role: "user", content }, current] }));
    log({ at: Date.now(), level: "info", text: `Question à ${ctx.agent} (${settings.model})`, detail: content });

    const update = (next: AssistantMessage) => {
      current = next;
      onRoom((r) => ({ ...r, messages: r.messages.map((m) => (m.id === next.id ? next : m)) }));
    };
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    try {
      await streamChat(
        { context: ctx.id, provider: settings.provider, model: settings.model, message: content, history },
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
        log({ at: Date.now(), level: "warn", text: "Génération arrêtée" });
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

  return (
    <div className={`room ${showLogs ? "room--logs" : ""}`} data-theme={ctx.theme}>
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`}>
        <button type="button" className="back" onClick={props.onLeave}>
          ← Retour à l'Agora
        </button>

        <div className="identity">
          <span className="identity__emblem">
            <Emblem name={ctx.emblem} size={56} />
          </span>
          <div className="identity__place">{ctx.place}</div>
          <div className="identity__agent">
            avec <strong>{ctx.agent}</strong>
          </div>
          <p className="identity__desc">{ctx.description}</p>
        </div>

        <button
          type="button"
          className="primary wide"
          onClick={() => {
            abort.current?.abort();
            onRoom(() => ({ messages: [], logs: [] }));
            setMenuOpen(false);
          }}
        >
          Nouvelle conversation
        </button>

        <section className="panel">
          <h3>Archives</h3>
          <p className="panel__big">{fmt(ctx.points)}</p>
          <p className="muted small-text">extraits indexés · {ctx.corpus_label}</p>
        </section>

        <section className="panel">
          <h3>Outils MCP</h3>
          <ul className="tools">
            {ctx.tools.map((t) => (
              <li key={t.name}>
                <span>{t.label}</span>
                <code>{t.name}</code>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h3>Modèle local</h3>
          <select value={settings.model} disabled={busy} onChange={(e) => props.onModel(e.target.value)}>
            {settings.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
                {m.size ? ` · ${m.size}` : ""}
              </option>
            ))}
          </select>
        </section>
      </aside>

      <main className="chat">
        <header className="chat__head">
          <button type="button" className="ghost small menu-btn" onClick={() => setMenuOpen(true)} aria-label="Menu">
            ☰
          </button>
          <div className="chat__title">
            <span className="chat__place">{ctx.place}</span>
            <span className="chat__tagline">{ctx.tagline}</span>
          </div>
          <button type="button" className={`ghost small ${showLogs ? "active" : ""}`} onClick={() => setShowLogs((v) => !v)}>
            Journal {room.logs.length > 0 && <span className="count">{room.logs.length}</span>}
          </button>
        </header>

        <div className="chat__scroll" ref={scroller}>
          {room.messages.length === 0 ? (
            <div className="empty">
              <span className="empty__emblem">
                <Emblem name={ctx.emblem} size={96} />
              </span>
              <h2>{ctx.tagline}</h2>
              <p className="muted">
                {ctx.agent} cherche dans ses archives avant de répondre, et cite ses sources.
              </p>
              <div className="suggestions">
                {ctx.suggestions.map((s) => (
                  <button key={s} type="button" className="suggestion" onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="thread">
              {room.messages.map((m) => (
                <MessageView key={m.id} msg={m} emblem={ctx.emblem} />
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
            placeholder={`Écris à ${ctx.agent}…`}
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
        <p className="composer__hint muted">Entrée pour envoyer · Maj + Entrée pour aller à la ligne · tout reste sur ta machine</p>
      </main>

      {showLogs && (
        <LogPanel
          logs={room.logs}
          onClose={() => setShowLogs(false)}
          onClear={() => onRoom((r) => ({ ...r, logs: [] }))}
        />
      )}
      {menuOpen && <div className="backdrop" onClick={() => setMenuOpen(false)} />}
    </div>
  );
}
