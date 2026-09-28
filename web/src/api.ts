// Contrat avec l'API Python (src/agora/api.py). Les événements SSE sont émis par agent.run_turn.

export interface Provider {
  id: string;
  name: string;
  key_url: string;
  key_hint: string;
  available: boolean;
  note: string;
}

export interface Model {
  id: string;
  label: string;
}

export interface Health {
  index: { status: "ready" | "downloading" | "error" | "unknown"; error: string | null; points: Record<string, number | null> };
  tools: { name: string; server: string }[];
}

export interface Source {
  kind: "film" | "debat";
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
  cost_usd: number;
  llm_ms: number;
  tool_ms: number;
  total_ms: number;
}

export type ChatEvent =
  | { type: "thinking"; round: number }
  | { type: "token"; text: string }
  | { type: "tool_call"; id: string; name: string; server: string | null; args: Record<string, unknown> }
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

export const getHealth = () => fetch("/api/health").then((r) => json<Health>(r));
export const getProviders = () => fetch("/api/providers").then((r) => json<Provider[]>(r));

export const getModels = (provider: string, apiKey: string) =>
  fetch("/api/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey }),
  }).then((r) => json<{ models: Model[]; default: string | null }>(r));

export interface ChatRequest {
  provider: string;
  model: string;
  api_key: string;
  message: string;
  history: { role: "user" | "assistant"; content: string }[];
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
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = frame
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n");
      if (data) onEvent(JSON.parse(data) as ChatEvent);
    }
  }
}
