// Palettes : chaque thème est un jeu de variables CSS appliqué sur <html data-theme="…">.
// Les valeurs vivent dans styles.css ; ici, juste ce qu'il faut pour le sélecteur.

export interface Theme {
  id: string;
  name: string;
  mood: string;
  swatches: string[]; // fond, surface, accent, accent secondaire
}

export const THEMES: Theme[] = [
  {
    id: "agora",
    name: "Agora",
    mood: "Marbre, terre cuite et olivier : une place publique au soleil.",
    swatches: ["#F4EEE3", "#FFFCF6", "#C2522B", "#6E7B3B"],
  },
  {
    id: "hemicycle",
    name: "Hémicycle",
    mood: "Bleu nuit, velours rouge et dorures : la solennité de l'Assemblée.",
    swatches: ["#0E1523", "#172034", "#E0485A", "#D8AE52"],
  },
  {
    id: "pellicule",
    name: "Pellicule",
    mood: "Salle obscure et lumière de projecteur : un film noir chaleureux.",
    swatches: ["#131110", "#1D1A17", "#F2A33A", "#56B3A8"],
  },
  {
    id: "neon",
    name: "Néon",
    mood: "Enseigne de cinéma rétro, cyan et magenta sur fond violet.",
    swatches: ["#0C0A19", "#16122A", "#3EE0DA", "#FF5DBB"],
  },
];

const KEY = "agora.theme";

export function loadTheme(): string {
  try {
    return localStorage.getItem(KEY) ?? "agora";
  } catch {
    return "agora";
  }
}

export function applyTheme(id: string) {
  document.documentElement.dataset.theme = id;
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* stockage indisponible : le thème vaut pour la session */
  }
}
