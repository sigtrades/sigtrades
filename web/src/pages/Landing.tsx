import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import RichText from "../components/RichText";
import { BrokerLogo } from "../components/BrokerLogos";

const BROKERS = ["tiger", "longbridge", "schwab", "alpaca", "usmart", "ibkr", "futu"] as const;
const FEATURE_KEYS = ["rules", "risk", "audit", "notify"] as const;

const SOURCE_META = {
  discord: {
    ring: "ring-indigo-100",
    bg: "bg-[#5865F2]/10",
    icon: <img src="/sources/discord.svg" alt="" className="h-3.5 w-3.5 object-contain" aria-hidden />,
  },
  telegram: {
    ring: "ring-sky-100",
    bg: "bg-[#26A5E4]/10",
    icon: <img src="/sources/telegram.svg" alt="" className="h-3.5 w-3.5 object-contain" aria-hidden />,
  },
  tradingview: {
    ring: "ring-slate-200",
    bg: "bg-slate-100",
    icon: <img src="/sources/tradingview.svg" alt="" className="h-3.5 w-3.5 object-contain" aria-hidden />,
  },
  sunnyquant: {
    ring: "ring-amber-100",
    bg: "bg-amber-50",
    icon: <img src="/sources/sunnyquant.png" alt="" className="h-3.5 w-3.5 rounded-sm object-contain" aria-hidden />,
  },
  webhook: {
    ring: "ring-emerald-100",
    bg: "bg-emerald-50 text-emerald-600",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5" aria-hidden>
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" strokeLinecap="round" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" strokeLinecap="round" />
      </svg>
    ),
  },
} as const;

type SourceKey = keyof typeof SOURCE_META;

function CheckIcon({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg viewBox="0 0 12 12" fill="none" className={className} aria-hidden>
      <path d="M2.5 6l2.5 2.5 5-5" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconWrap({ children, className = "bg-brand-50 text-brand-600" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${className}`}>
      {children}
    </div>
  );
}

function SectionHeader({ eyebrow, title, subtitle, center = false }: { eyebrow: string; title: string; subtitle?: string; center?: boolean }) {
  return (
    <div className={`mb-10 max-w-2xl ${center ? "mx-auto text-center" : ""}`}>
      <p className="text-sm font-semibold uppercase tracking-wide text-brand-600">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">{title}</h2>
      {subtitle && <p className="mt-3 text-slate-600">{subtitle}</p>}
    </div>
  );
}

const FEATURE_ICONS: Record<(typeof FEATURE_KEYS)[number], React.ReactNode> = {
  rules: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M6 6h12M6 12h8M6 18h4M14 12l4 4M14 12l4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  risk: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M12 3l8 4v5c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V7z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  audit: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" strokeLinecap="round" />
      <path d="M9 12h6M9 16h4" strokeLinecap="round" />
    </svg>
  ),
  notify: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M6 8a6 6 0 1112 0c0 7 3 7 3 7H3s3 0 3-7M10 21h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

const STEP_ICONS = [
  (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M12 3v10M8 7l4-4 4 4M4 14v4a2 2 0 002 2h12a2 2 0 002-2v-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M13 2L4 14h7l-1 8 10-14h-7l0-6z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
];

function PipelinePreview() {
  const { t } = useTranslation();
  const stages = [
    { label: t("hero.pipeline.connect"), detail: "Discord · AAPL option alert", tone: "indigo" },
    { label: t("hero.pipeline.parse"), detail: "AI parse · risk passed", tone: "brand" },
    { label: t("hero.pipeline.execute"), detail: "Tiger · FILLED", tone: "emerald" },
  ] as const;

  return (
    <div className="relative lg:pl-4">
      <div className="pointer-events-none absolute -right-10 -top-12 h-48 w-48 rounded-full bg-brand-200/50 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-8 left-2 h-36 w-36 rounded-full bg-indigo-100/80 blur-3xl" />
      <div className="relative overflow-hidden rounded-[1.75rem] border border-white/70 bg-white/80 shadow-pop ring-1 ring-slate-900/5 backdrop-blur-xl">
        <div className="flex items-center justify-between border-b border-white/10 bg-slate-950 px-4 py-3">
          <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            <span className="ml-2 text-[11px] font-medium text-slate-400">SigTrades / pipeline</span>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 px-2 py-1 text-[10px] font-semibold text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            LIVE
          </span>
        </div>

        <div className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-brand-700">Execution pipeline</p>
              <h3 className="mt-1 text-base font-bold text-slate-950">Discord Options · Tiger</h3>
              <p className="mt-1 font-mono text-[11px] text-slate-400">PIPE-8F2A · signal_01J7...</p>
            </div>
            <span className="badge bg-brand-50 text-brand-700 ring-1 ring-brand-100">AUTO</span>
          </div>

          <div className="mt-5 space-y-2.5">
            {stages.map((stage, index) => (
              <div key={stage.label} className="relative flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white px-3.5 py-3 shadow-sm">
                {index < stages.length - 1 && <span className="absolute left-[1.62rem] top-[2.9rem] h-3.5 w-px bg-slate-200" />}
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
                    stage.tone === "indigo"
                      ? "bg-indigo-50 text-indigo-600"
                      : stage.tone === "brand"
                        ? "bg-brand-50 text-brand-700"
                        : "bg-emerald-50 text-emerald-700"
                  }`}
                >
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-800">{stage.label}</p>
                  <p className="mt-0.5 truncate font-mono text-[10px] text-slate-500">{stage.detail}</p>
                </div>
                <CheckIcon className="h-4 w-4 text-emerald-500" />
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 border-t border-slate-100 bg-slate-50/70">
          {[
            [t("hero.stats.sources"), "5+"],
            [t("hero.stats.brokers"), "6"],
            [t("hero.stats.audit"), "ET"],
          ].map(([label, value]) => (
            <div key={label} className="border-r border-slate-100 px-3 py-3.5 text-center last:border-r-0">
              <p className="text-base font-bold text-slate-900">{value}</p>
              <p className="mt-0.5 text-[9px] text-slate-500">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function IntegrationRail({ sourceKeys }: { sourceKeys: SourceKey[] }) {
  const { t } = useTranslation();
  return (
    <div className="mt-12 rounded-[1.75rem] border border-slate-200/80 bg-white/80 p-5 shadow-card backdrop-blur sm:p-6">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
          {t("hero.ingress.sources")}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2.5">
          {sourceKeys.map((key) => (
            <SourcePill key={key} sourceKey={key} name={t(`hero.ingress.${key}`)} />
          ))}
        </div>
      </div>

      <div className="my-5 flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-gradient-to-r from-transparent via-slate-200 to-slate-200" />
        <img src="/logo.png" alt="" className="h-10 w-10 rounded-xl object-cover shadow-sm ring-4 ring-brand-50" />
        <span className="h-px flex-1 bg-gradient-to-r from-slate-200 via-slate-200 to-transparent" />
      </div>

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
          {t("hero.ingress.destinations")}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          {BROKERS.map((broker) => (
            <div
              key={broker}
              className="flex min-h-14 items-center justify-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 shadow-sm"
            >
              <BrokerLogo broker={broker} className="h-7 w-7 rounded object-contain" />
              <span className="text-xs font-semibold text-slate-800">
                {broker === "tiger"
                  ? "Tiger"
                  : broker === "longbridge"
                    ? "Longbridge"
                    : broker === "schwab"
                      ? "Schwab"
                      : broker === "alpaca"
                        ? "Alpaca"
                        : broker === "usmart"
                          ? "uSMART"
                          : broker === "ibkr"
                            ? "IBKR"
                            : "Futu"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SourcePill({ sourceKey, name }: { sourceKey: SourceKey; name: string }) {
  const meta = SOURCE_META[sourceKey];
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-card ring-1 ${meta.ring} transition-colors duration-200`}>
      <span className={`flex h-6 w-6 items-center justify-center rounded-full ${meta.bg}`}>{meta.icon}</span>
      {name}
    </span>
  );
}

export default function Landing() {
  const { t } = useTranslation();
  const steps = [
    { label: t("hero.pipeline.connect"), detail: t("hero.pipeline.connectDesc"), icon: STEP_ICONS[0] },
    { label: t("hero.pipeline.parse"), detail: t("hero.pipeline.parseDesc"), icon: STEP_ICONS[1] },
    { label: t("hero.pipeline.execute"), detail: t("hero.pipeline.executeDesc"), icon: STEP_ICONS[2] },
  ];
  const trustPoints = [t("hero.trust1"), t("hero.trust2"), t("hero.trust3"), t("hero.trust4")];
  const sourceKeys = Object.keys(SOURCE_META) as SourceKey[];

  return (
    <Layout>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-slate-100">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,#f8fafc_0%,#ffffff_60%)]" />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.32]"
          style={{
            backgroundImage: "radial-gradient(circle at 1px 1px, rgb(148 163 184 / 0.28) 1px, transparent 0)",
            backgroundSize: "28px 28px",
          }}
        />
        <div className="pointer-events-none absolute -left-24 top-20 h-72 w-72 rounded-full bg-brand-100/50 blur-3xl" />

        <div className="relative mx-auto max-w-6xl px-4 pb-14 pt-14 sm:pb-20 sm:pt-20">
          <div className="grid items-center gap-10 lg:grid-cols-[1.08fr_.92fr] lg:gap-12">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-brand-200/80 bg-white/90 px-3 py-1 text-xs font-semibold text-brand-700 shadow-card backdrop-blur-sm">
                <img src="/logo.png" alt="" className="h-5 w-5 rounded-md object-cover shadow-sm" />
                {t("hero.badge")}
              </div>
              <h1 className="mt-6 text-4xl font-bold tracking-[-0.035em] text-slate-950 sm:text-5xl lg:text-[3.35rem] lg:leading-[1.07]">
                {t("hero.titleLead")}
                <span className="mt-1 block bg-gradient-to-r from-brand-600 to-emerald-400 bg-clip-text text-transparent">
                  {t("hero.titleAccent")}
                </span>
              </h1>
              <RichText
                text={t("hero.subtitle")}
                className="mt-5 max-w-xl text-base leading-relaxed text-slate-600 sm:text-lg"
                strongClassName="font-semibold text-slate-900"
              />
              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  to="/register"
                  className="btn-primary cursor-pointer px-6 py-3 text-base shadow-pop transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
                >
                  {t("hero.cta")}
                </Link>
                <a
                  href="#how-it-works"
                  className="btn-secondary cursor-pointer px-6 py-3 text-base transition-colors duration-200 hover:border-brand-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
                >
                  {t("hero.ctaSecondary")}
                </a>
              </div>
              <ul className="mt-8 grid gap-3 sm:grid-cols-2">
                {trustPoints.map((point) => (
                  <li key={point} className="flex items-start gap-3 text-sm text-slate-600">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                      <CheckIcon />
                    </span>
                    <span
                      className={
                        /加密|encrypt|明文|plaintext/i.test(point)
                          ? "font-medium text-slate-800"
                          : undefined
                      }
                    >
                      {point}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-5 max-w-xl border-l-2 border-slate-200 pl-3 text-[11px] leading-relaxed text-slate-500">
                {t("hero.disclaimer")}
              </p>
            </div>
            <PipelinePreview />
          </div>

          <IntegrationRail sourceKeys={sourceKeys} />
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-b border-slate-100 bg-slate-50/60 py-16 sm:py-20">
        <div className="mx-auto max-w-6xl px-4">
          <SectionHeader eyebrow={t("hero.flowEyebrow")} title={t("hero.flowTitle")} subtitle={t("hero.flowSubtitle")} />
          <div className="grid gap-5 lg:grid-cols-3">
            {steps.map((step, i) => (
              <div
                key={step.label}
                className="group relative rounded-2xl border border-slate-200 bg-white p-6 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-pop"
              >
                {i < steps.length - 1 && (
                  <div className="pointer-events-none absolute -right-3 top-1/2 z-10 hidden h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-sm text-slate-300 lg:flex">
                    →
                  </div>
                )}
                <div className="flex items-center justify-between gap-3">
                  <IconWrap className="transition-colors duration-200 group-hover:bg-brand-500 group-hover:text-white">
                    {step.icon}
                  </IconWrap>
                  <span className="text-2xl font-black tracking-[-0.04em] text-brand-600/80 transition-colors duration-200 group-hover:text-brand-600">
                    0{i + 1}
                  </span>
                </div>
                <h3 className="mt-4 text-lg font-semibold text-slate-900">{step.label}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{step.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:py-20">
        <SectionHeader eyebrow={t("hero.featuresEyebrow")} title={t("hero.featuresTitle")} />
        <div className="grid gap-5 sm:grid-cols-2">
          {FEATURE_KEYS.map((key) => (
            <div
              key={key}
              className="group cursor-default rounded-2xl border border-slate-200 bg-white p-6 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-pop"
            >
              <IconWrap className="bg-slate-900 text-white transition-colors duration-200 group-hover:bg-brand-500">
                {FEATURE_ICONS[key]}
              </IconWrap>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">{t(`hero.features.${key}`)}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{t(`hero.features.${key}Desc`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Brokers */}
      <section className="border-t border-slate-100 bg-slate-50 py-16 sm:py-20">
        <div className="mx-auto max-w-6xl px-4">
          <SectionHeader eyebrow={t("hero.brokerEyebrow")} title={t("hero.brokerTitle")} subtitle={t("hero.brokerSubtitle")} />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {BROKERS.map((key) => {
              const isAgent = key === "ibkr" || key === "futu";
              return (
                <div
                  key={key}
                  className="min-h-[13rem] rounded-2xl border border-slate-200 bg-white p-6 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-pop"
                >
                  <div className="flex items-start justify-between gap-2">
                    <BrokerLogo broker={key} framed />
                    <span className={`badge text-[10px] ${isAgent ? "bg-slate-100 text-slate-600" : "bg-brand-50 text-brand-700 ring-1 ring-brand-100"}`}>
                      {isAgent ? t("hero.brokerAgent") : t("hero.brokerCloud")}
                    </span>
                  </div>
                  <h3 className="mt-4 font-semibold text-slate-900">{t(`hero.brokers.${key}`)}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{t(`hero.brokers.${key}Desc`)}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Security */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:py-20">
        <div className="relative overflow-hidden rounded-[1.75rem] bg-slate-950 text-white shadow-pop ring-1 ring-brand-500/20">
          <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-brand-400/40 to-transparent" />
          <div className="grid gap-8 p-8 sm:p-10 lg:grid-cols-[1fr_1.1fr] lg:items-center">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-brand-300">{t("hero.securityEyebrow")}</p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">{t("hero.securityTitle")}</h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-300">{t("hero.securitySubtitle")}</p>
              <RichText
                text={t("hero.securityEncrypt")}
                className="mt-4 rounded-xl border border-brand-400/30 bg-brand-500/10 px-4 py-3 text-sm leading-relaxed text-brand-100"
                strongClassName="font-semibold text-white"
              />
            </div>
            <ul className="space-y-3">
              {[t("hero.security1"), t("hero.security2"), t("hero.security3")].map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3.5 text-sm text-slate-200 transition-colors duration-200 hover:border-brand-400/30 hover:bg-white/[0.07]"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-500/20 text-brand-300">
                    <CheckIcon />
                  </span>
                  <span className="font-medium text-white/95">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="mx-auto max-w-6xl px-4 pb-20 pt-4">
        <div className="rounded-[1.75rem] border border-brand-200/80 bg-gradient-to-br from-brand-50 via-white to-slate-50 p-8 text-center shadow-card sm:p-12">
          <p className="text-sm font-semibold uppercase tracking-wide text-brand-600">{t("hero.finalEyebrow")}</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">{t("hero.finalTitle")}</h2>
          <p className="mx-auto mt-3 max-w-2xl text-slate-600">{t("hero.finalSubtitle")}</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/register"
              className="btn-primary cursor-pointer px-8 py-3 text-base shadow-pop transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
            >
              {t("hero.finalCta")}
            </Link>
            <Link
              to="/pricing"
              className="btn-secondary cursor-pointer px-8 py-3 text-base transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
            >
              {t("nav.pricing")}
            </Link>
          </div>
        </div>
      </section>
    </Layout>
  );
}
