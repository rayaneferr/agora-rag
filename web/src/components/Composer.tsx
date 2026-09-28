import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef } from "react";

export function Composer(props: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
  /** Archives pas encore prêtes : on garde le champ visible, mais inactif. */
  disabled?: boolean;
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
    if (props.autoFocus && !props.disabled) ref.current?.focus();
  }, [props.autoFocus, props.disabled]);

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
        disabled={props.disabled}
        aria-label="Message"
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
        <button
          type="submit"
          className="composer__btn"
          disabled={props.disabled || !props.value.trim()}
          aria-label="Envoyer"
        >
          <ArrowUp size={18} strokeWidth={2.25} />
        </button>
      )}
    </form>
  );
}
