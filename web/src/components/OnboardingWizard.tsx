import { useTranslation } from "react-i18next";

type Props = {
  step: number;
  onStep: (n: number) => void;
  hasBroker: boolean;
  hasSource: boolean;
  hasParse: boolean;
  hasAction: boolean;
};

/** 总览引导顺序：先券商，再流水线（接入 → 解析 → 执行） */
const STEPS = ["broker", "pipeline", "parse", "action"] as const;

export default function OnboardingWizard({
  step,
  onStep,
  hasBroker,
  hasSource,
  hasParse,
  hasAction,
}: Props) {
  const { t } = useTranslation();

  const done = [hasBroker, hasSource, hasParse, hasAction];
  const allDone = done.every(Boolean);

  if (allDone) return null;

  return (
    <section className="rounded-[1.5rem] border border-brand-100 bg-gradient-to-br from-brand-50 to-white p-6 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand-600">{t("onboarding.eyebrow")}</p>
          <h2 className="mt-1 text-xl font-bold text-slate-950">{t("onboarding.title")}</h2>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">{t("onboarding.subtitle")}</p>
        </div>
        <div className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-500 shadow-card">
          {done.filter(Boolean).length} / {STEPS.length}
        </div>
      </div>

      <ol className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((key, i) => (
          <li key={key} className="relative">
            {i < STEPS.length - 1 ? (
              <span
                className="pointer-events-none absolute -right-2 top-10 z-10 hidden text-slate-300 lg:block"
                aria-hidden
              >
                →
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => onStep(i)}
              className={`h-full w-full rounded-2xl border p-4 text-left transition-colors ${
                done[i]
                  ? "border-profit/20 bg-profit-soft"
                  : step === i
                    ? "border-brand-200 bg-white shadow-card"
                    : "border-slate-200 bg-white/70 hover:bg-white"
              }`}
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${
                  done[i] ? "bg-profit" : step === i ? "bg-brand-600" : "bg-slate-300"
                }`}
              >
                {done[i] ? "✓" : i + 1}
              </span>
              <div className="mt-3">
                <div className="font-medium text-slate-900">{t(`onboarding.${key}Title`)}</div>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">{t(`onboarding.${key}Hint`)}</p>
              </div>
            </button>
          </li>
        ))}
      </ol>

      <p className="mt-4 text-xs text-slate-500">{t("onboarding.agentNote")}</p>
    </section>
  );
}
