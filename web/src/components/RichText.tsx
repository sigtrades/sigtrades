/** 支持 `**加粗**` 与换行的轻量文案渲染（用于隐私协议、安全说明等）。 */
export default function RichText({
  text,
  className,
  strongClassName = "font-semibold text-slate-900",
}: {
  text: string;
  className?: string;
  strongClassName?: string;
}) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <p className={className}>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className={strongClassName}>
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}
