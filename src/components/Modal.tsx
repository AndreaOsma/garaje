import { useEffect, useRef, type ReactNode } from "react";

type Props = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
};

/** Diálogo modal nativo (<dialog>): foco atrapado, Escape y fondo inerte gratis. */
export function Modal({ title, onClose, children, wide = false }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className={`modal${wide ? " modal--wide" : ""}`}
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal__inner">
        <header className="modal__header">
          <h2 id="modal-title">{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
