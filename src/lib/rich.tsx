import { Fragment, type ReactNode } from "react";

/** **negrita** y `código` dentro de una línea. Todo el texto lo pinta React (escapado).
 * Copiado de Insignia: lo justo para el texto de las lecciones de los carnés. */
export function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  parts.forEach((p, i) => {
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) out.push(<strong key={i}>{p.slice(2, -2)}</strong>);
    else if (p.startsWith("`") && p.endsWith("`") && p.length > 2) out.push(<code key={i} className="mono">{p.slice(1, -1)}</code>);
    else if (p) out.push(<Fragment key={i}>{p}</Fragment>);
  });
  return out;
}

/** Markdown mínimo: párrafos, `# títulos`, listas `-`/`1.` y bloques de código ``` en sus líneas. */
export function RichText({ text, className = "" }: { text: string; className?: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let codeBlock: string[] | null = null;
  const flush = () => {
    if (para.length) {
      blocks.push(<p key={blocks.length}>{para.flatMap((l, i) => (i ? [<br key={`b${i}`} />, ...inline(l)] : inline(l)))}</p>);
      para = [];
    }
    if (list) {
      const items = list.items.map((it, i) => <li key={i}>{inline(it)}</li>);
      blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
      list = null;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (codeBlock !== null) {
      if (line.trim() === "```") {
        blocks.push(
          <pre key={blocks.length} className="rich__code mono">
            {codeBlock.join("\n")}
          </pre>
        );
        codeBlock = null;
      } else codeBlock.push(raw);
      continue;
    }
    const heading = line.match(/^#{1,3}\s+(.*)$/);
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (line.trim().startsWith("```")) {
      flush();
      codeBlock = [];
    } else if (!line.trim()) flush();
    else if (heading) {
      flush();
      blocks.push(<h3 key={blocks.length}>{inline(heading[1])}</h3>);
    } else if (bullet || numbered) {
      if (para.length) flush();
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flush();
      list = list ?? { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
    } else {
      if (list) flush();
      para.push(line);
    }
  }
  if (codeBlock !== null) blocks.push(<pre key={blocks.length} className="rich__code mono">{codeBlock.join("\n")}</pre>);
  flush();
  return <div className={`rich ${className}`}>{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>;
}

/** Variante en línea (sin bloques): para opciones, pasos a ordenar y soluciones. */
export function InlineRich({ text }: { text: string }) {
  return <>{inline(text)}</>;
}
