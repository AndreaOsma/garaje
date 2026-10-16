import { useEffect, useRef, useState } from "react";

type UiDensity = "minimal" | "detailed";

type Props = {
  value: UiDensity;
  onChange: (mode: UiDensity) => void;
};

const OPTIONS: Array<{ id: UiDensity; icon: string; label: string; hint: string }> = [
  {
    id: "minimal",
    icon: "◫",
    label: "Simple",
    hint: "Lo esencial",
  },
  {
    id: "detailed",
    icon: "▦",
    label: "Detalle",
    hint: "Todo visible",
  },
];

export function DensityToggle({ value, onChange }: Props) {
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
      className={`density-toggle${open ? " is-open" : ""}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="density-toggle__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="density-toggle-menu"
        title={`${active.label} — cambiar densidad`}
        aria-label={`Densidad actual: ${active.label}. Abrir opciones`}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden>{active.icon}</span>
      </button>
      <div
        id="density-toggle-menu"
        className="density-toggle__menu"
        role="listbox"
        aria-label="Densidad de la interfaz"
        aria-hidden={!open}
      >
        {OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="option"
            aria-selected={value === opt.id}
            className={`density-toggle__option${value === opt.id ? " is-active" : ""}`}
            onClick={() => {
              onChange(opt.id);
              setOpen(false);
            }}
          >
            <span className="density-toggle__option-icon" aria-hidden>{opt.icon}</span>
            <span className="density-toggle__option-text">
              <span className="density-toggle__option-label">{opt.label}</span>
              <span className="muted density-toggle__option-hint">{opt.hint}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
