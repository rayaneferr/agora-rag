import type { ChatEvent, Source, Stats } from "./api";

export interface ToolStep {
  kind: "tool";
  id: string;
  name: string;
  label: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "error";
  durationMs?: number;
  count?: number;
  error?: string | null;
}

/** Texte que le modèle écrit avant d'appeler un outil (« Je cherche dans les débats… »). */
export interface NoteStep {
  kind: "note";
  text: string;
}

export type Step = ToolStep | NoteStep;

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  steps: Step[];
  sources: Source[];
  status: "thinking" | "tool" | "writing" | "done" | "error" | "stopped";
  stats?: Stats;
  error?: string;
  round: number;
  startedAt: number;
}

export type Message = UserMessage | AssistantMessage;

export interface LogEntry {
  id: string;
  at: number;
  level: "info" | "tool" | "ok" | "warn" | "error";
  text: string;
  detail?: string;
}

export const uid = () => Math.random().toString(36).slice(2, 10);

export function logEntry(level: LogEntry["level"], text: string, detail?: string): LogEntry {
  return { id: uid(), at: Date.now(), level, text, detail };
}

export function newAssistant(): AssistantMessage {
  return {
    id: uid(),
    role: "assistant",
    content: "",
    steps: [],
    sources: [],
    status: "thinking",
    round: 0,
    startedAt: Date.now(),
  };
}

export const sourceKey = (s: Source) => `${s.kind}|${s.url}|${s.title}|${s.subtitle}`;

export function dedupeSources(sources: Source[]): Source[] {
  const seen = new Set<string>();
  return sources.filter((s) => {
    const key = sourceKey(s);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Applique un événement SSE au message en cours ; renvoie aussi l'entrée de journal associée. */
export function applyEvent(msg: AssistantMessage, ev: ChatEvent): { msg: AssistantMessage; log?: LogEntry } {
  switch (ev.type) {
    case "thinking":
      return {
        msg: { ...msg, status: "thinking", round: ev.round },
        log: logEntry("info", `Appel au modèle (tour ${ev.round})`),
      };
    case "token":
      return { msg: { ...msg, status: "writing", content: msg.content + ev.text } };
    case "tool_call": {
      // Le texte écrit avant l'appel d'outil n'est pas la réponse : on le range comme note.
      const steps: Step[] = msg.content.trim()
        ? [...msg.steps, { kind: "note", text: msg.content.trim() }]
        : [...msg.steps];
      steps.push({ kind: "tool", id: ev.id, name: ev.name, label: ev.label, args: ev.args, status: "running" });
      return {
        msg: { ...msg, status: "tool", content: "", steps },
        log: logEntry("tool", `→ MCP · ${ev.name}`, JSON.stringify(ev.args)),
      };
    }
    case "tool_result": {
      const steps = msg.steps.map((s) =>
        s.kind === "tool" && s.id === ev.id
          ? {
              ...s,
              status: ev.ok ? ("ok" as const) : ("error" as const),
              durationMs: ev.duration_ms,
              count: ev.count,
              error: ev.error,
            }
          : s,
      );
      return {
        msg: { ...msg, steps, sources: dedupeSources([...msg.sources, ...ev.sources]) },
        log: ev.ok
          ? logEntry("ok", `✓ ${ev.name} · ${ev.count} résultat${ev.count > 1 ? "s" : ""} · ${ev.duration_ms} ms`)
          : logEntry("error", `✗ ${ev.name} a échoué`, ev.error ?? undefined),
      };
    }
    case "done":
      return {
        msg: { ...msg, status: "done", content: ev.content || msg.content, stats: ev.stats },
        log: logEntry(
          "ok",
          `Réponse · ${(ev.stats.total_ms / 1000).toFixed(1)} s · ${ev.stats.prompt_tokens + ev.stats.completion_tokens} tokens`,
        ),
      };
    case "error":
      return {
        msg: { ...msg, status: "error", error: ev.message },
        log: logEntry("error", `Erreur (${ev.kind})`, ev.message),
      };
  }
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

/** « 412 Mo », « 1,2 Go » : tailles des téléchargements de premier lancement. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1).replace(".", ",")} Go`;
  return `${Math.round(bytes / 1e6)} Mo`;
}
