import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Markdown, isSafeHref, parseBlocks } from "./markdown";

const html = (text: string) => renderToStaticMarkup(<Markdown text={text} />);

describe("parseBlocks", () => {
  it("separa párrafos y agrupa listas", () => {
    expect(parseBlocks("Hola\nmundo\n\n- a\n- b\n\n1. uno\n2. dos")).toEqual([
      { kind: "p", lines: ["Hola", "mundo"] },
      { kind: "ul", items: ["a", "b"] },
      { kind: "ol", items: ["uno", "dos"] },
    ]);
  });
});

describe("Markdown", () => {
  it("renderiza negrita, cursiva y código", () => {
    expect(html("**Capital:** Santiago, *capital* y `CLP`")).toBe(
      '<div class="flex flex-col gap-2"><p><strong>Capital:</strong> Santiago, <em>capital</em> y <code class="rounded bg-white/10 px-1">CLP</code></p></div>',
    );
  });

  it("nunca inyecta HTML del texto", () => {
    const out = html('<img src=x onerror="alert(1)"> **<script>x</script>**');
    expect(out).not.toContain("<img");
    expect(out).not.toContain("<script>");
    expect(out).toContain("&lt;img");
  });

  it("solo enlaza http(s); javascript: queda como texto", () => {
    expect(html("[sitio](https://munistgo.cl)")).toContain('href="https://munistgo.cl"');
    const malo = html("[clic](javascript:alert(1))");
    expect(malo).not.toContain("href");
    expect(malo).toContain("clic");
    expect(isSafeHref("data:text/html,x")).toBe(false);
  });

  it("muestra los títulos como texto", () => {
    expect(html("## Trámites")).toBe('<div class="flex flex-col gap-2"><p>Trámites</p></div>');
  });
});
