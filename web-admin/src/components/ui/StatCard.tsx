import clsx from "clsx";

export default function StatCard({
  label,
  hint,
  value,
  tone = "default",
}: {
  label: string;
  hint?: string;
  value: string | number;
  tone?: "default" | "green" | "blue" | "amber" | "red";
}) {
  const tones = {
    default: "text-slate-900",
    green: "text-green-600",
    blue: "text-brand-600",
    amber: "text-amber-600",
    red: "text-red-600",
  };
  return (
    <div className="card py-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={clsx("mt-1 text-2xl font-bold tabular-nums", tones[tone])}>{value}</p>
      {hint ? <p className="mt-1 text-[11px] leading-snug text-slate-400">{hint}</p> : null}
    </div>
  );
}
