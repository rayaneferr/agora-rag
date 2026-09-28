import { Clapperboard, Landmark, type LucideIcon, MessageSquare } from "lucide-react";

const ICONS: Record<string, LucideIcon> = { clap: Clapperboard, hemicycle: Landmark };

/** Icône d'un contexte, sur une pastille teintée de son accent. */
export function ContextIcon({ emblem, size = 32 }: { emblem: string; size?: number }) {
  const Icon = ICONS[emblem] ?? MessageSquare;
  return (
    <span className="ctx-icon" style={{ width: size, height: size }}>
      <Icon size={Math.round(size * 0.5)} strokeWidth={1.75} />
    </span>
  );
}
