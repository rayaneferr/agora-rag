// La chouette d'Agora (générée avec Gemini, fond détouré). L'humeur pilote une légère animation.

type Mood = "idle" | "busy" | "error";

export function Mascot({ size = 40, mood = "idle" }: { size?: number; mood?: Mood }) {
  return <img className={`mascot mascot--${mood}`} src="/mascot.png" width={size} height={size} alt="" />;
}
