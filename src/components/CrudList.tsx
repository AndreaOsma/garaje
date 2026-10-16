import { useState, type ReactNode } from "react";
import { Modal } from "./Modal";
import { RecordForm, type Field } from "./RecordForm";
import { EmptyState, confirmAndRun } from "./ui";

type Item = { id: number };

type Props<T extends Item> = {
  title: string;
  newLabel: string;
  items: T[];
  fields: Field[];
  detailed: boolean;
  emptyTitle: string;
  emptyHint?: ReactNode;
  newDefaults?: () => Record<string, unknown>;
  renderItem: (item: T) => ReactNode;
  create: (data: Record<string, unknown>) => Promise<unknown>;
  update: (id: number, data: Record<string, unknown>) => Promise<unknown>;
  remove: (id: number) => Promise<unknown>;
  onChanged: () => void;
  describe?: (item: T) => string;
  extraActions?: (item: T) => ReactNode;
  headerExtra?: ReactNode;
};

/** Lista de tarjetas con alta/edición en modal y borrado con confirmación. */
export function CrudList<T extends Item>(props: Props<T>) {
  const [editing, setEditing] = useState<T | "new" | null>(null);
  const close = () => setEditing(null);

  return (
    <section className="panel" aria-label={props.title}>
      <header className="panel__header">
        <h2>{props.title}</h2>
        <div className="panel__actions">
          {props.headerExtra}
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setEditing("new")}>
            + {props.newLabel}
          </button>
        </div>
      </header>

      {props.items.length === 0 ? (
        <EmptyState title={props.emptyTitle}>{props.emptyHint}</EmptyState>
      ) : (
        <ul className="card-list">
          {props.items.map((item) => (
            <li key={item.id} className="card">
              <div className="card__body">{props.renderItem(item)}</div>
              <div className="card__actions">
                {props.extraActions?.(item)}
                <button type="button" className="icon-btn" aria-label="Editar" title="Editar" onClick={() => setEditing(item)}>
                  ✎
                </button>
                <button
                  type="button"
                  className="icon-btn icon-btn--danger"
                  aria-label="Eliminar"
                  title="Eliminar"
                  onClick={() =>
                    confirmAndRun(
                      `¿Eliminar ${props.describe?.(item) ?? "este registro"}?`,
                      () => props.remove(item.id),
                      props.onChanged
                    )
                  }
                >
                  🗑
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <Modal title={editing === "new" ? props.newLabel : "Editar"} onClose={close}>
          <RecordForm
            fields={props.fields}
            detailed={props.detailed}
            initial={editing === "new" ? props.newDefaults?.() : (editing as unknown as Record<string, unknown>)}
            onSubmit={(data) => (editing === "new" ? props.create(data) : props.update(editing.id, data))}
            onDone={() => {
              close();
              props.onChanged();
            }}
            onCancel={close}
          />
        </Modal>
      )}
    </section>
  );
}
