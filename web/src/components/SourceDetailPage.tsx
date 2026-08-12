import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { type PipelineStepId, type SourcePipelineStatus } from "../lib/sourcePipeline";
import ParseConfigSection from "./ParseConfigSection";
import SourcePipelineBar from "./SourcePipelineBar";
import SourceRouteConfig from "./SourceRouteConfig";
import SourceSignalFeed from "./SourceSignalFeed";

type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids?: string[];
  channel_labels?: Record<string, string>;
  bridge_mode?: string;
  is_active?: boolean;
};

type Props = {
  status: SourcePipelineStatus;
  discordSources: DiscordSource[];
  onBack: () => void;
  onReload: () => void;
  scrollTo?: PipelineStepId | null;
};

export default function SourceDetailPage({
  status,
  discordSources,
  onBack,
  onReload,
  scrollTo,
}: Props) {
  const { t } = useTranslation();
  const source = discordSources.find((s) => s.source_id === status.sourceId);
  const channelText = useMemo(() => {
    if (!source) return "";
    return Object.values(source.channel_labels || {}).join(" · ") || source.channel_ids?.join(", ") || "";
  }, [source]);

  const sectionId = (step: string) => `pipeline-${step}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <button type="button" onClick={onBack} className="mb-2 text-sm text-brand-600 hover:underline">
            ← {t("pipeline.backToSources")}
          </button>
          <h2 className="text-xl font-bold text-slate-900">{status.name}</h2>
          {channelText ? <p className="mt-1 text-sm text-slate-500">{channelText}</p> : null}
          <p className="mt-1 font-mono text-xs text-slate-400">{status.sourceId}</p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <p>{t("pipeline.todayStats", { signals: status.todaySignals, filled: status.todayFilled, pending: status.todayPending })}</p>
          {status.ready ? (
            <span className="badge-success mt-2 inline-block">{t("pipeline.ready")}</span>
          ) : (
            <span className="badge-neutral mt-2 inline-block">{t("pipeline.incomplete")}</span>
          )}
        </div>
      </div>

      <div className="card">
        <SourcePipelineBar status={status} />
      </div>

      <section id={sectionId("connect")} className={`card ${scrollTo === "connect" ? "ring-2 ring-brand-300" : ""}`}>
        <h3 className="font-semibold text-slate-900">{t("pipeline.sectionConnect")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t("pipeline.sectionConnectHint")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className={status.connected ? "badge-success" : "badge-neutral"}>
            {status.connected ? t("dashboard.discordSourceActive") : t("dashboard.discordSourceStopped")}
          </span>
          {channelText ? <span className="text-slate-600">{channelText}</span> : null}
        </div>
      </section>

      <section id={sectionId("parse")} className={`card ${scrollTo === "parse" ? "ring-2 ring-brand-300" : ""}`}>
        <h3 className="font-semibold text-slate-900">{t("pipeline.sectionParse")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t("pipeline.sectionParseHint")}</p>
        <div className="mt-4">
          <ParseConfigSection
            sources={discordSources}
            fixedSourceId={status.sourceId}
            onSaved={onReload}
          />
        </div>
      </section>

      <section id={sectionId("action")} className={`card ${scrollTo === "execute" ? "ring-2 ring-brand-300" : ""}`}>
        <h3 className="font-semibold text-slate-900">{t("pipeline.sectionAction")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t("pipeline.sectionActionHint")}</p>
        <div className="mt-4">
          <SourceRouteConfig sourceId={status.sourceId} onSaved={onReload} />
        </div>
      </section>

      <section id={sectionId("broker")} className="card">
        <h3 className="font-semibold text-slate-900">{t("pipeline.sectionBroker")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t("pipeline.sectionBrokerHint")}</p>
        {status.hasBroker ? (
          <p className="mt-3 text-sm text-slate-700">{status.brokers.join(", ")}</p>
        ) : (
          <p className="mt-3 text-sm text-loss">{t("pipeline.sectionBrokerMissing")}</p>
        )}
      </section>

      <section className="card">
        <h3 className="font-semibold text-slate-900">{t("pipeline.sectionFeed")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t("pipeline.sectionFeedHint")}</p>
        <div className="mt-4">
          <SourceSignalFeed sourceId={status.sourceId} onAction={onReload} />
        </div>
      </section>
    </div>
  );
}
