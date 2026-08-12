import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import GoogleLoginButton from "../components/GoogleLoginButton";
import { useAuth } from "../store/auth";

const REQUIRE_VERIFY = import.meta.env.VITE_REQUIRE_EMAIL_VERIFICATION === "true";
const HAS_GOOGLE = !!import.meta.env.VITE_GOOGLE_CLIENT_ID;

export default function Login() {
  const { t } = useTranslation();
  const login = useAuth((s) => s.login);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const goAfterAuth = () => {
    const user = useAuth.getState().user;
    const next = (searchParams.get("next") || "").trim();
    if (REQUIRE_VERIFY && user && !user.email_verified) {
      navigate("/verify-pending", { replace: true });
    } else if (next.startsWith("/") && !next.startsWith("//")) {
      navigate(next, { replace: true });
    } else {
      navigate("/app", { replace: true });
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await login(email, password);
      goAfterAuth();
    } catch {
      setError(t("auth.loginFailed"));
    }
  };

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-slate-900">{t("auth.loginTitle")}</h1>
            <p className="mt-2 text-sm text-slate-500">{t("auth.loginSubtitle")}</p>
          </div>

          {error && (
            <p className="mb-4 rounded-lg border border-loss/20 bg-loss/5 px-3 py-2 text-sm text-loss">
              {error}
            </p>
          )}

          {HAS_GOOGLE && (
            <>
              <GoogleLoginButton mode="login" onSuccess={goAfterAuth} onError={setError} />
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
              className="input w-full"
              placeholder={t("auth.email")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onFocus={() => setError("")}
            />
            <input
              type="password"
              className="input w-full"
              placeholder={t("auth.password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              onFocus={() => setError("")}
            />
            <div className="flex justify-end">
              <Link to="/forgot-password" className="text-sm text-brand-600 hover:underline">
                {t("auth.forgotLink")}
              </Link>
            </div>
            <button type="submit" className="btn-primary w-full py-2.5">
              {t("auth.submitLogin")}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            {t("auth.noAccount")}{" "}
            <Link to="/register" className="text-brand-600 hover:underline">
              {t("nav.signup")}
            </Link>
          </p>
        </div>
      </div>
    </Layout>
  );
}
