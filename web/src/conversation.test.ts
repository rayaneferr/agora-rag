import { describe, expect, it } from "vitest";
import type { ChatEvent, Source } from "./api";
import { applyEvent, dedupeSources, formatBytes, formatMs, newAssistant } from "./conversation";

const source = (title: string, url = "u"): Source => ({
  kind: "film",
  title,
  subtitle: "1993",
  url,
  excerpt: "…",
  score: 0.9,
});

function replay(events: ChatEvent[]) {
  let msg = newAssistant();
  const logs = [];
  for (const ev of events) {
    const out = applyEvent(msg, ev);
    msg = out.msg;
    if (out.log) logs.push(out.log);
  }
  return { msg, logs };
}

describe("applyEvent", () => {
  it("suit un tour complet : réflexion, outil, texte, fin", () => {
    const { msg, logs } = replay([
      { type: "thinking", round: 1 },
      { type: "tool_call", id: "c1", name: "search_films", label: "Recherche", args: { query: "boucle" } },
      {
        type: "tool_result",
        id: "c1",
        name: "search_films",
        ok: true,
        duration_ms: 120,
        count: 3,
        sources: [source("Groundhog Day")],
        error: null,
      },
      { type: "thinking", round: 2 },
      { type: "token", text: "Un " },
      { type: "token", text: "film." },
      {
        type: "done",
        content: "Un film.",
        stats: {
          llm_calls: 2,
          tool_calls: 1,
          prompt_tokens: 100,
          completion_tokens: 20,
          llm_ms: 900,
          tool_ms: 120,
          total_ms: 1100,
        },
      },
    ]);
    expect(msg.status).toBe("done");
    expect(msg.content).toBe("Un film.");
    expect(msg.round).toBe(2);
    expect(msg.steps).toEqual([
      {
        kind: "tool",
        id: "c1",
        name: "search_films",
        label: "Recherche",
        args: { query: "boucle" },
        status: "ok",
        durationMs: 120,
        count: 3,
        error: null,
      },
    ]);
    expect(msg.sources.map((s) => s.title)).toEqual(["Groundhog Day"]);
    expect(logs.map((l) => l.level)).toEqual(["info", "tool", "ok", "info", "ok"]);
    expect(logs.at(-1)?.text).toBe("Réponse · 1.1 s · 120 tokens");
  });

  it("range le texte écrit avant un appel d'outil comme note, pas comme réponse", () => {
    const { msg } = replay([
      { type: "token", text: "Je cherche…" },
      { type: "tool_call", id: "c1", name: "search_debats", label: "Recherche", args: {} },
    ]);
    expect(msg.content).toBe("");
    expect(msg.status).toBe("tool");
    expect(msg.steps[0]).toEqual({ kind: "note", text: "Je cherche…" });
    expect(msg.steps[1]).toMatchObject({ kind: "tool", status: "running" });
  });

  it("marque l'étape en échec et garde le message d'erreur de l'outil", () => {
    const { msg, logs } = replay([
      { type: "tool_call", id: "c1", name: "get_film", label: "Fiche", args: { film_id: 1 } },
      {
        type: "tool_result",
        id: "c1",
        name: "get_film",
        ok: false,
        duration_ms: 5,
        count: 1,
        sources: [],
        error: "boom",
      },
    ]);
    expect(msg.steps[0]).toMatchObject({ status: "error", error: "boom" });
    expect(logs.at(-1)).toMatchObject({ level: "error", detail: "boom" });
  });

  it("passe en erreur sur un événement error et garde le texte déjà reçu", () => {
    const { msg } = replay([
      { type: "token", text: "Début" },
      { type: "error", kind: "network", message: "Ollama injoignable" },
    ]);
    expect(msg.status).toBe("error");
    expect(msg.error).toBe("Ollama injoignable");
    expect(msg.content).toBe("Début");
  });

  it("garde le texte streamé si done arrive sans contenu", () => {
    const { msg } = replay([
      { type: "token", text: "Texte" },
      {
        type: "done",
        content: "",
        stats: {
          llm_calls: 1,
          tool_calls: 0,
          prompt_tokens: 1,
          completion_tokens: 1,
          llm_ms: 1,
          tool_ms: 0,
          total_ms: 1,
        },
      },
    ]);
    expect(msg.content).toBe("Texte");
  });
});

describe("dedupeSources", () => {
  it("ne garde qu'une source par (type, url, titre, sous-titre)", () => {
    const out = dedupeSources([source("A"), source("A"), source("A", "autre"), source("B")]);
    expect(out.map((s) => `${s.title}/${s.url}`)).toEqual(["A/u", "A/autre", "B/u"]);
  });
});

describe("formats", () => {
  it("formatMs", () => {
    expect(formatMs(850)).toBe("850 ms");
    expect(formatMs(1234)).toBe("1,2 s");
  });
  it("formatBytes", () => {
    expect(formatBytes(412_000_000)).toBe("412 Mo");
    expect(formatBytes(2_270_000_000)).toBe("2,3 Go");
  });
});
