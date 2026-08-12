import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import {
  type PipelineStepId,
  type RouteRule,
  type SourcePipelineStatus,
  pipelineDisplayName,
  pipelineIdSuffix,
  wizardStepIndex,
} from "../lib/sourcePipeline";
import {
  brokerDisplayName,
  isBrokerPaperMode,
  normalizeBrokerKey,
} from "../lib/brokerCredentials";
import { webhookIngestUrl } from "../lib/webhookSources";
import { BrokerLogo } from "./BrokerLogos";
import ConfirmDialog from "./ConfirmDialog";
import PipelineWizard from "./PipelineWizard";
import SourcePipelineBar from "./SourcePipelineBar";
import PipelineFlowBoard from "./PipelineFlowBoard";
import WebhookSignalJsonModal from "./WebhookSignalJsonModal";

type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  bridge_mode?: string;
  is_active?: boolean;
};

type WebhookSource = { source_id: string; token: string; label?: string; url_path?: string };

function CopyWebhookButton({ url }: { url: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      window.prompt(t("execPipeline.copyWebhook"), url);
      setCopied(false);
    }
  };

  // 固定尺寸图标按钮：hover 用 title 提示文案；成功只换图标/颜色，标题文字不位移
  return (
    <button
      type="button"
      className={
        copied
          ? "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-profit/10 text-profit"
          : "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-brand-50 hover:text-brand-700"
      }
      title={copied ? t("execPipeline.webhookCopied") : t("execPipeline.copyWebhook")}
      aria-label={copied ? t("execPipeline.webhookCopied") : t("execPipeline.copyWebhook")}
      onClick={() => void copy()}
    >
      {copied ? (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5" aria-hidden>
          <path
            fillRule="evenodd"
            d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
            clipRule="evenodd"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5" aria-hidden>
          <path d="M7 3.5A1.5 1.5 0 018.5 2h6A1.5 1.5 0 0116 3.5v6a1.5 1.5 0 01-1.5 1.5h-1V7A2.5 2.5 0 0011 4.5H7v-1z" />
          <path d="M3.5 7A1.5 1.5 0 015 5.5h6A1.5 1.5 0 0112.5 7v6a1.5 1.5 0 01-1.5 1.5H5A1.5 1.5 0 013.5 13V7z" />
        </svg>
      )}
    </button>
  );
}

type TelegramSource = {
  source_id: string;
  name: string;
  chat_ids: string[];
  chat_labels?: Record<string, string>;
  is_active?: boolean;
};

function BrokerEnvModeTag({ paper }: { paper: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 ${
        paper
          ? "bg-amber-50 text-amber-800 ring-amber-200"
          : "bg-emerald-50 text-emerald-700 ring-emerald-200"
      }`}
    >
      {paper ? t("dashboard.envSimTag") : t("dashboard.envLiveTag")}
    </span>
  );
}

function PipelineCardTitle({ item }: { item: SourcePipelineStatus }) {
  const { t } = useTranslation();
  const broker = item.brokers[0];
  const brokerKey = broker ? normalizeBrokerKey(broker) : null;
  const paperMode = broker
    ? isBrokerPaperMode(broker, item.brokerEnv, item.brokerAccountId)
    : null;
  const policyLabel =
    item.orderTypePolicy === "LMT_then_MKT"
      ? t("pipeline.policyLmtShort")
      : item.orderTypePolicy
        ? t("pipeline.policyMktShort")
        : null;

  return (
    <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm font-semibold text-slate-900">
      <span className="truncate">{item.name}</span>
      {broker ? (
        <>
          <span className="font-normal text-slate-400">·</span>
          <span className="inline-flex items-center gap-1 font-semibold text-slate-800">
            {brokerKey ? (
              <span className="flex h-4 w-4 shrink-0 items-center justify-center overflow-hidden rounded border border-slate-200 bg-white">
                <BrokerLogo
                  broker={brokerKey}
                  className={
                    brokerKey === "longbridge" ? "h-3 w-3 object-contain" : "h-3 w-3 rounded object-contain"
                  }
                />
              </span>
            ) : null}
            <span>{brokerDisplayName(broker, t)}</span>
            {paperMode != null ? <BrokerEnvModeTag paper={paperMode} /> : null}
          </span>
        </>
      ) : null}
      {policyLabel ? (
        <>
          <span className="font-normal text-slate-400">·</span>
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200">
            {policyLabel}
          </span>
        </>
      ) : null}
      <span className="font-normal text-slate-400">({pipelineIdSuffix(item)})</span>
    </p>
  );
}

type Props = {
  pipelines: SourcePipelineStatus[];
  discordSources: DiscordSource[];
  webhooks: WebhookSource[];
  telegramSources?: TelegramSource[];
  ingestBase: string;
  routeRules: RouteRule[];
  onReload: () => void | Promise<void>;
  onGoToBrokers: () => void;
  onCreateWebhook: (label: string) => Promise<{ source_id: string; url: string }>;
  onWizardComplete?: () => void | Promise<void>;
};

export default function ExecutionPipelinesSection({
  pipelines,
  discordSources,
  webhooks,
  telegramSources = [],
  ingestBase,
  routeRules,
  onReload,
  onGoToBrokers,
  onCreateWebhook,
  onWizardComplete,
}: Props) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"list" | "wizard">("list");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeRouteRuleId, setActiveRouteRuleId] = useState<string | null>(null);
  const [wizardMode, setWizardMode] = useState<"new" | "edit">("new");
  const [wizardStep, setWizardStep] = useState(0);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    sourceId: string;
    routeRuleId?: string;
    name: string;
  } | null>(null);
  const [alertMessage, setAlertMessage] = useState("");
  const [jsonModalOpen, setJsonModalOpen] = useState(false);

  const webhookUrlBySource = useMemo(() => {
    const map = new Map<string, string>();
    for (const w of webhooks) {
      if (!w?.source_id) continue;
      if (map.has(w.source_id)) continue;
      const path = w.url_path || (w.token ? `/ingest/wh/${w.token}` : "");
      if (!path) continue;
      map.set(w.source_id, webhookIngestUrl(ingestBase, path));
    }
    return map;
  }, [webhooks, ingestBase]);

  const resolveWebhookUrl = (item: SourcePipelineStatus): string => {
    if (item.kind !== "webhook" && !item.sourceId.startsWith("wh-")) return "";
    return webhookUrlBySource.get(item.sourceId) || "";
  };

  const togglePipelineRun = async (routeRuleId: string, pause: boolean) => {
    if (togglingId) return;
    setTogglingId(routeRuleId);
    try {
      await api.post(`/config/pipelines/${routeRuleId}/${pause ? "pause" : "resume"}`);
      // 等列表数据刷新后再放开按钮，避免短暂回到旧状态仍可点
      await onReload();
    } catch {
      setAlertMessage(t(pause ? "execPipeline.pauseFailed" : "execPipeline.resumeFailed"));
    } finally {
      setTogglingId(null);
    }
  };

  const openWizard = (sourceId?: string, step = 0, routeRuleId?: string) => {
    setActiveId(sourceId || null);
    setActiveRouteRuleId(routeRuleId || null);
    setWizardMode(sourceId ? "edit" : "new");
    setWizardStep(step);
    setMode("wizard");
  };

  const stepIndex = (step?: PipelineStepId, kind?: SourcePipelineStatus["kind"]) => {
    return wizardStepIndex(step, kind || "discord");
  };

  const confirmDeletePipeline = async () => {
    if (!deleteTarget?.routeRuleId) {
      setDeleteTarget(null);
      setAlertMessage(t("execPipeline.deleteFailed"));
      return;
    }
    setDeletingId(deleteTarget.routeRuleId);
    try {
      await api.delete(`/config/pipelines/${deleteTarget.sourceId}`, {
        params: { rule_id: deleteTarget.routeRuleId },
      });
      setDeleteTarget(null);
      await onReload();
    } catch {
      setDeleteTarget(null);
      setAlertMessage(t("execPipeline.deleteFailed"));
    } finally {
      setDeletingId(null);
    }
  };

  if (mode === "wizard") {
    return (
      <PipelineWizard
        discordSources={discordSources}
        webhooks={webhooks}
        telegramSources={telegramSources}
        ingestBase={ingestBase}
        routeRules={routeRules}
        wizardMode={wizardMode}
        initialSourceId={activeId || undefined}
        initialRouteRuleId={activeRouteRuleId || undefined}
        initialStep={wizardStep}
        onCreateWebhook={onCreateWebhook}
        onClose={() => setMode("list")}
        onComplete={async () => {
          if (onWizardComplete) await onWizardComplete();
          else await onReload();
          setMode("list");
        }}
        onReload={onReload}
        onGoToBrokers={onGoToBrokers}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{t("execPipeline.title")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t("execPipeline.subtitle")}</p>
        </div>
        <button type="button" className="btn-primary" onClick={() => openWizard(undefined, 0)}>
          {t("execPipeline.create")}
        </button>
      </div>

      {pipelines.length === 0 ? (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-3 sm:px-5">
            <p className="text-sm font-semibold text-slate-900">{t("execPipeline.emptyTitle")}</p>
            <p className="mt-0.5 text-xs text-slate-500">{t("execPipeline.empty")}</p>
          </div>
          <div className="space-y-4 px-4 py-5 sm:px-5">
            <div className="flex flex-wrap items-center gap-2">
              {(["connect", "parse", "action", "broker"] as const).map((key, i, arr) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-500">
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-600">
                      {i + 1}
                    </span>
                    {t(`execPipeline.emptyStep.${key}`)}
                  </span>
                  {i < arr.length - 1 ? <span className="text-slate-300">→</span> : null}
                </div>
              ))}
            </div>
            <button type="button" className="btn-primary" onClick={() => openWizard(undefined, 0)}>
              {t("execPipeline.create")}
            </button>
          </div>
        </div>
      ) : (
        <ul className="space-y-4">
          {pipelines.map((item) => (
            <li
              key={item.pipelineKey}
              className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
            >
              {/* Header */}
              <div className="border-b border-slate-100 bg-slate-50/60 px-3 py-2.5 sm:px-4">
                <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {resolveWebhookUrl(item) ? (
                        <CopyWebhookButton url={resolveWebhookUrl(item)} />
                      ) : null}
                      <PipelineCardTitle item={item} />
                      {item.paused ? (
                        <span className="rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-amber-200">
                          {t("execPipeline.paused")}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
                      <p className="text-[11px] text-slate-500">
                        {t("pipeline.todayStats", {
                          signals: item.todaySignals,
                          filled: item.todayFilled,
                          pending: item.todayPending,
                        })}
                      </p>
                      <SourcePipelineBar
                        status={item}
                        inline
                        onStepClick={(step) =>
                          openWizard(item.sourceId, stepIndex(step, item.kind), item.routeRuleId)
                        }
                      />
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-1.5">
                    {item.routeRuleId ? (
                      item.paused ? (
                        <button
                          type="button"
                          className="btn-primary text-xs"
                          disabled={Boolean(togglingId)}
                          onClick={() => void togglePipelineRun(item.routeRuleId!, false)}
                        >
                          {togglingId === item.routeRuleId ? "…" : t("execPipeline.resume")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                          disabled={Boolean(togglingId)}
                          onClick={() => void togglePipelineRun(item.routeRuleId!, true)}
                        >
                          {togglingId === item.routeRuleId ? "…" : t("execPipeline.pause")}
                        </button>
                      )
                    ) : null}
                    {item.kind === "webhook" || item.sourceId.startsWith("wh-") ? (
                      <button
                        type="button"
                        className="btn-secondary text-xs"
                        disabled={Boolean(togglingId)}
                        onClick={() => setJsonModalOpen(true)}
                      >
                        {t("webhookJson.signalJson")}
                      </button>
                    ) : null}
                    {item.nextStep ? (
                      <button
                        type="button"
                        className="btn-secondary text-xs"
                        disabled={Boolean(togglingId)}
                        onClick={() =>
                          openWizard(item.sourceId, stepIndex(item.nextStep, item.kind), item.routeRuleId)
                        }
                      >
                        {t("pipeline.configureStep")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn-secondary text-xs"
                        disabled={Boolean(togglingId)}
                        onClick={() => openWizard(item.sourceId, 0, item.routeRuleId)}
                      >
                        {t("execPipeline.editPipeline")}
                      </button>
                    )}
                    <button
                      type="button"
                      className="rounded-lg border border-loss/30 px-3 py-1.5 text-xs font-medium text-loss hover:bg-loss-soft disabled:opacity-50"
                      disabled={deletingId === item.pipelineKey || Boolean(togglingId)}
                      onClick={() =>
                        setDeleteTarget({
                          sourceId: item.sourceId,
                          routeRuleId: item.routeRuleId,
                          name: pipelineDisplayName(item),
                        })
                      }
                    >
                      {deletingId === item.pipelineKey ? "…" : t("execPipeline.delete")}
                    </button>
                  </div>
                </div>
              </div>

              <div className="px-3 py-2 sm:px-4">
                <PipelineFlowBoard
                  sourceId={item.sourceId}
                  sourceKind={item.kind}
                  pipelineBroker={item.brokers[0]}
                  pipelineAccountLabel={
                    routeRules.find((r) => r.id === item.routeRuleId)?.account_label
                  }
                  pipelineAccountId={
                    routeRules.find((r) => r.id === item.routeRuleId)?.account_id
                  }
                  onAction={onReload}
                  maxRows={3}
                  compact
                  defaultCollapsed
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-slate-500">
        {t("execPipeline.brokerHint")}{" "}
        <button type="button" className="text-brand-600 hover:underline" onClick={onGoToBrokers}>
          {t("console.nav.brokers")}
        </button>
      </p>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("execPipeline.delete")}
        message={deleteTarget ? t("execPipeline.deleteConfirm", { name: deleteTarget.name }) : ""}
        confirmLabel={t("execPipeline.delete")}
        cancelLabel={t("execPipeline.cancel")}
        variant="danger"
        busy={Boolean(deletingId)}
        onClose={() => !deletingId && setDeleteTarget(null)}
        onConfirm={() => void confirmDeletePipeline()}
      />

      <ConfirmDialog
        open={Boolean(alertMessage)}
        title={t("execPipeline.alertTitle")}
        message={alertMessage}
        confirmLabel={t("execPipeline.alertOk")}
        alertOnly
        onClose={() => setAlertMessage("")}
      />

      <WebhookSignalJsonModal open={jsonModalOpen} onClose={() => setJsonModalOpen(false)} />
    </div>
  );
}
