import { Check, ChevronRight, CircleAlert, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../api";
import { type AssistantMessage, type Message, type ToolStep, formatMs } from "../conversation";

const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;

/** Ce que l'outil a cherché, en clair : la requête, puis les filtres utiles. */
function describe(step: ToolStep) {
  const { query, nom, limit: _limit, ...rest } = step.args;
  const filters = Object.entries(rest)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k.replace("_", " ")} ${v}`);
  return { query: (query ?? nom) as string | undefined, filters };
}

function StepRow({ step }: { step: ToolStep }) {
  const { query, filters } = describe(step);
  return (
    <li className={`step step--${step.status}`}>
      <span className="step__dot" aria-hidden />
      <div className="step__main">
        <div className="step__line">
          <span className="step__label">{step.label}</span>
          <span className="step__meta">
            {step.status === "running" && "en cours"}
            {step.status === "ok" && `${plural(step.count ?? 0, "résultat")} · ${formatMs(step.durationMs ?? 0)}`}
            {step.status === "error" && "échec"}
          </span>
        </div>
        {query && <div className="step__query">{query}</div>}
        {(filters.length > 0 || step.error) && (
          <div className="step__detail">{step.error ?? filters.join(" · ")}</div>
        )}
      </div>
    </li>
  );
}

/** Les appels MCP : une ligne vivante pendant la recherche, un résumé repliable ensuite. */
function Activity({ msg }: { msg: AssistantMessage }) {
  const tools = msg.steps.filter((s): s is ToolStep => s.kind === "tool");
  const live = msg.status === "thinking" || msg.status === "tool";
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(live), [live]);

  if (!tools.length) {
    return live ? <div className="activity__live shimmer">Réflexion…</div> : null;
  }
  const running = tools.find((t) => t.status === "running");
  const totalMs = tools.reduce((sum, t) => sum + (t.durationMs ?? 0), 0);
  const summary = live
    ? running
      ? `${running.label}…`
      : "Réflexion…"
    : `${plural(tools.length, "recherche")} dans les archives · ${formatMs(totalMs)}`;

  return (
    <div className={`activity ${open ? "is-open" : ""}`}>
      <button type="button" className="activity__head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className={live ? "shimmer" : ""}>{summary}</span>
        <ChevronRight className="activity__chevron" size={14} />
      </button>
      <div className="collapse">
        <ol className="steps">
          {tools.map((t) => (
            <StepRow key={t.id} step={t} />
          ))}
        </ol>
      </div>
    </div>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  const [all, setAll] = useState(false);
  if (!sources.length) return null;
  const shown = all ? sources : sources.slice(0, 3);
  return (
    <div className="sources">
      {shown.map((s, i) => (
        <a
          key={i}
          className="source"
          href={s.url ?? undefined}
          target="_blank"
          rel="noreferrer"
          title={s.excerpt || undefined}
        >
          <span className="source__title">{s.title}</span>
          <span className="source__sub">{s.subtitle}</span>
        </a>
      ))}
      {sources.length > 3 && (
        <button type="button" className="source source--more" onClick={() => setAll((v) => !v)}>
          {all ? "Moins" : `+${sources.length - 3}`}
        </button>
      )}
    </div>
  );
}

function Actions({ msg }: { msg: AssistantMessage }) {
  const [copied, setCopied] = useState(false);
  const s = msg.stats;
  const detail = s
    ? `Modèle ${formatMs(s.llm_ms)} · outils ${formatMs(s.tool_ms)} · ${(s.prompt_tokens + s.completion_tokens).toLocaleString("fr-FR")} tokens`
    : undefined;
  return (
    <div className="actions">
      <button
        type="button"
        className="icon-btn"
        aria-label="Copier la réponse"
        onClick={() => {
          navigator.clipboard?.writeText(msg.content).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          });
        }}
      >
        {copied ? <Check size={15} /> : <Copy size={15} />}
      </button>
      {s && (
        <span className="actions__time" title={detail}>
          {formatMs(s.total_ms)}
        </span>
      )}
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
  return (
    <div className="msg msg--assistant">
      <Activity msg={msg} />
      {msg.content && (
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>
      )}
      {msg.status === "stopped" && <p className="muted small">Réponse interrompue.</p>}
      {msg.error && (
        <div className="notice notice--error">
          <CircleAlert size={16} />
          {msg.error}
        </div>
      )}
      {msg.status === "done" && (
        <>
          <Sources sources={msg.sources} />
          <Actions msg={msg} />
        </>
      )}
    </div>
  );
}
