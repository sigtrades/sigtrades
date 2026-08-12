export type PlanCode = "free" | "starter" | "pro";

const PLAN_CODES: PlanCode[] = ["free", "starter", "pro"];

export function normalizePlanCode(code?: string | null): PlanCode {
  const c = (code || "free").toLowerCase();
  if (PLAN_CODES.includes(c as PlanCode)) return c as PlanCode;
  return "free";
}

/** 前台统一展示名（无 i18n 时的英文兜底；组件内优先用 t(`pricing.${code}`)） */
export function planDisplayName(code?: string | null, apiName?: string | null): string {
  const normalized = normalizePlanCode(code);
  const labels: Record<PlanCode, string> = {
    free: "Basic",
    starter: "Starter",
    pro: "Pro",
  };
  const fromApi = apiName?.trim();
  if (fromApi && PLAN_CODES.includes(fromApi.toLowerCase() as PlanCode)) {
    return labels[fromApi.toLowerCase() as PlanCode];
  }
  return labels[normalized];
}

export type PlanTheme = {
  card: string;
  title: string;
  price: string;
  check: string;
  ribbon: string;
  badge: string;
  ctaPrimary: string;
  ctaSecondary: string;
};

export const PLAN_THEMES: Record<PlanCode, PlanTheme> = {
  free: {
    card: "border-slate-200 bg-gradient-to-b from-slate-50 via-white to-white ring-1 ring-slate-100",
    title: "text-slate-800",
    price: "text-slate-900",
    check: "bg-slate-100 text-slate-600",
    ribbon: "bg-slate-500",
    badge: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
    ctaPrimary: "btn-secondary",
    ctaSecondary: "btn-secondary",
  },
  starter: {
    card: "border-emerald-200 bg-gradient-to-b from-emerald-50 via-white to-white ring-1 ring-emerald-100",
    title: "text-emerald-900",
    price: "text-emerald-950",
    check: "bg-emerald-100 text-emerald-700",
    ribbon: "bg-emerald-500",
    badge: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200",
    ctaPrimary: "inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50",
    ctaSecondary: "inline-flex items-center justify-center rounded-lg border border-emerald-200 bg-white px-4 py-2.5 text-sm font-semibold text-emerald-800 transition hover:bg-emerald-50 disabled:opacity-50",
  },
  pro: {
    card: "border-brand-300 bg-gradient-to-b from-brand-50 via-white to-white ring-1 ring-brand-200",
    title: "text-brand-900",
    price: "text-brand-950",
    check: "bg-brand-100 text-brand-700",
    ribbon: "bg-brand-500",
    badge: "bg-brand-50 text-brand-800 ring-1 ring-brand-200",
    ctaPrimary: "btn-primary",
    ctaSecondary: "btn-secondary",
  },
};

export function planTheme(code?: string | null): PlanTheme {
  return PLAN_THEMES[normalizePlanCode(code)];
}
