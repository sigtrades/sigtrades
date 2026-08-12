import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../lib/api";
import { normalizePlanCode, planDisplayName, planTheme, type PlanCode } from "../lib/planDisplay";
import { useAuth } from "../store/auth";

const SUPPORT_EMAIL = "support@sigtrades.com";

type Plan = {
  code: string;
  name: string;
  features: Record<string, unknown>;
};

/** 前台只展示基础套餐 / 专业版；starter 保留在类型与后台，但不出现在定价页 */
const PLAN_ORDER: PlanCode[] = ["free", "pro"];

type BulletTone = "default" | "limit" | "accent";

function normalizeBullets(raw: unknown): Array<{ text: string; tone: BulletTone }> {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (typeof item === "string") return { text: item, tone: "default" as const };
      if (item && typeof item === "object" && "text" in item) {
        const tone = (item as { tone?: BulletTone }).tone;
        return {
          text: String((item as { text: string }).text),
          tone: tone === "limit" || tone === "accent" ? tone : ("default" as const),
        };
      }
      return null;
    })
    .filter((x): x is { text: string; tone: BulletTone } => Boolean(x?.text));
}

function bulletTextClass(tone: BulletTone, isPro: boolean): string {
  if (tone === "limit") return "font-semibold text-amber-800";
  if (tone === "accent") return isPro ? "font-semibold text-brand-800" : "font-semibold text-brand-700";
  return "text-slate-700";
}

function bulletCheckClass(tone: BulletTone, themeCheck: string): string {
  if (tone === "limit") return "bg-amber-100 text-amber-800";
  if (tone === "accent") return "bg-brand-100 text-brand-800";
  return themeCheck;
}

type SubStatus = {
  plan_code?: string;
};

export default function Pricing() {
  const { t } = useTranslation();
  const { isAuthenticated, user, fetchMe } = useAuth();
  const loggedIn = isAuthenticated && !!user;
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subStatus, setSubStatus] = useState<SubStatus | null>(null);

  useEffect(() => {
    api.get("/plans").then((r) => setPlans(r.data));
    if (isAuthenticated) void fetchMe();
  }, [isAuthenticated, fetchMe]);

  useEffect(() => {
    if (!isAuthenticated) {
      setSubStatus(null);
      return;
    }
    let cancelled = false;
    api
      .get("/subscriptions/status")
      .then((r) => {
        if (!cancelled) setSubStatus(r.data as SubStatus);
      })
      .catch(() => {
        /* ignore */
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const sortedPlans = useMemo(() => {
    const byCode = new Map(plans.map((p) => [normalizePlanCode(p.code), p]));
    return PLAN_ORDER.map((code) => byCode.get(code)).filter(Boolean) as Plan[];
  }, [plans]);

  const currentPlan = normalizePlanCode(user?.plan_code || subStatus?.plan_code);

  return (
    <Layout>
      <div className="mx-auto max-w-6xl px-4 py-14">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">{t("pricing.eyebrow")}</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900 sm:text-4xl">{t("pricing.title")}</h1>
          <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-slate-600">{t("pricing.subtitle")}</p>
        </div>

        <div className="mx-auto mt-10 grid w-full max-w-3xl gap-5 sm:grid-cols-2">
          {sortedPlans.map((p) => {
            const code = normalizePlanCode(p.code);
            const theme = planTheme(code);
            const planName = t(`pricing.${code}`, { defaultValue: planDisplayName(p.code, p.name) });
            const isCurrent = currentPlan === code;
            const isFeatured = code === "pro";
            const bullets = normalizeBullets(t(`pricing.bullets.${code}`, { returnObjects: true }));
            const ctaClass = isFeatured ? theme.ctaPrimary : theme.ctaSecondary;

            return (
              <div
                key={p.code}
                className={`relative flex flex-col rounded-2xl border p-6 shadow-card transition-shadow hover:shadow-pop ${theme.card}`}
              >
                {isFeatured && (
                  <span className={`absolute -top-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-0.5 text-xs font-semibold text-white shadow-sm ${theme.ribbon}`}>
                    {t("pricing.recommended")}
                  </span>
                )}
                {isCurrent && (
                  <span className={`absolute right-4 top-4 rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide ${theme.badge}`}>
                    {t("pricing.currentPlan")}
                  </span>
                )}

                <div className="mt-1">
                  <h2 className={`text-2xl font-bold ${theme.title}`}>{planName}</h2>
                  <p className="mt-2 flex items-baseline gap-1">
                    <span className={`text-2xl font-bold tracking-tight ${theme.price}`}>
                      {code === "free" ? t("pricing.basicIncluded") : t("pricing.proAccess")}
                    </span>
                  </p>
                  <p
                    className={`mt-2 min-h-[2.5rem] text-sm leading-relaxed ${
                      code === "free" ? "font-medium text-amber-900" : isFeatured ? "font-medium text-brand-800" : "text-slate-600"
                    }`}
                  >
                    {t(`pricing.${code}Desc`)}
                  </p>
                </div>

                <ul className="mt-6 flex-1 space-y-3 text-sm">
                  {bullets.map((line) => (
                    <li key={line.text} className="flex items-start gap-2.5">
                      <span
                        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs ${bulletCheckClass(line.tone, theme.check)}`}
                      >
                        {line.tone === "limit" ? "!" : "✓"}
                      </span>
                      <span className={bulletTextClass(line.tone, isFeatured)}>{line.text}</span>
                    </li>
                  ))}
                </ul>

                {code === "free" ? (
                  <Link
                    to={loggedIn ? "/app" : "/register"}
                    className={`mt-8 w-full text-center ${theme.ctaSecondary}`}
                  >
                    {loggedIn ? (isCurrent ? t("pricing.currentUsing") : t("nav.dashboard")) : t("pricing.startFree")}
                  </Link>
                ) : isCurrent ? (
                  <span className={`mt-8 w-full cursor-default text-center opacity-80 ${ctaClass}`}>{t("pricing.currentUsing")}</span>
                ) : (
                  <a href={`mailto:${SUPPORT_EMAIL}`} className={`mt-8 block w-full text-center ${ctaClass}`}>
                    {t("pricing.contactUs")}
                  </a>
                )}
              </div>
            );
          })}
        </div>

        <div className="mx-auto mt-8 max-w-xl rounded-xl border border-brand-200 bg-brand-50/60 px-5 py-4 text-center text-sm text-brand-900">
          <p>{t("pricing.redeemNote")}</p>
          <Link to="/redeem" className="mt-2 inline-block font-semibold text-brand-700 hover:underline">
            {t("pricing.redeemLink")} →
          </Link>
          <span className="mx-2 text-slate-400">·</span>
          <a href={`mailto:${SUPPORT_EMAIL}`} className="font-semibold text-brand-700 hover:underline">
            {t("pricing.contactUs")} →
          </a>
        </div>

        {!loggedIn ? (
          <p className="mx-auto mt-8 max-w-xl text-center text-sm text-slate-500">
            {t("pricing.loginHint")}{" "}
            <Link to="/register" className="font-medium text-brand-600 hover:underline">
              {t("nav.signup")}
            </Link>
          </p>
        ) : null}

        <div className="mx-auto mt-8 max-w-3xl space-y-3 rounded-xl border border-slate-200 bg-white px-5 py-4 text-xs leading-relaxed text-slate-500">
          <p className="rounded-lg border border-brand-100 bg-brand-50/70 px-3 py-2 text-sm text-brand-900">
            {t("pricing.autoTradeNote")}
          </p>
          <p>{t("pricing.billingNote")}</p>
        </div>
      </div>
    </Layout>
  );
}
