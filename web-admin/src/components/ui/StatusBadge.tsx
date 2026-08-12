import clsx from "clsx";

const palette: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  inactive: "bg-slate-100 text-slate-600",
  online: "bg-green-100 text-green-700",
  offline: "bg-slate-100 text-slate-600",
  banned: "bg-red-100 text-red-700",
  pending: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
  success: "bg-green-100 text-green-700",
  default: "bg-slate-100 text-slate-700",
};

export default function StatusBadge({ value, kind }: { value: string | boolean; kind?: string }) {
  const text = typeof value === "boolean" ? (value ? "是" : "否") : value;
  const key = kind || String(text).toLowerCase();
  return (
    <span className={clsx("inline-flex rounded-full px-2 py-0.5 text-xs font-medium", palette[key] || palette.default)}>
      {text}
    </span>
  );
}
