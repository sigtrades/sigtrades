import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import api from "../lib/api";
import Layout from "../components/Layout";
import GoogleLoginButton from "../components/GoogleLoginButton";
import { useAuth } from "../store/auth";

const REQUIRE_VERIFY = import.meta.env.VITE_REQUIRE_EMAIL_VERIFICATION === "true";
const HAS_GOOGLE = !!import.meta.env.VITE_GOOGLE_CLIENT_ID;

export default function Register() {
  const { t } = useTranslation();
  const register = useAuth((s) => s.register);
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState("");
  const [verifySent, setVerifySent] = useState(true);
  const [resendBusy, setResendBusy] = useState(false);
  const [resendMsg, setResendMsg] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

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

  const goAfterAuth = (verified?: boolean) => {
    if (REQUIRE_VERIFY && verified === false) {
      navigate("/verify-pending", { replace: true });
    } else {
      navigate("/app", { replace: true });
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError(t("auth.passwordTooShort"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    if (!agreedToTerms) {
      setError(t("auth.agreeTermsRequired"));
      return;
    }
    setBusy(true);
    try {
      const result = await register(email, password);
      if (REQUIRE_VERIFY && result.email_verified === false) {
        setRegisteredEmail(email.trim());
        setVerifySent(result.verify_email_sent !== false);
        setSuccess(true);
        startCooldown(60);
        return;
      }
      goAfterAuth(result.email_verified);
    } catch {
      setError(t("auth.registerFailed"));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!registeredEmail || resendBusy || cooldown > 0) return;
    setResendBusy(true);
    setResendMsg("");
    try {
      await api.post("/auth/resend-verification", { email: registeredEmail });
      setResendMsg(t("auth.verifySent"));
      startCooldown(60);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 429) {
        startCooldown(60);
        setResendMsg(t("auth.verifyCooldown"));
      } else {
        setResendMsg(t("auth.verifyError"));
      }
    } finally {
      setResendBusy(false);
    }
  };

  if (success) {
    return (
      <Layout>
        <div className="mx-auto max-w-md px-4 py-16">
          <div className="card text-center">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-7 w-7" aria-hidden>
                <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">{t("auth.registerSuccess")}</h1>
            <p className="mt-3 text-sm text-slate-600">{t("auth.verificationSent")}</p>
            <p className="mt-2 font-mono text-sm text-brand-600">{registeredEmail}</p>
            {!verifySent ? (
              <p className="mt-3 text-sm text-amber-700">{t("auth.verifySendFailed")}</p>
            ) : null}
            <button
              type="button"
              onClick={resend}
              disabled={resendBusy || cooldown > 0}
              className="btn-secondary mt-6 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cooldown > 0 ? t("auth.resendVerifyIn", { sec: cooldown }) : t("auth.resendVerify")}
            </button>
            {resendMsg ? <p className="mt-3 text-sm text-slate-600">{resendMsg}</p> : null}
            <p className="mt-8 text-sm text-slate-600">
              <Link to="/verify-pending" className="text-brand-600 hover:underline">
                {t("auth.goVerifyPending")}
              </Link>
              <span className="mx-2 text-slate-300">·</span>
              <Link to="/login" className="text-brand-600 hover:underline">
                {t("nav.login")}
              </Link>
            </p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-slate-900">{t("auth.registerTitle")}</h1>
            <p className="mt-2 text-sm text-slate-500">{t("auth.registerSubtitle")}</p>
          </div>

          {error && (
            <p className="mb-4 rounded-lg border border-loss/20 bg-loss/5 px-3 py-2 text-sm text-loss">
              {error}
            </p>
          )}

          {HAS_GOOGLE && (
            <>
              {/* 点 Google 即视为同意条款并自动勾选，避免二次提示 */}
              <div
                onPointerDown={() => {
                  setAgreedToTerms(true);
                  setError("");
                }}
              >
                <GoogleLoginButton
                  mode="register"
                  onSuccess={() => goAfterAuth(true)}
                  onError={setError}
                />
              </div>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-slate-400">{t("auth.orContinueWithEmail")}</span>
                </div>
              </div>
            </>
          )}

          <form onSubmit={onSubmit} className="space-y-4">
            <input
              type="email"
              required
              className="input w-full"
              placeholder={t("auth.email")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              onFocus={() => setError("")}
            />
            <div>
              <input
                type="password"
                required
                minLength={8}
                className="input w-full"
                placeholder={t("auth.password")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                onFocus={() => setError("")}
              />
              <p className="mt-1.5 text-xs text-slate-400">{t("auth.passwordHint")}</p>
            </div>
            <input
              type="password"
              required
              minLength={8}
              className="input w-full"
              placeholder={t("auth.confirmPasswordPlaceholder")}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              onFocus={() => setError("")}
            />

            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                checked={agreedToTerms}
                onChange={(e) => {
                  setAgreedToTerms(e.target.checked);
                  setError("");
                }}
              />
              <span className="text-xs leading-relaxed text-slate-500">
                <Trans
                  i18nKey="auth.agreeTerms"
                  components={{
                    terms: (
                      <Link
                        to="/legal/terms"
                        target="_blank"
                        className="text-brand-600 underline hover:text-brand-700"
                      />
                    ),
                    privacy: (
                      <Link
                        to="/legal/privacy"
                        target="_blank"
                        className="text-brand-600 underline hover:text-brand-700"
                      />
                    ),
                  }}
                />
              </span>
            </label>

            <button
              type="submit"
              disabled={busy || !agreedToTerms}
              className="btn-primary w-full py-2.5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? t("auth.registering") : t("auth.submitRegister")}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            {t("auth.hasAccount")}{" "}
            <Link to="/login" className="text-brand-600 hover:underline">
              {t("nav.login")}
            </Link>
          </p>
        </div>
      </div>
    </Layout>
  );
}
