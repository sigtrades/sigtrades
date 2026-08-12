import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../store/auth";

export default function Footer() {
  const { t } = useTranslation();
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  const user = useAuth((s) => s.user);
  const loggedIn = isAuthenticated && !!user;
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Link to="/" className="text-lg font-bold tracking-tight text-brand-600">
              SigTrades
            </Link>
            <p className="mt-2 max-w-sm text-sm text-slate-600">{t("footer.tagline")}</p>
            <p className="mt-4 text-sm text-slate-500">{t("footer.copyright", { year })}</p>
          </div>
          <div className="flex flex-col gap-6 sm:flex-row sm:gap-12">
            <nav className="flex flex-col gap-2 text-sm text-slate-600">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{t("footer.product")}</span>
              <Link to="/pricing" className="hover:text-brand-600">
                {t("nav.pricing")}
              </Link>
              {loggedIn ? (
                <Link to="/app" className="hover:text-brand-600">
                  {t("nav.dashboard")}
                </Link>
              ) : (
                <>
                  <Link to="/login" className="hover:text-brand-600">
                    {t("nav.login")}
                  </Link>
                  <Link to="/register" className="hover:text-brand-600">
                    {t("nav.signup")}
                  </Link>
                </>
              )}
            </nav>
            <nav className="flex flex-col gap-2 text-sm text-slate-600">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{t("footer.legal")}</span>
              <Link to="/legal/terms" className="hover:text-brand-600">
                {t("footer.terms")}
              </Link>
              <Link to="/legal/refund" className="hover:text-brand-600">
                {t("footer.refund")}
              </Link>
              <Link to="/legal/privacy" className="hover:text-brand-600">
                {t("footer.privacy")}
              </Link>
              <Link to="/legal/risk" className="hover:text-brand-600">
                {t("footer.risk")}
              </Link>
            </nav>
          </div>
        </div>
        <p className="mt-8 border-t border-slate-200 pt-6 text-xs leading-relaxed text-slate-400">
          {t("footer.disclaimer")}
        </p>
      </div>
    </footer>
  );
}
