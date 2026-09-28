import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import { applyTheme, loadTheme } from "./themes";

applyTheme(loadTheme()); // avant le premier rendu : pas de flash de thème

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
