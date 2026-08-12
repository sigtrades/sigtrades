import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import api from "../lib/api";

export default function ForgotPassword() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch {
      setError(t("auth.forgotError"));
    }
  };

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <h1 className="text-2xl font-bold text-slate-900">{t("auth.forgotTitle")}</h1>
          {sent ? (
            <p className="mt-4 text-slate-600">{t("auth.forgotSent")}</p>
          ) : (
            <form onSubmit={submit} className="mt-6 space-y-4">
              <input type="email" required className="input w-full" placeholder={t("auth.email")} value={email} onChange={(e) => setEmail(e.target.value)} />
              {error && <p className="text-sm text-loss">{error}</p>}
              <button type="submit" className="btn-primary w-full">{t("auth.forgotSubmit")}</button>
            </form>
          )}
          <p className="mt-4 text-sm">
            <Link to="/login" className="text-brand-600 hover:underline">{t("nav.login")}</Link>
          </p>
        </div>
      </div>
    </Layout>
  );
}
