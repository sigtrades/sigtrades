import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  findDuplicateChannelBroker,
  formatChannelLabels,
  type RouteRule,
} from "../lib/sourcePipeline";
import { renameDiscordPipelineSource } from "../lib/discordBridge";
import { renameTelegramSource, type TelegramSource } from "../lib/telegramSource";
import { formatApiError } from "../lib/apiError";
import ConfirmDialog from "./ConfirmDialog";
import ParseConfigSection, { type ParseConfigHandle } from "./ParseConfigSection";
import PipelineSourceConnect from "./PipelineSourceConnect";
import SourceRouteConfig, {
  type BrokerOption,
  type SourceRouteHandle,
  loadBrokerOptions,
} from "./SourceRouteConfig";

type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  guild_id?: string;
  is_active?: boolean;
  bridge_mode?: string;
};

type WebhookSource = { source_id: string; token: string; label?: string };

type Props = {
  discordSources: DiscordSource[];
  webhooks: WebhookSource[];
  telegramSources?: TelegramSource[];
  ingestBase: string;
  routeRules: RouteRule[];
  wizardMode: "new" | "edit";
  initialSourceId?: string;
  initialRouteRuleId?: string;
  initialStep?: number;
  onCreateWebhook: (label: string) => Promise<{ source_id: string; url: string }>;
  onClose: () => void;
  onComplete: () => void | Promise<void>;
  onReload: () => void | Promise<void>;
  onGoToBrokers?: () => void;
};

type WizardStepKey = "source" | "parse" | "execute";

const ALL_STEPS: WizardStepKey[] = ["source", "parse", "execute"];
const WEBHOOK_STEPS: WizardStepKey[] = ["source", "execute"];

function isWebhookSource(sourceId: string, sourceKind: string): boolean {
  return sourceId.startsWith("wh-") || sourceKind === "webhook";
}

function normalizeInitialStep(step: number, skipParse: boolean): number {
  if (skipParse) {
    if (step <= 0) return 0;
    return 1;
  }
  if (step >= 3) return 2;
  if (step >= 2) return 2;
  return step;
}

export default function PipelineWizard({
  discordSources,
  webhooks,
  telegramSources = [],
  ingestBase,
  routeRules,
  wizardMode,
  initialSourceId,
  initialRouteRuleId,
  initialStep = 0,
  onCreateWebhook,
  onClose,
  onComplete,
  onReload,
  onGoToBrokers,
}: Props) {
  const { t } = useTranslation();
  const [sourceKind, setSourceKind] = useState<"discord" | "webhook" | "telegram">("discord");
  const skipParse = isWebhookSource(initialSourceId || "", sourceKind);
  const [step, setStep] = useState(normalizeInitialStep(initialStep, skipParse));
  const [sourceId, setSourceId] = useState(initialSourceId || "");
  const [routeRuleId, setRouteRuleId] = useState(initialRouteRuleId || "");
  const [pipelineName, setPipelineName] = useState("");
  const [parseCanProceed, setParseCanProceed] = useState(false);
  const [executeCanFinish, setExecuteCanFinish] = useState(false);
  const [brokerKey, setBrokerKey] = useState("");
  const [brokerOptions, setBrokerOptions] = useState<BrokerOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [duplicateConfirm, setDuplicateConfirm] = useState<{
    existingName: string;
    brokerLabel: string;
    channelText: string;
  } | null>(null);
  const [sessionSources, setSessionSources] = useState<DiscordSource[]>([]);

  const parseRef = useRef<ParseConfigHandle>(null);
  const routeRef = useRef<SourceRouteHandle>(null);
  const createdInSessionRef = useRef<string | null>(null);

  const wizardSteps = useMemo(
    () => (isWebhookSource(sourceId, sourceKind) ? WEBHOOK_STEPS : ALL_STEPS),
    [sourceId, sourceKind],
  );
  const currentStepKey = wizardSteps[step] ?? wizardSteps[0];

  const resolveBrokerKeyFromRule = useCallback(
    (options: BrokerOption[], rule?: RouteRule | null) => {
      if (!rule?.broker) return "";
      const byLabel = rule.account_label
        ? `${rule.broker}:${rule.account_label}`
        : "";
      const byAccount = `${rule.broker}:${rule.account_id || ""}`;
      if (byLabel && options.some((o) => o.key === byLabel)) return byLabel;
      if (options.some((o) => o.key === byAccount)) return byAccount;
      const match = options.find(
        (o) =>
          o.broker === rule.broker &&
          ((rule.account_label && o.account_label === rule.account_label) ||
            (rule.account_id && o.account_id === rule.account_id)),
      );
      return match?.key || byLabel || byAccount;
    },
    [],
  );

  const refreshBrokers = useCallback(async () => {
    const options = await loadBrokerOptions(t);
    setBrokerOptions(options);
    // 用函数式更新，避免异步回来时用过期的空 brokerKey 把已回填的券商盖成列表第一项
    setBrokerKey((prev) => {
      if (prev) return prev;
      if (wizardMode === "edit") {
        const rule = initialRouteRuleId
          ? routeRules.find((r) => r.id === initialRouteRuleId)
          : routeRules.find((r) => r.source_id === (sourceId || initialSourceId));
        return resolveBrokerKeyFromRule(options, rule) || "";
      }
      return options[0]?.key || "";
    });
  }, [
    t,
    wizardMode,
    initialRouteRuleId,
    initialSourceId,
    sourceId,
    routeRules,
    resolveBrokerKeyFromRule,
  ]);

  // 编辑时只回填一次名称；勿随 discordSources/webhooks 轮询覆盖用户输入
  const nameSeededForRef = useRef<string | null>(null);

  useEffect(() => {
    const webhook = isWebhookSource(initialSourceId || "", sourceKind);
    setSourceId(initialSourceId || "");
    setRouteRuleId(initialRouteRuleId || "");
    setBrokerKey("");
    createdInSessionRef.current = null;
    setSessionSources([]);
    setStep(normalizeInitialStep(initialStep, webhook));
    nameSeededForRef.current = null;
    if (wizardMode === "new") {
      setPipelineName("");
    } else if (initialSourceId?.startsWith("wh-")) {
      setSourceKind("webhook");
    } else if (initialSourceId?.startsWith("tg-")) {
      setSourceKind("telegram");
    }
  }, [initialSourceId, initialRouteRuleId, wizardMode, initialStep]);

  useEffect(() => {
    if (wizardMode !== "edit" || !initialSourceId) return;
    if (nameSeededForRef.current === initialSourceId) return;
    const src = discordSources.find((s) => s.source_id === initialSourceId);
    const tg = telegramSources.find((s) => s.source_id === initialSourceId);
    const wh = webhooks.find((w) => w.source_id === initialSourceId);
    if (src) {
      // 只用自定义 label，不要 sourceChannelDisplayName（含【频道】后缀）
      setPipelineName(src.name?.trim() || "");
      nameSeededForRef.current = initialSourceId;
    } else if (tg) {
      setPipelineName(tg.name?.trim() || "");
      nameSeededForRef.current = initialSourceId;
    } else if (wh) {
      setPipelineName(wh.label?.trim() || "Webhook");
      nameSeededForRef.current = initialSourceId;
    }
  }, [wizardMode, initialSourceId, discordSources, webhooks, telegramSources]);

  useEffect(() => {
    if (step >= wizardSteps.length - 1 && currentStepKey === "execute") {
      void refreshBrokers();
    }
  }, [step, wizardSteps.length, currentStepKey, refreshBrokers]);

  useEffect(() => {
    if (step >= wizardSteps.length) {
      setStep(Math.max(0, wizardSteps.length - 1));
    }
  }, [step, wizardSteps.length]);

  const mergedDiscordSources = useMemo(() => {
    const map = new Map(discordSources.map((s) => [s.source_id, s]));
    for (const s of sessionSources) map.set(s.source_id, s);
    return [...map.values()];
  }, [discordSources, sessionSources]);

  const prepareSourceForWizard = async (): Promise<string | null> => {
    if (!sourceId) return null;

    if (wizardMode === "edit") {
      if (sourceId.startsWith("tg-")) {
        await renameTelegramSource(sourceId, pipelineName);
      } else if (!sourceId.startsWith("wh-")) {
        await renameDiscordPipelineSource(sourceId, pipelineName);
      }
      await onReload();
      return sourceId;
    }

    // 新建：允许选用已保存的信号源，或本会话刚创建的源（Webhook/Telegram 仍须先点新建接入）。
    const sessionOk = createdInSessionRef.current === sourceId;
    if (sourceId.startsWith("wh-")) {
      if (!sessionOk && !webhooks.some((w) => w.source_id === sourceId)) {
        setError(t("execPipeline.mustCreateNewSource"));
        return null;
      }
      return sourceId;
    }
    if (sourceId.startsWith("tg-")) {
      if (!sessionOk && !telegramSources.some((s) => s.source_id === sourceId)) {
        setError(t("execPipeline.mustCreateNewSource"));
        return null;
      }
      await renameTelegramSource(sourceId, pipelineName);
      return sourceId;
    }

    const discordOk =
      sessionOk ||
      mergedDiscordSources.some(
        (s) =>
          s.source_id === sourceId &&
          s.bridge_mode === "personal" &&
          (s.channel_ids?.length ?? 0) > 0,
      );
    if (!discordOk) {
      setError(t("execPipeline.mustCreateNewSource"));
      return null;
    }
    await renameDiscordPipelineSource(sourceId, pipelineName);
    return sourceId;
  };

  const handleSourceCreated = (id: string, source?: DiscordSource | TelegramSource) => {
    createdInSessionRef.current = id;
    setSourceId(id);
    if (source && "channel_ids" in source) {
      setSessionSources((prev) => [...prev.filter((s) => s.source_id !== id), source]);
    }
  };

  const canNext =
    (currentStepKey === "source" && Boolean(sourceId)) ||
    (currentStepKey === "parse" && parseCanProceed);

  const handleNext = async () => {
    setError("");
    if (currentStepKey === "source") {
      if (!sourceId || busy) return;
      setBusy(true);
      try {
        const nextId = await prepareSourceForWizard();
        if (!nextId) return;
        setStep((s) => s + 1);
      } catch (e) {
        setError(formatApiError(e, t));
      } finally {
        setBusy(false);
      }
      return;
    }
    if (currentStepKey === "parse") {
      if (!parseRef.current?.canProceed() || busy) return;
      setBusy(true);
      try {
        const ok = await parseRef.current?.save();
        if (!ok) return;
        setStep((s) => s + 1);
      } finally {
        setBusy(false);
      }
      return;
    }
    setStep((s) => s + 1);
  };

  const doSaveAndComplete = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const ok = await routeRef.current?.save();
      if (!ok) return;
      // 等刷新与关闭完成前保持 busy，避免保存成功后按钮短暂可再次点击
      await onReload();
      await onComplete();
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!routeRef.current?.canFinish()) {
      setError(t("execPipeline.brokerRequired"));
      return;
    }

    const currentSource = mergedDiscordSources.find((s) => s.source_id === sourceId);
    const selectedBroker = brokerOptions.find((o) => o.key === brokerKey);
    if (currentSource && selectedBroker) {
      const duplicate = findDuplicateChannelBroker({
        sourceId,
        channelIds: currentSource.channel_ids || [],
        broker: selectedBroker.broker,
        accountId: selectedBroker.account_id,
        accountLabel: selectedBroker.account_label,
        discordSources: mergedDiscordSources,
        routeRules,
      });
      if (duplicate) {
        setDuplicateConfirm({
          existingName: duplicate.name,
          brokerLabel: selectedBroker.label,
          channelText: formatChannelLabels(
            duplicate.channelIds,
            currentSource.channel_labels,
          ),
        });
        return;
      }
    }

    await doSaveAndComplete();
  };

  const sourcesForParse = useMemo(() => {
    const discord = mergedDiscordSources
      .filter((s) => s.source_id === sourceId || !sourceId)
      .map((s) => ({
        source_id: s.source_id,
        name: s.name,
        channel_ids: s.channel_ids,
        bridge_mode: s.bridge_mode,
        is_active: s.is_active,
        kind: "discord" as const,
      }));
    const wh = webhooks
      .filter((w) => w.source_id === sourceId || !sourceId)
      .map((w) => ({
        source_id: w.source_id,
        name: w.label?.trim() || "Webhook",
        kind: "webhook" as const,
      }));
    const tg = telegramSources
      .filter((s) => s.source_id === sourceId || !sourceId)
      .map((s) => ({
        source_id: s.source_id,
        name: s.name,
        chat_ids: s.chat_ids,
        channel_ids: s.chat_ids,
        is_active: s.is_active,
        kind: "telegram" as const,
      }));
    // 当前会话刚创建的 Telegram 可能尚未进入 reload 列表
    if (sourceId.startsWith("tg-") && !tg.some((s) => s.source_id === sourceId)) {
      tg.push({
        source_id: sourceId,
        name: pipelineName || sourceId,
        chat_ids: [],
        channel_ids: [],
        is_active: true,
        kind: "telegram",
      });
    }
    return [...discord, ...wh, ...tg];
  }, [mergedDiscordSources, webhooks, telegramSources, sourceId, pipelineName]);

  return (
    <div className="card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            {wizardMode === "new" ? t("execPipeline.wizardTitleNew") : t("execPipeline.wizardTitleEdit")}
          </h2>
          <p className="mt-1 text-sm text-slate-600">{t("execPipeline.wizardHint")}</p>
        </div>
        <button type="button" className="btn-secondary text-sm" onClick={onClose}>
          {t("execPipeline.cancel")}
        </button>
      </div>

      <ol className="mt-5 flex flex-wrap gap-2">
        {wizardSteps.map((key, i) => (
          <li
            key={key}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              i === step
                ? "border-brand-300 bg-brand-50 text-brand-700"
                : i < step
                  ? "border-profit/30 bg-profit-soft text-profit"
                  : "border-slate-200 text-slate-400"
            }`}
          >
            {i + 1}. {t(`execPipeline.step.${key}`)}
          </li>
        ))}
      </ol>

      <div className="mt-6">
        {currentStepKey === "source" ? (
          <div className="space-y-5">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-3">
                <label className="shrink-0 text-xs font-medium text-slate-600">
                  {t("execPipeline.pipelineName")}
                </label>
                <input
                  className="input min-w-0 flex-1"
                  value={pipelineName}
                  onChange={(e) => setPipelineName(e.target.value)}
                  placeholder={t("execPipeline.pipelineNamePlaceholder")}
                />
              </div>
              <p className="text-xs text-slate-500">{t("execPipeline.pipelineNameHint")}</p>
            </div>
            <PipelineSourceConnect
              discordSources={mergedDiscordSources}
              webhooks={webhooks}
              telegramSources={telegramSources}
              ingestBase={ingestBase}
              sourceId={sourceId}
              pipelineName={pipelineName}
              onPipelineNameChange={setPipelineName}
              onSourceIdChange={setSourceId}
              onKindChange={setSourceKind}
              onSourceCreated={handleSourceCreated}
              onCreateWebhook={onCreateWebhook}
              onReload={onReload}
              mode={wizardMode}
            />
            {isWebhookSource(sourceId, sourceKind) ? (
              <p className="rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-xs text-brand-800">
                {t("execPipeline.webhookSkipParseHint")}
              </p>
            ) : null}
          </div>
        ) : null}

        {currentStepKey === "parse" && sourceId ? (
          <ParseConfigSection
            ref={parseRef}
            sources={sourcesForParse}
            fixedSourceId={sourceId}
            embedWizard
            onError={setError}
            onCanProceedChange={setParseCanProceed}
          />
        ) : null}

        {currentStepKey === "execute" && sourceId ? (
          <SourceRouteConfig
            ref={routeRef}
            sourceId={sourceId}
            routeRuleId={routeRuleId || undefined}
            initialRule={
              routeRuleId
                ? routeRules.find((r) => r.id === routeRuleId)
                : routeRules.find((r) => r.source_id === sourceId)
            }
            embedWizard
            brokerOptions={brokerOptions}
            brokerKey={brokerKey}
            onBrokerKeyChange={setBrokerKey}
            onGoToBrokers={onGoToBrokers}
            onError={setError}
            onCanFinishChange={setExecuteCanFinish}
          />
        ) : null}
      </div>

      {error ? <p className="mt-3 text-sm text-loss">{error}</p> : null}

      <div className="mt-6 flex flex-wrap justify-between gap-2">
        <button
          type="button"
          className="btn-secondary text-sm"
          disabled={step === 0 || busy}
          onClick={() => setStep((s) => Math.max(0, s - 1))}
        >
          {t("execPipeline.prev")}
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {currentStepKey === "source" && !sourceId ? (
            <p className="text-xs text-amber-700">
              {sourceKind === "webhook"
                ? t("execPipeline.pickWebhookRequired")
                : t("execPipeline.pickChannelRequired")}
            </p>
          ) : null}
          {step < wizardSteps.length - 1 ? (
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={!canNext || busy}
              onClick={() => void handleNext()}
            >
              {busy ? t("execPipeline.saving") : t("execPipeline.next")}
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={busy || !executeCanFinish}
              onClick={() => void finish()}
            >
              {busy ? t("execPipeline.saving") : t("execPipeline.finish")}
            </button>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(duplicateConfirm)}
        title={t("execPipeline.duplicateChannelBrokerTitle")}
        message={
          duplicateConfirm
            ? t("execPipeline.duplicateChannelBrokerMessage", {
                name: duplicateConfirm.existingName,
                channels: duplicateConfirm.channelText,
                broker: duplicateConfirm.brokerLabel,
              })
            : ""
        }
        confirmLabel={t("execPipeline.duplicateChannelBrokerConfirm")}
        cancelLabel={t("execPipeline.cancel")}
        busy={busy}
        onClose={() => !busy && setDuplicateConfirm(null)}
        onConfirm={() => {
          setDuplicateConfirm(null);
          void doSaveAndComplete();
        }}
      />
    </div>
  );
}
