// Emblèmes des lieux : dessinés en SVG, colorés par les variables du thème actif.

function Clap({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <g transform="rotate(-12 12 22)">
        <rect x="8" y="12" width="48" height="11" rx="2" fill="var(--emblem-ink)" />
        {[0, 1, 2, 3].map((i) => (
          <path key={i} d={`M${14 + i * 11} 12 l7 0 l-5 11 l-7 0 z`} fill="var(--emblem-light)" />
        ))}
      </g>
      <rect x="8" y="25" width="48" height="29" rx="3" fill="var(--emblem-ink)" />
      <rect x="8" y="25" width="48" height="6" fill="var(--emblem-light)" opacity=".9" />
      {[0, 1, 2, 3].map((i) => (
        <path key={i} d={`M${12 + i * 11} 25 l6 0 l-4 6 l-6 0 z`} fill="var(--emblem-ink)" />
      ))}
      <path d="M15 40 h20 M15 46 h14" stroke="var(--emblem-light)" strokeWidth="2" strokeLinecap="round" opacity=".7" />
      <circle cx="46" cy="43" r="4" fill="var(--accent)" />
    </svg>
  );
}

function Hemicycle({ size }: { size: number }) {
  // Sièges en demi-cercles concentriques, comme dans la salle des séances. Couleurs neutres : aucun
  // « côté » n'est mis en avant.
  const rows = [
    { r: 12, n: 7 },
    { r: 18, n: 11 },
    { r: 24, n: 15 },
  ];
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      {rows.map(({ r, n }, ri) =>
        Array.from({ length: n }, (_, i) => {
          const a = Math.PI - (i / (n - 1)) * Math.PI;
          return (
            <circle
              key={`${ri}-${i}`}
              cx={32 + r * Math.cos(a)}
              cy={44 - r * Math.sin(a)}
              r={1.9}
              fill={ri === 0 ? "var(--accent)" : "var(--emblem-light)"}
              opacity={1 - ri * 0.18}
            />
          );
        }),
      )}
      <rect x="27" y="46" width="10" height="7" rx="1.5" fill="var(--emblem-light)" />
      <path d="M22 56 h20" stroke="var(--emblem-light)" strokeWidth="1.6" strokeLinecap="round" opacity=".6" />
    </svg>
  );
}

function Column({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <path d="M14 14 h36 l-3 5 h-30 z" fill="var(--accent)" />
      {[21, 28, 35, 42].map((x) => (
        <rect key={x} x={x - 2} y="21" width="4" height="28" rx="1" fill="var(--emblem-ink)" opacity=".85" />
      ))}
      <rect x="15" y="50" width="34" height="4" rx="1" fill="var(--accent)" />
      <rect x="12" y="55" width="40" height="3" rx="1" fill="var(--emblem-ink)" opacity=".6" />
    </svg>
  );
}

export function Emblem({ name, size = 40 }: { name: string; size?: number }) {
  if (name === "clap") return <Clap size={size} />;
  if (name === "hemicycle") return <Hemicycle size={size} />;
  return <Column size={size} />;
}
