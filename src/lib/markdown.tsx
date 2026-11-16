import { Fragment, type ReactNode } from "react";

/**
 * Markdown mínimo para las respuestas del asistente: párrafos, saltos de línea, listas (- * 1.),
 * **negrita**, *cursiva*, `código` y enlaces [texto](http…). Construye elementos React, NUNCA
 * HTML: la respuesta del LLM está anclada en contenido de terceros y no se confía
 * en ella. Enlaces solo http(s) — cualquier otro esquema (javascript:, data:) queda como texto.
 * Sin dependencias a propósito (cadena de suministro): cubre lo que producen las respuestas.
 */

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] };

const UL_ITEM = /^\s*[-*•]\s+(.*)$/;
const OL_ITEM = /^\s*\d+[.)]\s+(.*)$/;
const INLINE = /(\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)|\*([^*\s][^*]*)\*|_([^_\s][^_]*)_)/;

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.replace(/^#{1,6}\s+/, ""); // los títulos se muestran como texto normal
    const last = blocks[blocks.length - 1];
    const ul = UL_ITEM.exec(line);
    const ol = ul ? null : OL_ITEM.exec(line);
    if (ul) {
      if (last?.kind === "ul") last.items.push(ul[1]);
      else blocks.push({ kind: "ul", items: [ul[1]] });
    } else if (ol) {
      if (last?.kind === "ol") last.items.push(ol[1]);
      else blocks.push({ kind: "ol", items: [ol[1]] });
    } else if (line.trim() === "") {
      blocks.push({ kind: "p", lines: [] }); // separador; los vacíos se descartan abajo
    } else if (last?.kind === "p") {
      last.lines.push(line);
    } else {
      blocks.push({ kind: "p", lines: [line] });
    }
  }
  return blocks.filter((b) => (b.kind === "p" ? b.lines.length > 0 : b.items.length > 0));
}

export function isSafeHref(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

export function renderInline(text: string, keyPrefix = "i"): ReactNode[] {
  const out: ReactNode[] = [];
  let rest = text;
  let n = 0;
  while (rest) {
    const m = INLINE.exec(rest);
    if (!m) {
      out.push(rest);
      break;
    }
    if (m.index > 0) out.push(rest.slice(0, m.index));
    const key = `${keyPrefix}-${n++}`;
    const [, , bold1, bold2, code, linkText, href, em1, em2] = m;
    if (bold1 ?? bold2) out.push(<strong key={key}>{renderInline(bold1 ?? bold2, key)}</strong>);
    else if (code) out.push(<code key={key} className="rounded bg-white/10 px-1">{code}</code>);
    else if (linkText !== undefined && href !== undefined)
      out.push(
        isSafeHref(href) ? (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer" className="underline">
            {linkText}
          </a>
        ) : (
          <Fragment key={key}>{linkText}</Fragment>
        ),
      );
    else out.push(<em key={key}>{renderInline(em1 ?? em2, key)}</em>);
    rest = rest.slice(m.index + m[0].length);
  }
  return out;
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      {parseBlocks(text).map((block, i) => {
        if (block.kind === "p")
          return (
            <p key={i}>
              {block.lines.map((line, j) => (
                <Fragment key={j}>
                  {j > 0 && <br />}
                  {renderInline(line, `${i}-${j}`)}
                </Fragment>
              ))}
            </p>
          );
        const List = block.kind === "ul" ? "ul" : "ol";
        return (
          <List key={i} className={block.kind === "ul" ? "list-disc pl-5" : "list-decimal pl-5"}>
            {block.items.map((item, j) => (
              <li key={j}>{renderInline(item, `${i}-${j}`)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
