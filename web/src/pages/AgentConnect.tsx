import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import GoogleLoginButton from "../components/GoogleLoginButton";
import api from "../lib/api";
import { formatApiError } from "../lib/apiError";
import { useAuth } from "../store/auth";

type ConnectInfo = {
  device_id: string;
  relay_url: string;
};

/** 自定义协议唤起桌面 Agent（需安装已注册协议的 Agent 包） */
const AGENT_APP_DEEP_LINK = "sigtrades-agent://open";

export default function AgentConnect() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const state = searchParams.get("state") ?? "";
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  const login = useAuth((s) => s.login);
  const user = useAuth((s) => s.user);
  const loggedIn = isAuthenticated && !!user;

  const [info, setInfo] = useState<ConnectInfo | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!state) {
      setError(t("agentConnect.invalidState"));
      return;
    }
    api.get("/agent-connect/info", { params: { state } })
      .then((r) => setInfo(r.data))
      .catch(() => setError(t("agentConnect.invalidState")));
  }, [state, t]);

  const onLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await login(email, password);
    } catch {
      setError(t("auth.loginFailed"));
    }
  };

  const onGoogleOk = () => {};

  const authorize = async () => {
    if (!state) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/agent-connect/authorize", { state });
      // Agent 通过 poll 领取 token；浏览器留在本页，不跳转本机 17890 UI
      setDone(true);
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  if (!state) {
    return (
      <Layout>
        <div className="mx-auto max-w-md px-4 py-16 text-center text-sm text-slate-600">
          {t("agentConnect.invalidState")}
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <h1 className="text-2xl font-bold text-slate-900">{t("agentConnect.title")}</h1>
          <p className="mt-2 text-sm text-slate-600">{t("agentConnect.subtitle")}</p>

          {info && (
            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
              <p>{t("agentConnect.device")}: <span className="font-mono">{info.device_id}</span></p>
            </div>
          )}

          {done ? (
            <div className="mt-6 space-y-3">
              <p className="text-sm text-profit">{t("agentConnect.redirecting")}</p>
              <a
                href={AGENT_APP_DEEP_LINK}
                className="btn-primary flex w-full items-center justify-center py-2.5"
              >
                {t("agentConnect.openAgent")}
              </a>
              <button
                type="button"
                className="btn-secondary w-full py-2.5"
                onClick={() => navigate("/app")}
              >
                {t("agentConnect.backToApp")}
              </button>
              <p className="text-center text-xs text-slate-400">{t("agentConnect.openAgentHint")}</p>
            </div>
          ) : !loggedIn ? (
            <div className="mt-6">
              <p className="mb-4 text-sm text-slate-600">{t("agentConnect.loginFirst")}</p>
              {import.meta.env.VITE_GOOGLE_CLIENT_ID && (
                <GoogleLoginButton onSuccess={onGoogleOk} onError={setError} />
              )}
              <form onSubmit={onLogin} className="mt-4 space-y-3">
                <input
                  type="email"
                  className="input w-full"
                  placeholder={t("auth.email")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <input
                  type="password"
                  className="input w-full"
                  placeholder={t("auth.password")}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button type="submit" className="btn-primary w-full py-2.5">{t("auth.submitLogin")}</button>
              </form>
              <p className="mt-3 text-sm text-slate-600">
                <Link to="/register" className="text-brand-600 hover:underline">{t("nav.signup")}</Link>
              </p>
            </div>
          ) : (
            <div className="mt-6">
              <p className="text-sm text-slate-600">
                {t("agentConnect.loggedInAs")} <span className="font-medium">{user?.email}</span>
              </p>
              <button
                type="button"
                className="btn-primary mt-4 w-full py-2.5"
                disabled={busy || !info}
                onClick={() => void authorize()}
              >
                {busy ? t("agentConnect.authorizing") : t("agentConnect.authorize")}
              </button>
              <button
                type="button"
                className="btn-secondary mt-2 w-full"
                onClick={() => navigate("/app")}
              >
                {t("agentConnect.cancel")}
              </button>
            </div>
          )}

          {error && <p className="mt-4 text-sm text-loss">{error}</p>}
        </div>
      </div>
    </Layout>
  );
}
