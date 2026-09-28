import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Polices embarquées dans le build : aucune requête vers un CDN, l'interface marche hors ligne.
import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/fraunces/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/limelight/400.css";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/cormorant-garamond/600.css";
import "@fontsource/cormorant-garamond/700.css";
import "@fontsource/cinzel/500.css";
import "@fontsource/cinzel/600.css";
import "./styles.css";

document.documentElement.dataset.theme = "agora"; // avant le premier rendu : pas de flash de thème

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
