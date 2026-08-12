import { useTranslation } from "react-i18next";
import { BrokerLogo } from "./BrokerLogos";

const SOURCES = [
  {
    key: "discord",
    color: "from-indigo-500 to-indigo-600",
    ring: "ring-indigo-200",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden>
        <path d="M20.3 4.4A17.2 17.2 0 0015.5 3c-.2.4-.5 1-.7 1.4a15.9 15.9 0 00-4.6 0C10 4 9.7 3.4 9.5 3a17.2 17.2 0 00-4.8 1.4C2.5 8.2 1.8 11.9 2.1 15.5a17.4 17.4 0 005.3 2.7c.4-.6.8-1.2 1.1-1.8-.6-.2-1.2-.5-1.7-.9.1-.1.2-.2.3-.3 3.3 1.5 6.8 1.5 10 0l.3.3c-.5.3-1.1.6-1.7.9.3.6.7 1.2 1.1 1.8a17.4 17.4 0 005.3-2.7c.4-4.2-.7-7.8-2.9-11.1ZM8.7 13.2c-.8 0-1.5-.8-1.5-1.7s.6-1.7 1.5-1.7 1.5.8 1.5 1.7-.7 1.7-1.5 1.7Zm6.6 0c-.8 0-1.5-.8-1.5-1.7s.6-1.7 1.5-1.7 1.5.8 1.5 1.7-.7 1.7-1.5 1.7Z" />
      </svg>
    ),
  },
  {
    key: "telegram",
    color: "from-sky-500 to-sky-600",
    ring: "ring-sky-200",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden>
        <path d="M21.9 4.6 2.8 11.5c-1.2.5-1.2 1.2-.2 1.5l4.9 1.5 1.9 5.8c.2.6.8.8 1.2.3l2.6-2.5 5.4 4c.9.5 1.5.2 1.7-.9L23.7 6.4c.3-1.3-.5-1.9-1.8-1.8Z" />
      </svg>
    ),
  },
  {
    key: "tradingview",
    color: "from-blue-600 to-blue-700",
    ring: "ring-blue-200",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5" aria-hidden>
        <path d="M4 19V5M4 19h16M8 17V9m4 8V7m4 10v-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    key: "webhook",
    color: "from-emerald-500 to-emerald-600",
    ring: "ring-emerald-200",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5" aria-hidden>
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" strokeLinecap="round" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" strokeLinecap="round" />
      </svg>
    ),
  },
] as const;

const BROKERS = ["tiger", "longbridge", "schwab", "alpaca", "usmart", "ibkr", "futu"] as const;

function FlowArrow({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 24"
      fill="none"
      className={`h-6 w-12 text-brand-300 ${className}`}
      aria-hidden
    >
      <path
        d="M4 12h32m-6-6 6 6-6 6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FlowArrowDown({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 48" fill="none" className={`h-10 w-6 text-brand-300 ${className}`} aria-hidden>
      <path
        d="M12 4v32m-6-6 6 6 6-6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function PlatformFlowDiagram() {
  const { t } = useTranslation();

  return (
    <div className="relative mx-auto max-w-5xl">
      <div className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-brand-200/40 via-white to-indigo-100/30 blur-2xl" />
      <div className="relative overflow-hidden rounded-[1.75rem] border border-slate-200/80 bg-white/90 p-6 shadow-pop backdrop-blur sm:p-8">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-slate-400">
          {t("hero.ingressEyebrow")}
        </p>

        {/* Sources */}
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
          {SOURCES.map((src) => (
            <div
              key={src.key}
              className={`flex flex-col items-center rounded-2xl border border-white/60 bg-white p-4 shadow-card ring-1 ${src.ring}`}
            >
              <div
                className={`flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br ${src.color} text-white shadow-sm`}
              >
                {src.icon}
              </div>
              <p className="mt-3 text-center text-sm font-semibold text-slate-800">
                {t(`hero.ingress.${src.key}`)}
              </p>
              <p className="mt-1 text-center text-[11px] leading-snug text-slate-500">
                {t(`hero.ingress.${src.key}Desc`)}
              </p>
            </div>
          ))}
        </div>

        {/* Converge arrows */}
        <div className="my-2 flex justify-center sm:my-4">
          <div className="flex items-end gap-1 sm:gap-3">
            <FlowArrowDown className="hidden sm:block -rotate-12 opacity-70" />
            <FlowArrowDown />
            <FlowArrowDown className="hidden sm:block rotate-12 opacity-70" />
          </div>
        </div>

        {/* Hub */}
        <div className="relative mx-auto max-w-xl">
          <div className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-brand-400 via-brand-500 to-emerald-400 opacity-20 blur-md" />
          <div className="relative rounded-2xl border-2 border-brand-300 bg-gradient-to-br from-brand-50 to-white p-5 text-center shadow-card">
            <img src="/logo.png" alt="" className="mx-auto h-14 w-14 rounded-2xl object-cover shadow-pop" />
            <p className="mt-3 text-lg font-bold tracking-tight text-slate-950">SigTrades</p>
            <p className="mt-1 text-sm text-slate-600">{t("hero.ingress.hubDesc")}</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {(["parse", "risk", "route"] as const).map((chip) => (
                <span
                  key={chip}
                  className="rounded-full bg-white px-3 py-1 text-xs font-medium text-brand-800 ring-1 ring-brand-200"
                >
                  {t(`hero.ingress.${chip}`)}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Diverge arrows */}
        <div className="my-2 flex justify-center sm:my-4">
          <div className="flex items-start gap-1 sm:gap-3">
            <FlowArrowDown className="hidden rotate-180 sm:block rotate-[168deg] opacity-70" />
            <FlowArrowDown className="rotate-180" />
            <FlowArrowDown className="hidden rotate-180 sm:block -rotate-[168deg] opacity-70" />
          </div>
        </div>

        {/* Brokers */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 sm:gap-4">
          {BROKERS.map((broker) => (
            <div
              key={broker}
              className="flex flex-col items-center rounded-2xl border border-slate-200 bg-slate-50/80 p-4 shadow-card"
            >
              <div className="flex h-10 items-center justify-center">
                <BrokerLogo broker={broker} />
              </div>
              <p className="mt-3 text-center text-sm font-semibold text-brand-700">
                {t(`hero.brokers.${broker}`)}
              </p>
              <p className="mt-1 text-center text-[11px] leading-snug text-slate-500">
                {t(`hero.brokers.${broker}Desc`)}
              </p>
            </div>
          ))}
        </div>

        {/* Desktop horizontal flow hint */}
        <div className="mt-6 hidden items-center justify-between gap-2 rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-500 lg:flex">
          <span className="font-medium text-slate-600">{t("hero.ingress.flowLabel")}</span>
          <div className="flex flex-1 items-center justify-center gap-2">
            <span>{t("hero.ingress.sources")}</span>
            <FlowArrow />
            <span className="font-semibold text-brand-700">SigTrades</span>
            <FlowArrow />
            <span>{t("hero.ingress.destinations")}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
