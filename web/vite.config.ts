import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En dev, le front (Vite, :5173) parle à l'API Python (`uv run agora --dev`, :8765).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
