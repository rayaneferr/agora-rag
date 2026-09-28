// Contrat avec l'API Python (src/agora/adapters/inbound/api.py). Événements SSE : core/agent.run_turn.

export interface Provider {
  id: string;
  name: string;
  note: string;
  install_url: string;
}

export interface Model {
  id: string;
  label: string;
  size: string;
}

/** Un contexte délimité : base indexée + serveur MCP + identité. */
export interface ContextInfo {
  id: string;
  place: string;
  agent: string;
  tagline: string;
  description: string;
  theme: string;
  emblem: string;
  corpus_label: string;
  /** Étendue des archives (« séances du 18 juillet 2024 au 26 septembre 2026 »), null tant que l'index n'est pas là. */
  coverage: string | null;
  suggestions: string[];
  tools: { name: string; label: string }[];
  points: number;
}

/** Progression d'un téléchargement de premier lancement (index, modèle d'embeddings). */
export interface Download {
  status: "ready" | "downloading" | "error" | "unknown";
  error: string | null;
  done_bytes: number | null;
  total_bytes: number | null;
}

export interface Health {
  index: Download;
  embedder: Download;
}

export interface Source {
  kind: string;
  title: string;
  subtitle: string;
  url: string | null;
  excerpt: string;
  score: number | null;
}

export interface Stats {
  llm_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  llm_ms: number;
  tool_ms: number;
  total_ms: number;
}

export type ChatEvent =
  | { type: "thinking"; round: number }
  | { type: "token"; text: string }
  | { type: "tool_call"; id: string; name: string; label: string; args: Record<string, unknown> }
  | {
      type: "tool_result";
      id: string;
      name: string;
      ok: boolean;
      duration_ms: number;
      count: number;
      sources: Source[];
      error: string | null;
    }
  | { type: "done"; content: string; stats: Stats }
  | { type: "error"; kind: string; message: string };

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Erreur ${res.status}`);
  }
  return res.json();
}

export const getProviders = () => fetch("/api/providers").then((r) => json<Provider[]>(r));
export const getContexts = () => fetch("/api/contexts").then((r) => json<ContextInfo[]>(r));
export const getHealth = () => fetch("/api/health").then((r) => json<Health>(r));
export const getModels = (provider: string) =>
  fetch(`/api/models?provider=${encodeURIComponent(provider)}`).then((r) =>
    json<{ models: Model[]; default: string | null }>(r),
  );

export interface ChatRequest {
  context: string;
  provider: string;
  model: string;
  message: string;
  history: { role: "user" | "assistant"; content: string }[];
}

/**
 * Découpe un flux SSE en trames `data:` au fil des morceaux reçus (une trame peut arriver coupée en deux).
 * Renvoie les données complètes et garde le reste pour l'appel suivant.
 */
export class SseParser {
  private buffer = "";

  push(chunk: string): string[] {
    this.buffer += chunk;
    const out: string[] = [];
    for (let sep = this.buffer.indexOf("\n\n"); sep >= 0; sep = this.buffer.indexOf("\n\n")) {
      const frame = this.buffer.slice(0, sep);
      this.buffer = this.buffer.slice(sep + 2);
      const data = frame
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n");
      if (data) out.push(data);
    }
    return out;
  }
}

/** POST + lecture du flux SSE (EventSource ne sait pas faire de POST). */
export async function streamChat(req: ChatRequest, onEvent: (e: ChatEvent) => void, signal: AbortSignal) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Erreur ${res.status}`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const data of parser.push(value)) onEvent(JSON.parse(data) as ChatEvent);
  }
}
