import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { useAuth } from "../store/auth";
import { navPath } from "../lib/appRoutes";
import { formatEtDateTime } from "../lib/datetime";

type RedeemResult = {
  plan_code?: string;
  membership_days?: number | null;
  period_end?: string | null;
  redeemed_at?: string | null;
  already_redeemed?: boolean;
  status?: string;
  code?: string;
};

function formatPeriodEnd(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export default function RedeemCode() {
  const { t, i18n } = useTranslation();
  const isZh = !String(i18n.language || "zh").toLowerCase().startsWith("en");
  const { user, isHydrating } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initial = (params.get("code") || "").trim();
  const [code, setCode] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RedeemResult | null>(null);
  const [autoTried, setAutoTried] = useState(false);

  const redeem = async (value: string) => {
    const trimmed = value.trim();
    if (trimmed.length < 4) {
      setError(isZh ? "请输入有效兑换码" : "Enter a valid code");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("/config/promotions/redeem", { code: trimmed });
      setResult(res.data?.data || res.data || {});
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (isZh ? "兑换失败" : "Redeem failed");
      setError(String(detail));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (isHydrating || !user || !initial || autoTried || result) return;
    setAutoTried(true);
    void redeem(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHydrating, user, initial, autoTried, result]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/redeem?code=${encodeURIComponent(code.trim())}`)}`);
      return;
    }
    void redeem(code);
  };

  const already = Boolean(result?.already_redeemed);

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-12">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">
          {isZh ? "兑换会员码" : "Redeem membership code"}
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          {isZh
            ? "合作产品权益需在此登录后兑换，不会自动开户。"
            : "Partner benefits require login here. No automatic account linking."}
        </p>

        {result ? (
          <div
            className={`mt-6 space-y-3 rounded-xl px-4 py-3 text-sm ${
              already
                ? "bg-slate-50 text-slate-800"
                : "bg-emerald-50 text-emerald-900"
            }`}
          >
            <p className="font-medium">
              {already
                ? isZh
                  ? "该码您已兑换"
                  : "Already redeemed"
                : isZh
                  ? "兑换成功"
                  : "Redeemed"}
            </p>
            <p>
              {isZh ? "状态" : "Status"}:{" "}
              <span className="font-medium">
                {already
                  ? isZh
                    ? "已兑换"
                    : "Redeemed"
                  : isZh
                    ? "兑换成功"
                    : "Success"}
              </span>
            </p>
            {result.plan_code ? (
              <p>
                {isZh ? "套餐" : "Plan"}:{" "}
                <span className="font-mono uppercase">{result.plan_code}</span>
                {result.membership_days != null ? (
                  <>
                    {" · "}
                    {isZh ? `约 ${result.membership_days} 天` : `~${result.membership_days} days`}
                  </>
                ) : null}
              </p>
            ) : null}
            {result.redeemed_at ? (
              <p>
                {isZh ? "兑换时间" : "Redeemed at"}: {formatEtDateTime(result.redeemed_at)}
              </p>
            ) : null}
            {result.period_end ? (
              <p>
                {isZh ? "到期日" : "Valid until"}: {formatPeriodEnd(result.period_end)}
              </p>
            ) : null}
            <Link to={navPath("membership")} className="inline-block text-brand-700 hover:underline">
              {isZh ? "查看会员" : "View membership"}
            </Link>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <label className="block text-sm font-medium text-slate-700">
              {isZh ? "兑换码" : "Code"}
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="xxxx…"
                autoComplete="off"
              />
            </label>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {!user && !isHydrating ? (
              <p className="text-sm text-slate-500">
                {isZh ? "兑换前需要登录 SigTrades 账号。" : "Sign in to SigTrades before redeeming."}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {busy
                ? "…"
                : user
                  ? isZh
                    ? "立即兑换"
                    : "Redeem"
                  : isZh
                    ? "登录并兑换"
                    : "Sign in & redeem"}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-xs text-slate-400">
          <Link to="/" className="hover:underline">
            {t("common.backHome", { defaultValue: isZh ? "返回首页" : "Home" })}
          </Link>
        </p>
      </div>
    </div>
  );
}
