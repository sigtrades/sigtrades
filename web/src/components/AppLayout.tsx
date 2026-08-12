import { ReactNode, useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { navPath } from "../lib/appRoutes";
import { normalizePlanCode, planDisplayName, planTheme } from "../lib/planDisplay";
import { useAuth } from "../store/auth";
import LanguageSwitcher from "./LanguageSwitcher";

export type NavId =
  | "overview"
  | "pipelines"
  | "sources"
  | "brokers"
  | "risk"
  | "executions"
  | "account"
  | "membership"
  | "settings";

type Props = {
  title: string;
  subtitle?: string;
  children: ReactNode;
};

const ICONS: Record<NavId, ReactNode> = {
  overview: <PathIcon d="M3 12l9-9 9 9M5 10v10h14V10" />,
  pipelines: <PathIcon d="M4 7h11l-3-3M20 17H9l3 3" />,
  sources: <PathIcon d="M4 6h16M4 12h16M4 18h10" />,
  brokers: <PathIcon d="M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6" />,
  risk: <PathIcon d="M12 3l8 4v5c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V7z" />,
  executions: <PathIcon d="M4 6h16M4 12h16M4 18h16" />,
  account: <PathIcon d="M20 21a8 8 0 10-16 0M12 11a4 4 0 100-8 4 4 0 000 8" />,
  membership: <PathIcon d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />,
  settings: <PathIcon d="M12 15a3 3 0 100-6 3 3 0 000 6zM4 12h2m12 0h2M12 4v2m0 12v2" />,
};

function PathIcon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d={d} />
    </svg>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
      {open ? (
        <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
      ) : (
        <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
      )}
    </svg>
  );
}

export default function AppLayout({ title, children }: Props) {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const items: NavId[] = [
    "overview",
    "pipelines",
    "sources",
    "brokers",
    "risk",
    "executions",
    "account",
    "membership",
    "settings",
  ];

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  const navLinks = (opts?: { onNavigate?: () => void; showLabels?: boolean }) => {
    const showLabels = opts?.showLabels !== false;
    return items.map((id) => (
      <NavLink
        key={id}
        to={navPath(id)}
        title={t(`console.nav.${id}`)}
        onClick={() => opts?.onNavigate?.()}
        className={({ isActive }) =>
          `flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
            isActive
              ? "bg-brand-500 text-white shadow-card"
              : "text-slate-300 hover:bg-white/10 hover:text-white"
          }`
        }
      >
        {({ isActive }) => (
          <>
            <span className={isActive ? "text-white" : "text-slate-500"}>{ICONS[id]}</span>
            {showLabels && <span>{t(`console.nav.${id}`)}</span>}
          </>
        )}
      </NavLink>
    ));
  };

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {/* Desktop sidebar */}
      <aside
        className={`sticky top-0 z-30 hidden h-screen shrink-0 flex-col border-r border-white/10 bg-slate-950 text-white shadow-2xl shadow-slate-950/10 transition-all md:flex ${
          collapsed ? "w-16" : "w-64"
        }`}
      >
        <div className="flex h-[4.5rem] items-center gap-3 border-b border-white/10 px-4">
          <Link to="/" className="flex h-10 w-10 items-center justify-center">
            <img src="/logo.png" alt="" className="h-10 w-10 rounded-xl object-cover shadow-pop" />
          </Link>
          {!collapsed && (
            <div>
              <p className="text-sm font-bold tracking-tight">SigTrades</p>
              <p className="text-xs text-slate-400">signal operations</p>
            </div>
          )}
        </div>
        <nav className="flex-1 space-y-1 px-3 py-5">{navLinks({ showLabels: !collapsed })}</nav>
        {!collapsed && (
          <div className="mx-3 mb-3 rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-200">{t("console.sidebarTitle")}</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">{t("console.sidebarHint")}</p>
          </div>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="flex min-h-11 items-center gap-2 border-t border-white/10 px-4 py-3 text-xs text-slate-400 hover:text-white"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className={`h-4 w-4 transition-transform ${collapsed ? "rotate-180" : ""}`}>
            <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {!collapsed && t("console.collapse")}
        </button>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/50"
            aria-label={t("common.close")}
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(18rem,88vw)] flex-col bg-slate-950 text-white shadow-2xl">
            <div className="flex h-14 items-center justify-between gap-3 border-b border-white/10 px-4">
              <Link to="/" className="flex items-center gap-2.5" onClick={() => setMobileOpen(false)}>
                <img src="/logo.png" alt="" className="h-9 w-9 rounded-xl object-cover shadow-pop" />
                <span className="text-sm font-bold tracking-tight">SigTrades</span>
              </Link>
              <button
                type="button"
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-slate-300 hover:bg-white/10"
                aria-label={t("common.close")}
                onClick={() => setMobileOpen(false)}
              >
                <MenuIcon open />
              </button>
            </div>
            <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">{navLinks({ onNavigate: () => setMobileOpen(false) })}</nav>
            <div className="border-t border-white/10 px-4 py-3">
              <p className="truncate text-xs text-slate-400">{user?.email}</p>
              <span className={`badge mt-2 ${planTheme(user?.plan_code).badge}`}>
                {t(`pricing.${normalizePlanCode(user?.plan_code)}`, {
                  defaultValue: planDisplayName(user?.plan_code),
                })}
              </span>
            </div>
          </aside>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex min-h-14 items-center justify-between gap-3 border-b border-slate-200/80 bg-white/85 px-3 py-2 shadow-sm shadow-slate-900/[0.02] backdrop-blur-xl sm:min-h-16 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 md:hidden"
              aria-label={t("common.menu")}
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen(true)}
            >
              <MenuIcon open={false} />
            </button>
            <div className="min-w-0 md:hidden">
              <p className="truncate text-sm font-semibold text-slate-900">{title}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="hidden items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm shadow-card sm:flex">
              <span className="max-w-[12rem] truncate text-slate-600 lg:max-w-none">{user?.email}</span>
              <span className={`badge ${planTheme(user?.plan_code).badge}`}>
                {t(`pricing.${normalizePlanCode(user?.plan_code)}`, {
                  defaultValue: planDisplayName(user?.plan_code),
                })}
              </span>
            </div>
            <LanguageSwitcher compact className="w-[5.5rem] sm:w-[6.5rem]" />
            <button type="button" onClick={logout} className="btn-secondary min-h-10 px-3 py-2 text-xs sm:text-sm">
              {t("nav.logout")}
            </button>
          </div>
        </header>
        <main aria-label={title} className="relative flex-1 overflow-y-auto px-3 py-5 sm:px-6 sm:py-8">
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.22]"
            style={{
              backgroundImage: "radial-gradient(circle at 1px 1px, rgb(148 163 184 / 0.22) 1px, transparent 0)",
              backgroundSize: "30px 30px",
            }}
          />
          <div className="relative mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
