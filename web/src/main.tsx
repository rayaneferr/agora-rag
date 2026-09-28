import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Polices embarquées dans le build : aucune requête vers un CDN, l'interface marche hors ligne.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Élément #root introuvable");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
