import { Link } from "react-router-dom";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import { useAuth } from "../store/auth";
import { navPath } from "../lib/appRoutes";

export default function MembershipSuccess() {
  const { t } = useTranslation();
  const { fetchMe } = useAuth();

  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);

  return (
    <Layout>
      <div className="card mx-auto max-w-lg px-4 py-20 text-center">
        <h1 className="text-3xl font-bold text-brand-600">{t("membership.successTitle")}</h1>
        <p className="mt-4 text-slate-600">{t("membership.successHint")}</p>
        <Link to={navPath("membership")} className="btn-primary mt-8 inline-block">{t("nav.dashboard")}</Link>
      </div>
    </Layout>
  );
}
