import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import api from "../lib/api";

export default function ResetPassword() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/reset-password", { token, password });
      setDone(true);
    } catch {
      setError(t("auth.resetError"));
    }
  };

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <h1 className="text-2xl font-bold text-slate-900">{t("auth.resetTitle")}</h1>
          {done ? (
            <p className="mt-4 text-slate-600">
              {t("auth.resetSuccess")} <Link to="/login" className="text-brand-600 hover:underline">{t("nav.login")}</Link>
            </p>
          ) : (
            <form onSubmit={submit} className="mt-6 space-y-4">
              <input type="password" required minLength={8} className="input w-full" placeholder={t("auth.password")} value={password} onChange={(e) => setPassword(e.target.value)} />
              {error && <p className="text-sm text-loss">{error}</p>}
              <button type="submit" className="btn-primary w-full" disabled={!token}>{t("auth.resetSubmit")}</button>
            </form>
          )}
        </div>
      </div>
    </Layout>
  );
}
