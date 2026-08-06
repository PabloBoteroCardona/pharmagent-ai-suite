import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ breaks: true });

/** Convierte la síntesis en Markdown del RAG a HTML seguro (sin extensiones async de marked). */
export function renderMarkdown(text: string): string {
  const rawHtml = marked.parse(text, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml);
}
