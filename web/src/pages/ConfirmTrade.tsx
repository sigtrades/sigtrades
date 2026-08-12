import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";
import Layout from "../components/Layout";

type Peek = {
  ok: boolean;
  action: "confirm" | "reject";
  expired?: boolean;
  broker?: string;
  account_label?: string;
  account_id?: string;
  signal?: {
    symbol?: string;
    side?: string;
    qty?: string | number;
    order_type?: string;
  };
};

type Phase = "loading" | "ready" | "submitting" | "done" | "error";

const publicApi = axios.create({ baseURL: "/api" });

export default function ConfirmTrade() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = useMemo(() => (params.get("token") || "").trim(), [params]);
  const [phase, setPhase] = useState<Phase>("loading");
  const [peek, setPeek] = useState<Peek | null>(null);
  const [error, setError] = useState("");
  const [resultStatus, setResultStatus] = useState("");

  useEffect(() => {
    if (!token) {
      setPhase("error");
      setError(t("confirmTrade.invalidToken"));
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await publicApi.get<Peek>("/public/confirm-trade", { params: { token } });
        if (cancelled) return;
        setPeek(res.data);
        if (res.data.expired) {
          setPhase("error");
          setError(t("confirmTrade.expired"));
          return;
        }
        setPhase("ready");
      } catch {
        if (!cancelled) {
          setPhase("error");
          setError(t("confirmTrade.loadFailed"));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  const submit = async () => {
    if (!token || !peek) return;
    setPhase("submitting");
    setError("");
    try {
      const res = await publicApi.post<{ ok: boolean; status?: string; action?: string }>(
        "/public/confirm-trade",
        { token },
      );
      setResultStatus(res.data.status || res.data.action || "ok");
      setPhase("done");
    } catch (e: unknown) {
      const detail =
        axios.isAxiosError(e) && e.response?.data?.detail
          ? String(e.response.data.detail)
          : "";
      if (detail === "confirmation_expired" || detail === "token_used") {
        setError(t("confirmTrade.expired"));
      } else if (detail === "pending_not_found") {
        setError(t("confirmTrade.notFound"));
      } else if (detail === "dispatch_failed") {
        setError(t("confirmTrade.dispatchFailed"));
      } else {
        setError(t("confirmTrade.submitFailed"));
      }
      setPhase("error");
    }
  };

  const isConfirm = peek?.action !== "reject";
  const signal = peek?.signal;

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <p className="text-sm font-semibold text-brand-700">SigTrades</p>
          <h1 className="mt-3 text-2xl font-bold text-slate-900">
            {isConfirm ? t("confirmTrade.titleConfirm") : t("confirmTrade.titleReject")}
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            {isConfirm ? t("confirmTrade.hintConfirm") : t("confirmTrade.hintReject")}
          </p>

          {phase === "loading" || phase === "submitting" ? (
            <p className="mt-6 text-sm text-slate-500">
              {phase === "submitting" ? t("confirmTrade.submitting") : t("common.loading")}
            </p>
          ) : null}

          {peek && (phase === "ready" || phase === "done") ? (
            <ul className="mt-6 space-y-1.5 text-sm text-slate-700">
              <li>
                {t("confirmTrade.symbol")}: <span className="font-medium">{signal?.symbol || "—"}</span>
              </li>
              <li>
                {t("confirmTrade.side")}: <span className="font-medium">{signal?.side || "—"}</span>
              </li>
              <li>
                {t("confirmTrade.qty")}: <span className="font-medium">{signal?.qty || "—"}</span>
              </li>
              <li>
                {t("confirmTrade.broker")}: <span className="font-medium">{peek.broker || "—"}</span>
              </li>
              <li>
                {t("confirmTrade.account")}:{" "}
                <span className="font-medium">{peek.account_label || peek.account_id || "—"}</span>
              </li>
            </ul>
          ) : null}

          {phase === "ready" ? (
            <button
              type="button"
              className={isConfirm ? "btn-primary mt-8 w-full" : "btn-secondary mt-8 w-full"}
              onClick={() => void submit()}
            >
              {isConfirm ? t("confirmTrade.ctaConfirm") : t("confirmTrade.ctaReject")}
            </button>
          ) : null}

          {phase === "done" ? (
            <div className="mt-8">
              <p className="text-sm font-medium text-profit">
                {isConfirm ? t("confirmTrade.doneConfirm") : t("confirmTrade.doneReject")}
              </p>
              {resultStatus ? (
                <p className="mt-1 text-xs text-slate-500">
                  {t("confirmTrade.status")}: {resultStatus}
                </p>
              ) : null}
              <Link to="/app" className="btn-primary mt-6 inline-flex">
                {t("nav.dashboard")}
              </Link>
            </div>
          ) : null}

          {phase === "error" ? (
            <div className="mt-8">
              <p className="text-sm text-loss">{error || t("confirmTrade.submitFailed")}</p>
              <Link to="/app" className="btn-secondary mt-6 inline-flex">
                {t("nav.dashboard")}
              </Link>
            </div>
          ) : null}
        </div>
      </div>
    </Layout>
  );
}
