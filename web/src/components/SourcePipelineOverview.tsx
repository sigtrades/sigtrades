import { useTranslation } from "react-i18next";
import { type PipelineStepId, type SourcePipelineStatus } from "../lib/sourcePipeline";
import SourcePipelineBar from "./SourcePipelineBar";

type Props = {
  items: SourcePipelineStatus[];
  onOpenDetail: (sourceId: string, scrollTo?: PipelineStepId) => void;
};

export default function SourcePipelineOverview({ items, onOpenDetail }: Props) {
  const { t } = useTranslation();

  if (items.length === 0) return null;

  return (
    <section className="card">
      <h2 className="font-semibold text-slate-900">{t("pipeline.overviewTitle")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("pipeline.overviewHint")}</p>
      <ul className="mt-4 space-y-4">
        {items.map((item) => (
          <li key={item.sourceId} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium text-slate-900">{item.name}</p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {t("pipeline.todayStats", {
                    signals: item.todaySignals,
                    filled: item.todayFilled,
                    pending: item.todayPending,
                  })}
                </p>
              </div>
              <div className="flex gap-2">
                {item.nextStep ? (
                  <button
                    type="button"
                    className="btn-secondary text-xs"
                    onClick={() => onOpenDetail(item.sourceId, item.nextStep)}
                  >
                    {t("pipeline.configureStep")}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn-primary text-xs"
                  onClick={() => onOpenDetail(item.sourceId)}
                >
                  {t("pipeline.openDetail")}
                </button>
              </div>
            </div>
            <div className="mt-3">
              <SourcePipelineBar
                status={item}
                compact
                onStepClick={(step) => onOpenDetail(item.sourceId, step)}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
