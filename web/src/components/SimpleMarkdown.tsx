import { Fragment, type ReactNode } from "react";

/** 轻量 Markdown：标题 / 分隔线 / 列表 / 粗体，用于风险揭示书展示。 */
export default function SimpleMarkdown({ source }: { source: string }) {
  const blocks = source.replace(/\r\n/g, "\n").split(/\n{2,}/);
  return (
    <div className="space-y-4 text-sm leading-relaxed text-slate-700">
      {blocks.map((block, i) => {
        const trimmed = block.trim();
        if (!trimmed) return null;
        if (/^---+$/.test(trimmed)) {
          return <hr key={i} className="border-slate-200" />;
        }
        if (trimmed.startsWith("# ")) {
          return (
            <h1 key={i} className="text-xl font-bold text-slate-900">
              {inline(trimmed.slice(2))}
            </h1>
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <h2 key={i} className="text-base font-semibold text-slate-900">
              {inline(trimmed.slice(3))}
            </h2>
          );
        }
        if (trimmed.startsWith("### ")) {
          return (
            <h3 key={i} className="text-sm font-semibold text-slate-900">
              {inline(trimmed.slice(4))}
            </h3>
          );
        }
        const lines = trimmed.split("\n");
        if (lines.every((l) => /^[-*]\s+/.test(l.trim()) || !l.trim())) {
          return (
            <ul key={i} className="list-disc space-y-1.5 pl-5">
              {lines
                .map((l) => l.trim())
                .filter(Boolean)
                .map((l, j) => (
                  <li key={j}>{inline(l.replace(/^[-*]\s+/, ""))}</li>
                ))}
            </ul>
          );
        }
        return (
          <p key={i} className="whitespace-pre-line">
            {inline(trimmed)}
          </p>
        );
      })}
    </div>
  );
}

function inline(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
