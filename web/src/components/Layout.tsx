import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../store/auth";
import Footer from "./Footer";
import LanguageSwitcher from "./LanguageSwitcher";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const loggedIn = isAuthenticated && !!user;
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [menuOpen]);

  const linkClass =
    "btn-ghost min-h-11 w-full justify-start px-3 text-base transition-colors duration-200 hover:text-brand-700 md:min-h-0 md:w-auto md:justify-center md:px-3 md:text-sm";

  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="flex min-w-0 items-center gap-2.5">
            <img src="/logo.png" alt="" className="h-9 w-9 shrink-0 rounded-xl object-cover shadow-pop" />
            <span className="truncate text-lg font-bold tracking-tight text-slate-900">SigTrades</span>
          </Link>

          <nav className="hidden items-center gap-1 text-sm md:flex">
            <Link to="/" className="btn-ghost transition-colors duration-200 hover:text-brand-700">
              {t("nav.home")}
            </Link>
            <Link to="/pricing" className="btn-ghost transition-colors duration-200 hover:text-brand-700">
              {t("nav.pricing")}
            </Link>
            {loggedIn ? (
              <>
                <Link to="/app" className="btn-ghost transition-colors duration-200 hover:text-brand-700">
                  {t("nav.dashboard")}
                </Link>
                <button type="button" onClick={logout} className="btn-ghost transition-colors duration-200 hover:text-brand-700">
                  {t("nav.logout")}
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn-ghost transition-colors duration-200 hover:text-brand-700">
                  {t("nav.login")}
                </Link>
                <Link to="/register" className="btn-primary transition-all duration-200 hover:-translate-y-px">
                  {t("nav.signup")}
                </Link>
              </>
            )}
            <span className="mx-1 h-4 w-px bg-slate-200" />
            <LanguageSwitcher compact className="w-[6.5rem]" />
          </nav>

          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 md:hidden"
            aria-label={menuOpen ? t("common.close") : t("common.menu")}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
              {menuOpen ? (
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              ) : (
                <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>

        {menuOpen ? (
          <div className="border-t border-slate-100 bg-white md:hidden">
            <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-3">
              <Link to="/" className={linkClass} onClick={() => setMenuOpen(false)}>
                {t("nav.home")}
              </Link>
              <Link to="/pricing" className={linkClass} onClick={() => setMenuOpen(false)}>
                {t("nav.pricing")}
              </Link>
              {loggedIn ? (
                <>
                  <Link to="/app" className={linkClass} onClick={() => setMenuOpen(false)}>
                    {t("nav.dashboard")}
                  </Link>
                  <button
                    type="button"
                    className={linkClass}
                    onClick={() => {
                      setMenuOpen(false);
                      logout();
                    }}
                  >
                    {t("nav.logout")}
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className={linkClass} onClick={() => setMenuOpen(false)}>
                    {t("nav.login")}
                  </Link>
                  <Link
                    to="/register"
                    className="btn-primary mt-1 min-h-11 w-full justify-center"
                    onClick={() => setMenuOpen(false)}
                  >
                    {t("nav.signup")}
                  </Link>
                </>
              )}
              <div className="mt-2 border-t border-slate-100 pt-3">
                <LanguageSwitcher className="w-full" />
              </div>
            </nav>
          </div>
        ) : null}
      </header>
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
