import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ST_WEBHOOK_OPTION_SAMPLE,
  ST_WEBHOOK_STOCK_SAMPLE,
  TV_WEBHOOK_SAMPLE,
} from "../lib/stWebhookV1";
import WebhookSignalJsonModal from "./WebhookSignalJsonModal";

type Props = {
  /** Compact single-column for narrow modals */
  compact?: boolean;
};

export default function WebhookJsonGuide({ compact = false }: Props) {
  const { t } = useTranslation();
  const [generatorOpen, setGeneratorOpen] = useState(false);

  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-700">{t("webhookJson.guideTitle")}</p>
        <button type="button" className="btn-secondary text-xs" onClick={() => setGeneratorOpen(true)}>
          {t("webhookJson.openGenerator")}
        </button>
      </div>

      <div className={compact ? "space-y-3" : "grid gap-3 sm:grid-cols-2"}>
        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {t("webhookJson.standardSample")}
          </p>
          <p className="mt-1 text-[11px] text-slate-500">{t("webhookJson.standardSampleHint")}</p>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-800">
            {JSON.stringify(ST_WEBHOOK_STOCK_SAMPLE, null, 2)}
          </pre>
          <details className="mt-2">
            <summary className="cursor-pointer text-[11px] font-medium text-brand-700">
              {t("webhookJson.optionSampleToggle")}
            </summary>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-800">
              {JSON.stringify(ST_WEBHOOK_OPTION_SAMPLE, null, 2)}
            </pre>
          </details>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {t("webhookJson.tvSample")}
          </p>
          <p className="mt-1 text-[11px] text-slate-500">{t("dashboard.tradingViewHint")}</p>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-800">
            {JSON.stringify(TV_WEBHOOK_SAMPLE, null, 2)}
          </pre>
        </div>
      </div>

      <WebhookSignalJsonModal open={generatorOpen} onClose={() => setGeneratorOpen(false)} />
    </div>
  );
}
