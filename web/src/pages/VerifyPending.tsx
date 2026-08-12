import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import Layout from "../components/Layout";
import { useAuth } from "../store/auth";

export default function VerifyPending() {
  const { t } = useTranslation();
  const { user, isAuthenticated, isHydrating, fetchMe } = useAuth();
  const navigate = useNavigate();
  const [msg, setMsg] = useState("");
  const [msgOk, setMsgOk] = useState(true);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (isAuthenticated) void fetchMe();
  }, [isAuthenticated, fetchMe]);

  useEffect(() => {
    if (user?.email_verified) navigate("/app", { replace: true });
  }, [user, navigate]);

  // 已登录待验证时轮询，用户点完邮件后自动进入
  useEffect(() => {
    if (!isAuthenticated || user?.email_verified) return;
    const id = window.setInterval(() => {
      void fetchMe().catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, [isAuthenticated, user?.email_verified, fetchMe]);

  const startCooldown = (sec = 60) => {
    setCooldown(sec);
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = window.setInterval(() => {
      setCooldown((s) => {
        if (s <= 1) {
          if (timerRef.current) window.clearInterval(timerRef.current);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  };

  const resend = async () => {
    if (!user?.email || busy || cooldown > 0) return;
    setBusy(true);
    setMsg("");
    try {
      await api.post("/auth/resend-verification", { email: user.email });
      setMsgOk(true);
      setMsg(t("auth.verifySent"));
      startCooldown(60);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      setMsgOk(false);
      if (status === 429) {
        startCooldown(60);
        setMsg(t("auth.verifyCooldown"));
      } else {
        setMsg(t("auth.verifyError"));
      }
    } finally {
      setBusy(false);
    }
  };

  if (isHydrating) {
    return (
      <Layout>
        <div className="mx-auto max-w-md px-4 py-16 text-center text-sm text-slate-500">…</div>
      </Layout>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card text-center">
          <h1 className="text-2xl font-bold text-slate-900">{t("auth.verifyTitle")}</h1>
          <p className="mt-4 text-sm leading-relaxed text-slate-600">{t("auth.verifyHint")}</p>
          <p className="mt-3 font-mono text-sm text-brand-600">{user?.email}</p>
          <button
            type="button"
            onClick={resend}
            disabled={busy || cooldown > 0}
            className="btn-primary mt-6 px-5 py-2.5 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {cooldown > 0 ? t("auth.resendVerifyIn", { sec: cooldown }) : t("auth.resendVerify")}
          </button>
          {msg ? (
            <p className={`mt-4 text-sm ${msgOk ? "text-slate-600" : "text-loss"}`}>{msg}</p>
          ) : null}
          <p className="mt-8 text-sm text-slate-500">{t("auth.verifyPendingTip")}</p>
          <p className="mt-4 text-sm">
            <Link to="/login" className="text-brand-600 hover:underline">
              {t("nav.login")}
            </Link>
          </p>
        </div>
      </div>
    </Layout>
  );
}
