import { useEffect, useRef, useState } from "react";

type DayNightMode = "day" | "night" | "auto";

type Props = {
  value: DayNightMode;
  onChange: (mode: DayNightMode) => void;
};

const OPTIONS: Array<{ id: DayNightMode; emoji: string; label: string }> = [
  { id: "day", emoji: "☀️", label: "Modo claro" },
  { id: "night", emoji: "🌙", label: "Modo oscuro" },
  { id: "auto", emoji: "🌘", label: "Automático" },
];

export function AppearanceToggle({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = OPTIONS.find((o) => o.id === value) ?? OPTIONS[0];

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div
      ref={rootRef}
      className={`appearance-toggle${open ? " is-open" : ""}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="appearance-toggle__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="appearance-toggle-menu"
        title={`${active.label} — cambiar tema`}
        aria-label={`Tema actual: ${active.label}. Abrir opciones`}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden>{active.emoji}</span>
      </button>
      <div
        id="appearance-toggle-menu"
        className="appearance-toggle__menu"
        role="listbox"
        aria-label="Tema"
        aria-hidden={!open}
      >
        {OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="option"
            aria-selected={value === opt.id}
            className={`appearance-toggle__btn${value === opt.id ? " is-active" : ""}`}
            title={opt.label}
            aria-label={opt.label}
            onClick={() => {
              onChange(opt.id);
              setOpen(false);
            }}
          >
            <span aria-hidden>{opt.emoji}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export type { DayNightMode };
