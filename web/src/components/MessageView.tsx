import { Check, ChevronRight, CircleAlert, Copy, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../api";
import { type AssistantMessage, formatMs, type Message, sourceKey, type ToolStep } from "../conversation";

const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;

/** Ce que l'outil a cherché, en clair : la requête, puis les filtres utiles. */
function describe(step: ToolStep) {
  const { query, nom, limit: _limit, ...rest } = step.args;
  const filters = Object.entries(rest)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k.replace("_", " ")} ${v}`);
  return { query: (query ?? nom) as string | undefined, filters };
}

/** Secondes écoulées depuis le début du tour : un modèle local peut mettre une minute avant le premier token. */
function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const s = Math.max(0, Math.floor((now - since) / 1000));
  return <span className="elapsed">{s} s</span>;
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
        {(filters.length > 0 || step.error) && <div className="step__detail">{step.error ?? filters.join(" · ")}</div>}
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
    return live ? (
      <div className="activity__live">
        <span className="shimmer">Réflexion…</span> <Elapsed since={msg.startedAt} />
      </div>
    ) : null;
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
        {live && <Elapsed since={msg.startedAt} />}
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

/** Sources compactes par défaut ; « Extraits » déplie le passage cité, lisible aussi au tactile et au lecteur d'écran. */
function Sources({ sources }: { sources: Source[] }) {
  const [all, setAll] = useState(false);
  const [excerpts, setExcerpts] = useState(false);
  if (!sources.length) return null;
  const shown = all || excerpts ? sources : sources.slice(0, 3);
  const hasExcerpt = sources.some((s) => s.excerpt);
  return (
    <div className={`sources ${excerpts ? "sources--excerpts" : ""}`}>
      {shown.map((s) => (
        <a key={sourceKey(s)} className="source" href={s.url ?? undefined} target="_blank" rel="noreferrer">
          <span className="source__title">{s.title}</span>
          <span className="source__sub">{s.subtitle}</span>
          {excerpts && s.excerpt && <span className="source__excerpt">{s.excerpt}…</span>}
        </a>
      ))}
      <span className="sources__actions">
        {!excerpts && sources.length > 3 && (
          <button type="button" className="source source--more" onClick={() => setAll((v) => !v)}>
            {all ? "Moins" : `+${sources.length - 3}`}
          </button>
        )}
        {hasExcerpt && (
          <button
            type="button"
            className="source source--more"
            onClick={() => setExcerpts((v) => !v)}
            aria-pressed={excerpts}
          >
            {excerpts ? "Masquer les extraits" : "Extraits"}
          </button>
        )}
      </span>
    </div>
  );
}

function Actions({ msg, onRetry }: { msg: AssistantMessage; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  const s = msg.stats;
  const detail = s
    ? `Modèle ${formatMs(s.llm_ms)} · outils ${formatMs(s.tool_ms)} · ${(s.prompt_tokens + s.completion_tokens).toLocaleString("fr-FR")} tokens`
    : undefined;
  return (
    <div className="actions">
      {msg.content && (
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
      )}
      {onRetry && (
        <button type="button" className="icon-btn" aria-label="Réessayer" title="Réessayer" onClick={onRetry}>
          <RotateCcw size={15} />
        </button>
      )}
      {s && (
        <span className="actions__time" title={detail}>
          {formatMs(s.total_ms)}
        </span>
      )}
    </div>
  );
}

export function MessageView({ msg, onRetry }: { msg: Message; onRetry?: () => void }) {
  if (msg.role === "user") {
    return (
      <div className="msg msg--user">
        <div className="bubble">{msg.content}</div>
      </div>
    );
  }
  const finished = msg.status === "done" || msg.status === "error" || msg.status === "stopped";
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
      {msg.status === "done" && <Sources sources={msg.sources} />}
      {finished && <Actions msg={msg} onRetry={onRetry} />}
    </div>
  );
}
