import { describe, expect, it } from "vitest";
import { SseParser } from "./api";

describe("SseParser", () => {
  it("rend une trame complète", () => {
    expect(new SseParser().push('data: {"type":"thinking"}\n\n')).toEqual(['{"type":"thinking"}']);
  });

  it("recolle une trame coupée entre deux morceaux réseau", () => {
    const p = new SseParser();
    expect(p.push('data: {"type":"tok')).toEqual([]);
    expect(p.push('en","text":"a"}\n\ndata: {"type":"done"}\n\n')).toEqual([
      '{"type":"token","text":"a"}',
      '{"type":"done"}',
    ]);
  });

  it("ignore les commentaires et champs inconnus, joint les data multilignes", () => {
    const p = new SseParser();
    expect(p.push(": keep-alive\nevent: x\ndata: a\ndata: b\n\n")).toEqual(["a\nb"]);
  });

  it("garde le reste incomplet pour l'appel suivant", () => {
    const p = new SseParser();
    expect(p.push("data: 1\n\ndata: 2\n")).toEqual(["1"]);
    expect(p.push("\n")).toEqual(["2"]);
  });
});
