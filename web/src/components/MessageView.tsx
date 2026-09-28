import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../api";
import { type AssistantMessage, type Message, type Step, TOOL_LABELS, formatCost, formatMs } from "../conversation";
import { Mascot } from "./Mascot";

const STATUS_TEXT: Record<AssistantMessage["status"], string> = {
  thinking: "Réfléchit…",
  tool: "Consulte les archives…",
  writing: "Rédige…",
  done: "",
  error: "",
  stopped: "Arrêté",
};

function argSummary(args: Record<string, unknown>) {
  const { query, nom, ...rest } = args;
  const main = (query ?? nom) as string | undefined;
  const filters = Object.entries(rest)
    .filter(([k, v]) => v !== null && v !== undefined && k !== "limit")
    .map(([k, v]) => `${k} : ${v}`);
  return { main, filters };
}

function StepView({ step }: { step: Step }) {
  if (step.kind === "note") return <li className="step-note">{step.text}</li>;
  const { main, filters } = argSummary(step.args);
  return (
    <li className={`tool-step tool-step--${step.status}`}>
      <span className="tool-step__icon" aria-hidden>
        {step.status === "running" ? <span className="spinner" /> : step.status === "ok" ? "✓" : "!"}
      </span>
      <div className="tool-step__body">
        <div className="tool-step__title">
          {TOOL_LABELS[step.name] ?? step.name}
          {step.server && <span className="badge">{step.server}</span>}
        </div>
        {main && <div className="tool-step__query">« {main} »</div>}
        {filters.length > 0 && (
          <div className="chips">
            {filters.map((f) => (
              <span key={f} className="chip">
                {f}
              </span>
            ))}
          </div>
        )}
        {step.status === "error" && <div className="tool-step__error">{step.error}</div>}
      </div>
      <span className="tool-step__meta">
        {step.status === "ok" && `${step.count} résultat${(step.count ?? 0) > 1 ? "s" : ""} · ${formatMs(step.durationMs ?? 0)}`}
      </span>
    </li>
  );
}

function Activity({ msg }: { msg: AssistantMessage }) {
  const running = msg.status !== "done" && msg.status !== "error" && msg.status !== "stopped";
  const [open, setOpen] = useState(true);
  const tools = msg.steps.filter((s) => s.kind === "tool").length;
  if (!msg.steps.length) return null;
  return (
    <div className="activity">
      <button type="button" className="activity__toggle" onClick={() => setOpen((v) => !v)}>
        <span>{running ? "Recherche en cours" : `${tools} recherche${tools > 1 ? "s" : ""} dans les archives`}</span>
        <span className={`caret ${open ? "caret--open" : ""}`}>›</span>
      </button>
      {open && (
        <ol className="activity__steps">
          {msg.steps.map((s, i) => (
            <StepView key={s.kind === "tool" ? s.id : `n${i}`} step={s} />
          ))}
        </ol>
      )}
    </div>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  const [all, setAll] = useState(false);
  if (!sources.length) return null;
  const shown = all ? sources : sources.slice(0, 4);
  return (
    <div className="sources">
      <div className="sources__head">
        Sources <span className="muted">({sources.length})</span>
      </div>
      <div className="sources__grid">
        {shown.map((s, i) => (
          <a key={i} className={`source source--${s.kind}`} href={s.url ?? undefined} target="_blank" rel="noreferrer">
            <span className="source__kind">{s.kind === "film" ? "Film" : "Séance"}</span>
            <span className="source__title">{s.title}</span>
            <span className="source__subtitle">{s.subtitle}</span>
            {s.excerpt && <span className="source__excerpt">{s.excerpt}</span>}
          </a>
        ))}
      </div>
      {sources.length > 4 && (
        <button type="button" className="link" onClick={() => setAll((v) => !v)}>
          {all ? "Réduire" : `Voir les ${sources.length - 4} autres`}
        </button>
      )}
    </div>
  );
}

function StatsLine({ msg }: { msg: AssistantMessage }) {
  const s = msg.stats;
  if (!s) return null;
  return (
    <div className="stats" title={`Modèle : ${formatMs(s.llm_ms)} · Outils : ${formatMs(s.tool_ms)}`}>
      <span>⏱ {formatMs(s.total_ms)}</span>
      <span>{s.tool_calls} outil{s.tool_calls > 1 ? "s" : ""}</span>
      <span>
        {(s.prompt_tokens + s.completion_tokens).toLocaleString("fr-FR")} tokens
      </span>
      <span>{s.cost_usd ? formatCost(s.cost_usd) : "gratuit"}</span>
    </div>
  );
}

export function MessageView({ msg }: { msg: Message }) {
  if (msg.role === "user") {
    return (
      <div className="msg msg--user">
        <div className="bubble">{msg.content}</div>
      </div>
    );
  }
  const busy = msg.status === "thinking" || msg.status === "tool" || msg.status === "writing";
  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar">
        <Mascot size={34} mood={msg.status === "error" ? "error" : busy ? "busy" : "idle"} />
      </div>
      <div className="msg__body">
        <Activity msg={msg} />
        {busy && !msg.content && (
          <div className="typing">
            <span className="typing__dots">
              <i />
              <i />
              <i />
            </span>
            {STATUS_TEXT[msg.status]}
          </div>
        )}
        {msg.content && (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            {msg.status === "writing" && <span className="cursor" />}
          </div>
        )}
        {msg.status === "stopped" && <div className="notice">Génération arrêtée.</div>}
        {msg.error && <div className="notice notice--error">{msg.error}</div>}
        {msg.status === "done" && <Sources sources={msg.sources} />}
        <StatsLine msg={msg} />
      </div>
    </div>
  );
}
