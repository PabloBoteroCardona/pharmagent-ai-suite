import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("converts basic markdown formatting to HTML", () => {
    const html = renderMarkdown("**Dosis:** 600 mg cada 8 horas.");
    expect(html).toContain("<strong>Dosis:</strong>");
  });

  it("converts line breaks (breaks: true) instead of requiring a blank line", () => {
    const html = renderMarkdown("Línea uno.\nLínea dos.");
    expect(html).toContain("<br");
  });

  it("strips a raw <script> tag embedded in the LLM response", () => {
    const html = renderMarkdown('Respuesta <script>alert("x")</script> normal.');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("alert(");
  });

  it("strips an inline event handler attribute", () => {
    const html = renderMarkdown('<img src="x" onerror="alert(1)">');
    expect(html).not.toContain("onerror");
  });

  it("strips a javascript: URL", () => {
    const html = renderMarkdown('[enlace](javascript:alert(1))');
    expect(html).not.toContain("javascript:");
  });
});
