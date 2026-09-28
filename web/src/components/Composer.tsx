import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef } from "react";

export function Composer(props: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
  placeholder: string;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [props.value]);

  useEffect(() => {
    if (props.autoFocus) ref.current?.focus();
  }, [props.autoFocus]);

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        props.onSend();
      }}
    >
      <textarea
        ref={ref}
        value={props.value}
        rows={1}
        placeholder={props.placeholder}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            props.onSend();
          }
        }}
      />
      {props.busy ? (
        <button type="button" className="composer__btn" onClick={props.onStop} aria-label="Arrêter">
          <Square size={12} fill="currentColor" strokeWidth={0} />
        </button>
      ) : (
        <button type="submit" className="composer__btn" disabled={!props.value.trim()} aria-label="Envoyer">
          <ArrowUp size={18} strokeWidth={2.25} />
        </button>
      )}
    </form>
  );
}
