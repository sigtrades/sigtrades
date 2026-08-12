import { useTranslation } from "react-i18next";
import { pipelineSteps, type PipelineStepId, type SourcePipelineStatus } from "../lib/sourcePipeline";

type Props = {
  status: SourcePipelineStatus;
  onStepClick?: (step: PipelineStepId) => void;
  compact?: boolean;
  /** Inline pills beside pipeline title */
  inline?: boolean;
};

function stepPillClass(step: ReturnType<typeof pipelineSteps>[number], status: SourcePipelineStatus) {
  if (step.warning) {
    return "border-amber-300 bg-amber-50 text-amber-900";
  }
  if (step.done) {
    return "border-profit/30 bg-profit-soft text-profit";
  }
  if (status.nextStep === step.id) {
    return "border-brand-300 bg-brand-50 text-brand-700";
  }
  return "border-slate-200 bg-white text-slate-500";
}

function stepIconClass(step: ReturnType<typeof pipelineSteps>[number]) {
  if (step.warning) {
    return "bg-amber-400 text-white";
  }
  if (step.done) {
    return "bg-profit text-white";
  }
  return "bg-slate-200 text-slate-600";
}

export default function SourcePipelineBar({ status, onStepClick, compact, inline }: Props) {
  const { t } = useTranslation();
  const steps = pipelineSteps(status, t);
  const pillClass = inline
    ? "gap-1 rounded-full border px-1.5 py-0.5 text-[10px]"
    : "gap-1.5 rounded-full border px-2.5 py-1 text-xs";
  const iconClass = inline ? "h-3.5 w-3.5 text-[9px]" : "h-4 w-4 text-[10px]";
  const arrowClass = inline ? "text-slate-300 text-[10px]" : "text-slate-300";

  return (
    <div className={inline ? "" : compact ? "space-y-2" : "space-y-3"}>
      <div className={`flex flex-wrap items-center ${inline ? "gap-1" : "gap-2"}`}>
        {steps.map((step, i) => (
          <div key={step.id} className={`flex items-center ${inline ? "gap-1" : "gap-2"}`}>
            <button
              type="button"
              onClick={() => onStepClick?.(step.id)}
              className={`inline-flex items-center font-medium transition-colors ${pillClass} ${stepPillClass(step, status)} ${
                onStepClick ? "hover:border-brand-400" : "cursor-default"
              }`}
              title={step.detail}
            >
              <span
                className={`flex items-center justify-center rounded-full font-bold ${iconClass} ${stepIconClass(step)}`}
              >
                {step.warning ? "⏸" : step.done ? "✓" : i + 1}
              </span>
              {step.label}
            </button>
            {i < steps.length - 1 ? <span className={arrowClass}>→</span> : null}
          </div>
        ))}
      </div>
      {!compact && !inline && status.nextStep ? (
        <p className="text-xs text-brand-600">
          {t("pipeline.nextStepHint", { step: steps.find((s) => s.id === status.nextStep)?.label })}
        </p>
      ) : null}
    </div>
  );
}
