import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { navPath } from "../lib/appRoutes";
import { normalizePlanCode, planDisplayName } from "../lib/planDisplay";

type SubscriptionStatus = {
  plan_code: string;
  plan_name: string;
  status: string;
  period_end?: string | null;
  billing_cycle: string;
  days_remaining?: number | null;
  stripe_configured: boolean;
  has_stripe_customer: boolean;
};

type PaymentMethod = {
  brand?: string;
  last4?: string;
  exp_month?: number;
  exp_year?: number;
  type?: string;
  label?: string;
  email?: string;
} | null;

type Invoice = {
  id: string;
  date?: string | null;
  description: string;
  status: string;
  amount: number;
  currency: string;
  hosted_invoice_url?: string | null;
};

function statusBadgeClass(status: string) {
  const s = status.toLowerCase();
  if (["active", "paid", "trialing"].includes(s)) return "badge-success";
  if (["past_due", "open"].includes(s)) return "badge-danger";
  return "badge-neutral";
}

export default function MembershipBillingSection() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [portalBusy, setPortalBusy] = useState(false);

  const now = new Date();
  const [billYear, setBillYear] = useState(now.getFullYear());
  const [billMonth, setBillMonth] = useState(now.getMonth() + 1);

  const monthOptions = useMemo(() => {
    const opts: { year: number; month: number; label: string }[] = [];
    for (let i = 0; i < 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      opts.push({
        year: d.getFullYear(),
        month: d.getMonth() + 1,
        label: t("membership.billMonth", { year: d.getFullYear(), month: d.getMonth() + 1 }),
      });
    }
    return opts;
  }, [now, t]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      let nextStatus: SubscriptionStatus | null = null;
      try {
        const statusRes = await api.get("/subscriptions/status");
        nextStatus = statusRes.data;
        setStatus(nextStatus);
      } catch {
        /* keep previous status */
      }

      const legacy = Boolean(nextStatus?.stripe_configured && nextStatus?.has_stripe_customer);
      if (!legacy) {
        setPaymentMethod(null);
        setInvoices([]);
        return;
      }
      try {
        const pmRes = await api.get("/subscriptions/payment-method");
        setPaymentMethod(pmRes.data.method);
      } catch {
        setPaymentMethod(null);
      }
      try {
        const invRes = await api.get("/subscriptions/invoices", {
          params: { year: billYear, month: billMonth },
        });
        setInvoices(invRes.data.items || []);
      } catch {
        setInvoices([]);
      }
    } finally {
      setLoading(false);
    }
  }, [billYear, billMonth]);

  useEffect(() => {
    void load();
  }, [load]);

  const showLegacyBilling = Boolean(status?.stripe_configured && status?.has_stripe_customer);

  const openPortal = async () => {
    setPortalBusy(true);
    try {
      const origin = window.location.origin;
      const { data } = await api.post("/subscriptions/portal", {
        return_url: `${origin}${navPath("membership")}`,
      });
      window.location.href = data.url;
    } finally {
      setPortalBusy(false);
    }
  };

  const statusLabel = (s: string) => {
    const key = `membership.status.${s.toLowerCase()}`;
    const translated = t(key);
    return translated === key ? s : translated;
  };

  const cycleLabel = (cycle: string) => {
    const key = `membership.cycle.${cycle}`;
    const translated = t(key);
    return translated === key ? cycle : translated;
  };

  if (loading && !status) {
    return <p className="py-8 text-sm text-slate-500">{t("common.loading")}</p>;
  }

  const planCode = normalizePlanCode(status?.plan_code);
  const planName = t(`pricing.${planCode}`, { defaultValue: planDisplayName(status?.plan_code, status?.plan_name) });
  const isTrial = status?.status === "trialing";
  const isFree = planCode === "free";

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-brand-200 bg-gradient-to-br from-brand-50 to-white px-5 py-4">
        <h3 className="font-semibold text-brand-900">{t("membership.redeemTitle")}</h3>
        <p className="mt-1 text-sm leading-relaxed text-brand-800">{t("membership.redeemHint")}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link to="/redeem" className="btn-primary text-sm">
            {t("membership.redeemCode")}
          </Link>
          <a
            href="https://sunnyquant.com"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary text-sm"
          >
            {t("membership.sunnyquantLink")} ↗
          </a>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold text-slate-900">{planName}</h2>
              {isTrial && <span className="badge bg-sky-100 text-sky-800">{t("membership.trialing")}</span>}
              {status?.status && !isTrial && (
                <span className={`badge ${statusBadgeClass(status.status)}`}>{statusLabel(status.status)}</span>
              )}
            </div>
            {status?.period_end && (
              <p className="mt-2 text-sm text-slate-500">
                {t("membership.planHint", { date: status.period_end })}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/pricing" className="btn-primary text-sm">
              {t("membership.viewPlans")}
            </Link>
            {showLegacyBilling && (
              <button type="button" onClick={() => void openPortal()} disabled={portalBusy} className="btn-secondary text-sm">
                {portalBusy ? t("common.loading") : t("membership.manageBilling")}
              </button>
            )}
          </div>
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">{t("membership.billingCycle")}</p>
            <p className="mt-1 text-sm font-semibold text-slate-900">
              {cycleLabel(
                status?.billing_cycle ??
                  (status?.plan_code && status.plan_code !== "free" ? "gift" : "subscription"),
              )}
            </p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">{t("membership.expiryDate")}</p>
            <p className="mt-1 text-sm font-semibold text-slate-900">{status?.period_end || "—"}</p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
            <p className="text-xs text-slate-500">{t("membership.remaining")}</p>
            <p className="mt-1 text-sm font-semibold text-slate-900">
              {status?.days_remaining != null
                ? t("membership.daysLeft", { count: status.days_remaining })
                : "—"}
            </p>
          </div>
        </div>
      </div>

      {!isFree ? null : (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p>{t("membership.upgradeViaRedeem")}</p>
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <p>{t("membership.supportHint")}</p>
        <a href="mailto:support@sigtrades.com" className="mt-1 inline-flex items-center gap-1 font-medium text-brand-700 hover:underline">
          support@sigtrades.com →
        </a>
      </div>

      {showLegacyBilling ? (
        <>
          <div className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-900">{t("membership.paymentMethod")}</h3>
                <p className="mt-1 text-sm text-slate-500">{t("membership.paymentMethodHintLegacy")}</p>
              </div>
              <button type="button" onClick={() => void openPortal()} disabled={portalBusy} className="btn-secondary text-sm">
                {portalBusy ? t("common.loading") : t("membership.manageStripe")}
              </button>
            </div>
            <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5">
              {paymentMethod?.label || paymentMethod?.last4 || paymentMethod?.email ? (
                <p className="text-sm font-medium text-slate-800">
                  {paymentMethod.label ||
                    (paymentMethod.last4
                      ? `${(paymentMethod.brand || "Card").toUpperCase()} •••• ${paymentMethod.last4}`
                      : paymentMethod.email
                        ? `Link · ${paymentMethod.email}`
                        : "")}
                  {paymentMethod.last4 && paymentMethod.exp_month && paymentMethod.exp_year ? (
                    <span className="ml-2 text-slate-500">
                      {paymentMethod.exp_month}/{paymentMethod.exp_year}
                    </span>
                  ) : null}
                </p>
              ) : (
                <p className="text-sm text-slate-500">{t("membership.noPaymentMethod")}</p>
              )}
            </div>
          </div>

          <div className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-900">{t("membership.bills")}</h3>
                <p className="mt-1 text-sm text-slate-500">{t("membership.billsHintLegacy")}</p>
              </div>
              <select
                value={`${billYear}-${billMonth}`}
                onChange={(e) => {
                  const [y, m] = e.target.value.split("-").map(Number);
                  setBillYear(y);
                  setBillMonth(m);
                }}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                {monthOptions.map((opt) => (
                  <option key={`${opt.year}-${opt.month}`} value={`${opt.year}-${opt.month}`}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-xs text-slate-500">
                    <th className="py-2 pr-4 font-medium">{t("membership.colDate")}</th>
                    <th className="py-2 pr-4 font-medium">{t("membership.colDesc")}</th>
                    <th className="py-2 pr-4 font-medium">{t("membership.colStatus")}</th>
                    <th className="py-2 pr-4 font-medium">{t("membership.colAmount")}</th>
                    <th className="py-2 font-medium">{t("membership.colInvoice")}</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.id} className="border-b border-slate-50">
                      <td className="py-3 pr-4 text-slate-700">{inv.date || "—"}</td>
                      <td className="py-3 pr-4 text-slate-700">{inv.description}</td>
                      <td className="py-3 pr-4">
                        <span className={`badge text-[10px] ${statusBadgeClass(inv.status)}`}>
                          {statusLabel(inv.status)}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-slate-700">
                        {inv.amount.toFixed(2)} {inv.currency}
                      </td>
                      <td className="py-3">
                        {inv.hosted_invoice_url ? (
                          <a
                            href={inv.hosted_invoice_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-brand-600 hover:underline"
                          >
                            {t("membership.viewInvoice")} ↗
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                  {invoices.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-6 text-center text-slate-500">
                        {t("membership.noBills")}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
