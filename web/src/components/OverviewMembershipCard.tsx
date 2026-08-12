import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { navPath } from "../lib/appRoutes";
import { normalizePlanCode, planDisplayName, planTheme } from "../lib/planDisplay";
import { useAuth } from "../store/auth";

type SubscriptionStatus = {
  plan_code: string;
  plan_name: string;
  status: string;
  period_end?: string | null;
  billing_cycle?: string;
  days_remaining?: number | null;
};

function statusBadgeClass(status: string) {
  const s = status.toLowerCase();
  if (["active", "paid", "trialing"].includes(s)) return "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200";
  if (["past_due", "open"].includes(s)) return "bg-rose-50 text-rose-800 ring-1 ring-rose-200";
  return "bg-slate-100 text-slate-700 ring-1 ring-slate-200";
}

export default function OverviewMembershipCard() {
  const { t } = useTranslation();
  const user = useAuth((s) => s.user);
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get("/subscriptions/status")
      .then((r) => {
        if (!cancelled) setStatus(r.data);
      })
      .catch(() => {
        /* 用 auth.user.plan_code 兜底 */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const planCode = normalizePlanCode(status?.plan_code || user?.plan_code);
  const planName = t(`pricing.${planCode}`, { defaultValue: planDisplayName(planCode, status?.plan_name) });
  const theme = planTheme(planCode);
  const rawStatus = (status?.status || (planCode === "free" ? "free" : "active")).toLowerCase();
  const statusKey = `membership.status.${rawStatus}`;
  const statusLabel = t(statusKey) === statusKey ? rawStatus : t(statusKey);
  const isFree = planCode === "free";

  return (
    <div className={`relative overflow-hidden rounded-2xl border p-5 sm:p-6 ${theme.card}`}>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {t("membership.overviewEyebrow")}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <h2 className={`text-2xl font-bold tracking-tight ${theme.title}`}>
              {t("membership.overviewPlan", { plan: planName })}
            </h2>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusBadgeClass(rawStatus)}`}>
              {statusLabel}
            </span>
          </div>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-600">
            {isFree
              ? t("membership.overviewFreeHint")
              : status?.period_end
                ? t("membership.planHint", { date: status.period_end })
                : t("membership.overviewPaidHint", { plan: planName })}
          </p>
          {!isFree && status?.days_remaining != null ? (
            <p className="mt-1.5 text-xs text-slate-500">
              {t("membership.daysLeft", { count: status.days_remaining })}
            </p>
          ) : null}
        </div>

        <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[14rem]">
          {isFree ? (
            <>
              <Link to="/redeem" className={`w-full text-center ${theme.ctaPrimary}`}>
                {t("membership.redeemCode")}
              </Link>
              <Link to="/pricing" className="btn-secondary w-full text-center text-sm">
                {t("membership.overviewViewPricing")}
              </Link>
            </>
          ) : (
            <Link to="/pricing" className={`w-full text-center ${theme.ctaSecondary}`}>
              {t("membership.overviewViewPricing")}
            </Link>
          )}
          <Link to={navPath("membership")} className="btn-ghost w-full text-center text-sm">
            {t("membership.overviewManage")}
          </Link>
        </div>
      </div>
    </div>
  );
}
