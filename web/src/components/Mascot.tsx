import { useEffect, useState } from "react";

// Mascotte provisoire (hibou SVG). Dès qu'une image existe dans web/public/mascot.png
// (celle générée avec Gemini), elle la remplace automatiquement.

type Mood = "idle" | "busy" | "error";

let customMascot: Promise<boolean> | null = null;
function hasCustomMascot() {
  customMascot ??= new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = "/mascot.png";
  });
  return customMascot;
}

export function Mascot({ size = 40, mood = "idle" }: { size?: number; mood?: Mood }) {
  const [custom, setCustom] = useState(false);
  useEffect(() => {
    hasCustomMascot().then(setCustom);
  }, []);

  const cls = `mascot mascot--${mood}`;
  if (custom) {
    return <img className={cls} src="/mascot.png" width={size} height={size} alt="Agora" />;
  }
  return (
    <svg className={cls} width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Agora">
      {/* aigrettes */}
      <path d="M17 17 L14 6 L25 13 Z" fill="var(--accent)" />
      <path d="M47 17 L50 6 L39 13 Z" fill="var(--accent)" />
      {/* corps */}
      <ellipse cx="32" cy="36" rx="21" ry="23" fill="var(--accent)" />
      <ellipse cx="32" cy="43" rx="13" ry="13" fill="var(--mascot-belly)" />
      {/* plumes du ventre */}
      <path d="M26 41 q3 3 6 0 q3 3 6 0 M28 47 q2 2.5 4 0 q2 2.5 4 0" stroke="var(--accent)" strokeWidth="1.4" fill="none" opacity=".5" />
      {/* yeux */}
      <g className="mascot__eyes">
        <circle cx="23.5" cy="28" r="8" fill="var(--mascot-belly)" />
        <circle cx="40.5" cy="28" r="8" fill="var(--mascot-belly)" />
        <circle className="mascot__pupil" cx="24.5" cy="28.5" r="3.6" fill="var(--mascot-ink)" />
        <circle className="mascot__pupil" cx="39.5" cy="28.5" r="3.6" fill="var(--mascot-ink)" />
        <circle cx="25.6" cy="27.2" r="1.1" fill="#fff" />
        <circle cx="40.6" cy="27.2" r="1.1" fill="#fff" />
      </g>
      {/* bec */}
      <path d="M32 32 l-3 4 h6 z" fill="var(--accent-2)" />
      {/* lunettes de lecture sur le front : clin d'œil aux archives */}
      <path d="M20 19 h24" stroke="var(--mascot-ink)" strokeWidth="1.2" opacity=".35" />
    </svg>
  );
}
