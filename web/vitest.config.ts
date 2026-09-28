import { defineConfig } from "vitest/config";

// Fonctions pures uniquement (état de conversation, parseur SSE) : pas de DOM à simuler.
export default defineConfig({
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
