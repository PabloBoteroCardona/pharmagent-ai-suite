import { describe, expect, it } from "vitest";
import { escapeHtml, latencyBadge, severityBadge, sourceChip, verdictBanner } from "./ui";

describe("escapeHtml", () => {
  it("escapes HTML special characters", () => {
    expect(escapeHtml('<script>alert("x")</script>')).toBe(
      "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
    );
  });

  it("leaves plain text untouched", () => {
    expect(escapeHtml("Ibuprofeno 600mg")).toBe("Ibuprofeno 600mg");
  });
});

describe("severityBadge", () => {
  it("renders the Spanish label for a known severity", () => {
    expect(severityBadge("SEVERE")).toContain("GRAVE");
  });

  it("falls back to the raw value for an unrecognized severity instead of hiding it", () => {
    expect(severityBadge("UNKNOWN")).toContain("UNKNOWN");
  });
});

describe("verdictBanner", () => {
  it("renders the Spanish label for a known verdict", () => {
    expect(verdictBanner("requiere_revision_medica")).toContain("REQUIERE REVISIÓN MÉDICA");
  });

  it("renders the safe verdict label", () => {
    expect(verdictBanner("apto")).toContain("APTO");
  });
});

describe("sourceChip", () => {
  it("labels a cache-sourced result", () => {
    expect(sourceChip("cache")).toContain("Caché vectorial");
  });

  it("labels a live CIMA result", () => {
    expect(sourceChip("live")).toContain("CIMA en vivo");
  });

  it("labels an unverified source", () => {
    expect(sourceChip("none")).toContain("Sin fuente verificada");
  });
});

describe("latencyBadge", () => {
  it("rounds the elapsed time and includes the engine label", () => {
    const html = latencyBadge(342.7, "Groq · Llama 3.1-8b-instant");
    expect(html).toContain("343");
    expect(html).toContain("Groq · Llama 3.1-8b-instant");
  });

  it("escapes the engine label to avoid HTML injection", () => {
    const html = latencyBadge(100, '<img src=x onerror="alert(1)">');
    expect(html).not.toContain("<img");
  });
});
