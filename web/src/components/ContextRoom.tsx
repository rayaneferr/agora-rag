import { ArrowLeft, PanelLeft, ScrollText, SquarePen } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { isReady } from "../App";
import { type ContextInfo, type Health, streamChat } from "../api";
import {
  type AssistantMessage,
  applyEvent,
  type LogEntry,
  logEntry,
  type Message,
  newAssistant,
  uid,
} from "../conversation";
import { Composer } from "./Composer";
import { ContextIcon } from "./ContextIcon";
import { LogPanel } from "./LogPanel";
import { MessageView } from "./MessageView";
import { SetupBanner } from "./SetupBanner";
import type { Settings } from "./Welcome";

export interface Room {
  messages: Message[];
  logs: LogEntry[];
}

/** En dessous de cette distance du bas, on considère que l'utilisateur suit la conversation. */
const STICK_PX = 80;

/** Un contexte ouvert : les agents à gauche, la conversation au centre, le journal à droite (à la demande). */
export function ContextRoom(props: {
  context: ContextInfo;
  contexts: ContextInfo[];
  settings: Settings;
  health: Health | null;
  room: Room;
  onRoom: (update: (r: Room) => Room) => void;
  onModel: (model: string) => void;
  onSwitch: (id: string) => void;
  onLeave: () => void;
}) {
  const { context: ctx, settings, room, onRoom } = props;
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  // Vrai tant que l'utilisateur est en bas : on suit alors la génération, sinon on le laisse relire.
  const stick = useRef(true);
  const ready = isReady(props.health);

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight });
  }, [room.messages]);

  useEffect(() => () => abort.current?.abort(), []); // quitter la salle arrête la génération

  const onScroll = () => {
    const el = scroller.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
  };

  const log = (entry: LogEntry) => onRoom((r) => ({ ...r, logs: [...r.logs.slice(-499), entry] }));

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy || !ready) return;
    setInput("");
    stick.current = true;
    const history = room.messages
      .filter((m) => m.role === "user" || (m.status === "done" && m.content))
      .map((m) => ({ role: m.role, content: m.content }));
    let current: AssistantMessage = newAssistant();
    onRoom((r) => ({ ...r, messages: [...r.messages, { id: uid(), role: "user", content }, current] }));
    log(logEntry("info", `Question (${settings.model})`, content));

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
        log(logEntry("warn", "Génération arrêtée"));
      } else {
        const message = e instanceof Error ? e.message : String(e);
        update({ ...current, status: "error", error: message });
        log(logEntry("error", "Échec de la requête", message));
      }
    } finally {
      abort.current = null;
      setBusy(false);
    }
  }

  /** Rejoue la dernière question : la réponse interrompue ou en erreur est retirée, la question renvoyée. */
  const retry = () => {
    const last = room.messages[room.messages.length - 1];
    const question = room.messages[room.messages.length - 2];
    if (last?.role !== "assistant" || question?.role !== "user") return;
    onRoom((r) => ({ ...r, messages: r.messages.slice(0, -2) }));
    void send(question.content);
  };

  const reset = () => {
    abort.current?.abort();
    onRoom(() => ({ messages: [], logs: [] }));
    setMenuOpen(false);
  };

  const composer = (
    <Composer
      value={input}
      onChange={setInput}
      onSend={() => send(input)}
      onStop={() => abort.current?.abort()}
      busy={busy}
      disabled={!ready}
      placeholder={ready ? `Écrire à ${ctx.agent}` : "Les archives se préparent…"}
      autoFocus
    />
  );
  const empty = room.messages.length === 0;
  const lastId = room.messages[room.messages.length - 1]?.id;

  return (
    <div className={`room ${showLogs ? "has-logs" : ""}`} data-context={ctx.theme}>
      <aside className={`sidebar ${menuOpen ? "is-open" : ""}`}>
        <div className="sidebar__top">
          <button type="button" className="nav-item" onClick={props.onLeave}>
            <ArrowLeft size={16} />
            Agents
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={reset}
            aria-label="Nouvelle conversation"
            title="Nouvelle conversation"
          >
            <SquarePen size={17} />
          </button>
        </div>

        <nav className="sidebar__list">
          {props.contexts.map((c) => (
            <button
              key={c.id}
              type="button"
              data-context={c.theme}
              className={`nav-item ${c.id === ctx.id ? "is-active" : ""}`}
              onClick={() => {
                setMenuOpen(false);
                if (c.id !== ctx.id) props.onSwitch(c.id);
              }}
            >
              <ContextIcon emblem={c.emblem} size={24} />
              {c.place}
            </button>
          ))}
        </nav>

        <label className="sidebar__model">
          <span>Modèle</span>
          <select value={settings.model} disabled={busy} onChange={(e) => props.onModel(e.target.value)}>
            {settings.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </aside>

      <main className="chat">
        <header className="chat__head">
          <button type="button" className="icon-btn only-mobile" onClick={() => setMenuOpen(true)} aria-label="Menu">
            <PanelLeft size={18} />
          </button>
          <span className="chat__title">{ctx.place}</span>
          <button
            type="button"
            className={`icon-btn ${showLogs ? "is-active" : ""}`}
            onClick={() => setShowLogs((v) => !v)}
            aria-label="Journal"
            title="Journal MCP"
          >
            <ScrollText size={17} />
          </button>
        </header>

        {empty ? (
          <div className="intro">
            <ContextIcon emblem={ctx.emblem} size={44} />
            <h2>{ctx.tagline}</h2>
            {ctx.coverage && <p className="intro__coverage">{ctx.coverage}</p>}
            <SetupBanner health={props.health} />
            {composer}
            <div className="suggestions">
              {ctx.suggestions.map((s) => (
                <button key={s} type="button" className="suggestion" disabled={!ready} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="chat__scroll" ref={scroller} onScroll={onScroll}>
              <div className="thread">
                {room.messages.map((m) => (
                  <MessageView key={m.id} msg={m} onRetry={m.id === lastId && !busy ? retry : undefined} />
                ))}
              </div>
            </div>
            <div className="chat__foot">
              <SetupBanner health={props.health} />
              {composer}
              <p className="fine">Réponses générées en local à partir des archives. Vérifie les sources.</p>
            </div>
          </>
        )}
      </main>

      {showLogs && (
        <LogPanel
          logs={room.logs}
          onClose={() => setShowLogs(false)}
          onClear={() => onRoom((r) => ({ ...r, logs: [] }))}
        />
      )}
      {menuOpen && (
        <button type="button" className="backdrop" aria-label="Fermer le menu" onClick={() => setMenuOpen(false)} />
      )}
    </div>
  );
}
