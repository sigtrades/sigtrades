import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import RichText from "../components/RichText";
import SimpleMarkdown from "../components/SimpleMarkdown";
import api from "../lib/api";

const VALID_DOCS = ["terms", "refund", "privacy", "risk"] as const;
type DocId = (typeof VALID_DOCS)[number];

function isValidDoc(doc?: string): doc is DocId {
  return VALID_DOCS.includes(doc as DocId);
}

export default function Legal() {
  const { doc } = useParams<{ doc: string }>();
  const { t } = useTranslation();
  const valid = isValidDoc(doc);
  const [riskMd, setRiskMd] = useState("");
  const [riskError, setRiskError] = useState("");
  const [riskLoading, setRiskLoading] = useState(false);

  useEffect(() => {
    if (!valid || doc !== "risk") return;
    let cancelled = false;
    setRiskLoading(true);
    setRiskError("");
    api
      .get<{ markdown: string }>("/public/risk-disclosure")
      .then(({ data }) => {
        if (!cancelled) setRiskMd(data.markdown || "");
      })
      .catch(() => {
        if (!cancelled) setRiskError(t("legal.risk.loadFailed"));
      })
      .finally(() => {
        if (!cancelled) setRiskLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [doc, valid, t]);

  if (!valid) return <Navigate to="/legal/terms" replace />;

  const sections = t(`legal.${doc}.sections`, { returnObjects: true }) as { title: string; body: string }[];

  return (
    <Layout>
      <div className="mx-auto max-w-3xl px-4 py-14">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">{t("legal.eyebrow")}</p>
        <h1 className="mt-2 text-3xl font-bold text-slate-900">{t(`legal.${doc}.title`)}</h1>
        <p className="mt-3 text-sm text-slate-500">{t(`legal.${doc}.updated`)}</p>
        <p className="mt-6 text-sm leading-relaxed text-slate-600">{t(`legal.${doc}.intro`)}</p>

        {doc === "risk" ? (
          <div className="mt-10 rounded-xl border border-slate-200 bg-white p-6 shadow-card">
            {riskLoading ? (
              <p className="text-sm text-slate-500">{t("legal.risk.loading")}</p>
            ) : riskError ? (
              <p className="text-sm text-loss">{riskError}</p>
            ) : (
              <SimpleMarkdown source={riskMd} />
            )}
          </div>
        ) : (
          <div className="mt-10 space-y-8">
            {Array.isArray(sections) &&
              sections.map((section, i) => (
                <section key={i} className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
                  <h2 className="text-lg font-semibold text-slate-900">{section.title}</h2>
                  <RichText
                    text={section.body}
                    className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-600"
                    strongClassName="font-semibold text-slate-900"
                  />
                </section>
              ))}
          </div>
        )}

        <nav className="mt-12 flex flex-wrap gap-4 border-t border-slate-200 pt-8 text-sm text-slate-600">
          {VALID_DOCS.filter((id) => id !== doc).map((id) => (
            <Link key={id} to={`/legal/${id}`} className="hover:text-brand-600">
              {t(`legal.${id}.title`)}
            </Link>
          ))}
          <Link to="/" className="hover:text-brand-600">
            {t("nav.home")}
          </Link>
        </nav>
      </div>
    </Layout>
  );
}
