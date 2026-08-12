import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { formatApiError } from "../lib/apiError";
import api from "../lib/api";
import { webhookIngestUrl } from "../lib/webhookSources";
import { sourceChannelDisplayName } from "../lib/sourcePipeline";
import {
  createTelegramSource,
  parseTelegramChatIds,
  type TelegramSource,
} from "../lib/telegramSource";
import DiscordPersonalSection from "./DiscordPersonalSection";
import UiSelect from "./UiSelect";
import WebhookJsonGuide from "./WebhookJsonGuide";

export type PipelineSourceKind = "discord" | "webhook" | "telegram";

type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  guild_id?: string;
  bridge_mode?: string;
  is_active?: boolean;
};

type WebhookSource = { source_id: string; token: string; label?: string; url_path?: string };

type Props = {
  discordSources: DiscordSource[];
  webhooks: WebhookSource[];
  telegramSources?: TelegramSource[];
  ingestBase: string;
  sourceId: string;
  pipelineName?: string;
  onPipelineNameChange?: (name: string) => void;
  onSourceIdChange: (id: string) => void;
  onKindChange?: (kind: PipelineSourceKind) => void;
  onSourceCreated?: (id: string, source?: DiscordSource | TelegramSource) => void;
  onCreateWebhook: (label: string) => Promise<{ source_id: string; url: string }>;
  onReload: () => void | Promise<void>;
  mode?: "new" | "edit";
};

const KINDS: PipelineSourceKind[] = ["discord", "webhook", "telegram"];

function KindIcon({ kind }: { kind: PipelineSourceKind }) {
  if (kind === "discord") {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-6 w-6" aria-hidden>
        <path d="M20.3 4.4A17.2 17.2 0 0015.5 3c-.2.4-.5 1-.7 1.4a15.9 15.9 0 00-4.6 0C10 4 9.7 3.4 9.5 3a17.2 17.2 0 00-4.8 1.4C2.5 8.2 1.8 11.9 2.1 15.5a17.4 17.4 0 005.3 2.7c.4-.6.8-1.2 1.1-1.8-.6-.2-1.2-.5-1.7-.9.1-.1.2-.2.3-.3 3.3 1.5 6.8 1.5 10 0l.3.3c-.5.3-1.1.6-1.7.9.3.6.7 1.2 1.1 1.8a17.4 17.4 0 005.3-2.7c.4-4.2-.7-7.8-2.9-11.1ZM8.7 13.2c-.8 0-1.5-.8-1.5-1.7s.6-1.7 1.5-1.7 1.5.8 1.5 1.7-.7 1.7-1.5 1.7Zm6.6 0c-.8 0-1.5-.8-1.5-1.7s.6-1.7 1.5-1.7 1.5.8 1.5 1.7-.7 1.7-1.5 1.7Z" />
      </svg>
    );
  }
  if (kind === "webhook") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden>
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" strokeLinecap="round" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-6 w-6" aria-hidden>
      <path d="M21.9 4.6 2.8 11.5c-1.2.5-1.2 1.2-.2 1.5l4.9 1.5 1.9 5.8c.2.6.8.8 1.2.3l2.6-2.5 5.4 4c.9.5 1.5.2 1.7-.9L23.7 6.4c.3-1.3-.5-1.9-1.8-1.8Z" />
    </svg>
  );
}

function inferKindFromSourceId(sourceId: string): PipelineSourceKind {
  if (sourceId.startsWith("wh-")) return "webhook";
  if (sourceId.startsWith("tg-")) return "telegram";
  return "discord";
}

export default function PipelineSourceConnect({
  discordSources,
  webhooks,
  telegramSources = [],
  ingestBase,
  sourceId,
  pipelineName,
  onPipelineNameChange,
  onSourceIdChange,
  onKindChange,
  onSourceCreated,
  onCreateWebhook,
  onReload,
  mode = "new",
}: Props) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<PipelineSourceKind>("discord");
  const [createOpen, setCreateOpen] = useState(false);
  const [dcLabel, setDcLabel] = useState(pipelineName || "My Discord");
  const [dcUserToken, setDcUserToken] = useState("");
  const [webhookBusy, setWebhookBusy] = useState(false);
  const [webhookError, setWebhookError] = useState("");
  const [createdWebhookUrl, setCreatedWebhookUrl] = useState<string | null>(null);
  const [sessionWebhookId, setSessionWebhookId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [tgBusy, setTgBusy] = useState(false);
  const [tgError, setTgError] = useState("");
  const [tgChatIds, setTgChatIds] = useState("");
  const [sessionTelegramId, setSessionTelegramId] = useState<string | null>(null);
  const [canWebhook, setCanWebhook] = useState(true);

  const effectiveLabel = pipelineName ?? dcLabel;
  const setEffectiveLabel = (value: string) => {
    onPipelineNameChange?.(value);
    setDcLabel(value);
  };

  useEffect(() => {
    api
      .get("/config/entitlements")
      .then((r) => setCanWebhook(Boolean(r.data?.features?.webhook)))
      .catch(() => setCanWebhook(false));
  }, []);

  useEffect(() => {
    if (!sourceId) return;
    setKind(inferKindFromSourceId(sourceId));
  }, [sourceId]);

  useEffect(() => {
    onKindChange?.(kind);
  }, [kind, onKindChange]);

  useEffect(() => {
    if (!canWebhook && kind === "webhook" && mode === "new") {
      setKind("discord");
    }
  }, [canWebhook, kind, mode]);

  const selectable = discordSources.filter(
    (s) => s.bridge_mode === "personal" && (s.channel_ids?.length ?? 0) > 0,
  );

  const channelLabel = (s: DiscordSource | undefined) => {
    if (!s) return t("execPipeline.pickSource");
    const name = sourceChannelDisplayName(s);
    return s.is_active === false ? `${name} (${t("dashboard.discordSourceStopped")})` : name;
  };

  const selectedDiscord = useMemo(
    () => selectable.find((s) => s.source_id === sourceId),
    [selectable, sourceId],
  );

  const discordOptions = useMemo(
    () => selectable.map((s) => ({ value: s.source_id, label: channelLabel(s) })),
    [selectable, t],
  );

  const telegramOptions = useMemo(
    () =>
      telegramSources.map((s) => ({
        value: s.source_id,
        label: `${s.name}${s.chat_ids?.length ? ` (${s.chat_ids.join(", ")})` : ""}`,
      })),
    [telegramSources],
  );

  const handleCreateTelegram = async () => {
    setTgError("");
    const ids = parseTelegramChatIds(tgChatIds);
    if (!ids.length) {
      setTgError(t("execPipeline.telegramChatIdsRequired"));
      return;
    }
    setTgBusy(true);
    try {
      const created = await createTelegramSource({
        label: effectiveLabel.trim() || t("execPipeline.sourceKind.telegram"),
        chat_ids: ids,
      });
      setSessionTelegramId(created.source_id);
      onSourceIdChange(created.source_id);
      onSourceCreated?.(created.source_id, created);
      await onReload();
    } catch (e) {
      setTgError(formatApiError(e, t));
    } finally {
      setTgBusy(false);
    }
  };

  const webhookOptions = useMemo(() => {
    const seen = new Set<string>();
    return webhooks
      .filter((w) => {
        if (seen.has(w.source_id)) return false;
        seen.add(w.source_id);
        return true;
      })
      .map((w) => ({
        value: w.source_id,
        label: w.label?.trim() || w.source_id,
      }));
  }, [webhooks]);

  const webhooksForSource = useMemo(() => {
    if (!sourceId) return [];
    return webhooks.filter((w) => w.source_id === sourceId);
  }, [webhooks, sourceId]);

  const selectedWebhookUrl = useMemo(() => {
    if (createdWebhookUrl) return createdWebhookUrl;
    const primary = webhooksForSource[0];
    if (!primary) return null;
    return webhookIngestUrl(ingestBase, primary.url_path || `/ingest/wh/${primary.token}`);
  }, [webhooksForSource, ingestBase, createdWebhookUrl]);

  // 新建流水线时不要自动挂已有 Webhook：否则会显示「已创建」却因未在本会话新建而无法下一步

  useEffect(() => {
    if (mode === "edit" || !sourceId || kind !== "discord") return;
    const src = selectable.find((s) => s.source_id === sourceId);
    if (!src) return;
    onPipelineNameChange?.(sourceChannelDisplayName(src));
  }, [sourceId, mode, selectable, onPipelineNameChange, kind]);

  const createDiscordBridge = async (payload: {
    label: string;
    user_token?: string;
    channel_ids: string[];
    channel_labels: Record<string, string>;
    guild_id?: string;
  }) => {
    const label =
      payload.label.trim() ||
      sourceChannelDisplayName({
        channel_ids: payload.channel_ids,
        channel_labels: payload.channel_labels,
      });
    const { data } = await api.post("/config/discord-bridge-source", {
      ...payload,
      label,
      action: "confirm_trade",
      order_type_policy: "MKT_only",
    });
    const created: DiscordSource = {
      source_id: data.source_id,
      name: label,
      channel_ids: payload.channel_ids,
      channel_labels: payload.channel_labels,
      guild_id: payload.guild_id,
      bridge_mode: "personal",
    };
    onSourceIdChange(data.source_id);
    onSourceCreated?.(data.source_id, created);
    onPipelineNameChange?.(sourceChannelDisplayName(created));
    setCreateOpen(false);
    await Promise.resolve(onReload());
    return data.source_id as string;
  };

  const handleCreateWebhook = async () => {
    setWebhookBusy(true);
    setWebhookError("");
    try {
      const label = (pipelineName || effectiveLabel || t("dashboard.webhook")).trim();
      const result = await onCreateWebhook(label);
      setSessionWebhookId(result.source_id);
      onSourceIdChange(result.source_id);
      onSourceCreated?.(result.source_id);
      onPipelineNameChange?.(label);
      setCreatedWebhookUrl(result.url);
      await onReload();
    } catch (e) {
      setWebhookError(formatApiError(e, t));
    } finally {
      setWebhookBusy(false);
    }
  };

  const copyWebhookUrl = async () => {
    const url = selectedWebhookUrl || createdWebhookUrl;
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const openCreateModal = () => setCreateOpen(true);

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600">
        {mode === "edit" ? t("execPipeline.stepSourceEditHint") : t("execPipeline.stepSourceHint")}
      </p>
      {kind === "discord" ? (
        <p className="rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-xs text-brand-800">
          {t("execPipeline.sameChannelHint")}
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        {KINDS.map((k) => {
          const active = kind === k;
          const locked = k === "webhook" && !canWebhook && mode === "new";
          return (
            <button
              key={k}
              type="button"
              onClick={() => {
                if (locked) return;
                setKind(k);
              }}
              className={`rounded-xl border p-4 text-left transition-colors ${
                locked
                  ? "cursor-not-allowed border-amber-200 bg-amber-50/50 opacity-90"
                  : active
                    ? "border-brand-300 bg-brand-50 ring-1 ring-brand-200"
                    : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${active && !locked ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-500"}`}>
                <KindIcon kind={k} />
              </div>
              <p className="mt-3 font-medium text-slate-900">
                {t(`execPipeline.sourceKind.${k}`)}
                {locked ? (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                    {t("nav.pricing")}
                  </span>
                ) : null}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {locked ? t("dashboard.webhookUpgradeTitle") : t(`execPipeline.sourceKindDesc.${k}`)}
              </p>
            </button>
          );
        })}
      </div>

      {!canWebhook && mode === "new" ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50/80 px-4 py-3">
          <p className="text-xs leading-relaxed text-amber-900">{t("dashboard.webhookUpgradeHint")}</p>
          <Link to="/pricing" className="btn-primary shrink-0 px-3 py-1.5 text-xs">
            {t("dashboard.webhookUpgradeCta")}
          </Link>
        </div>
      ) : null}

      {kind === "discord" && mode === "new" ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
          {selectable.length > 0 ? (
            <div className="min-w-0 space-y-1.5">
              <label className="text-xs font-medium text-slate-600">{t("execPipeline.pickChannel")}</label>
              <UiSelect
                value={sourceId}
                onChange={onSourceIdChange}
                options={discordOptions}
                placeholder={t("execPipeline.pickSource")}
              />
              {selectedDiscord ? (
                <p className="text-xs text-profit">
                  {t("execPipeline.channelLinked")}: {channelLabel(selectedDiscord)}
                </p>
              ) : (
                <p className="text-xs text-slate-500">{t("execPipeline.pickChannelRequired")}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-600">{t("execPipeline.newChannelRequired")}</p>
          )}
          <button type="button" className="btn-secondary text-sm" onClick={openCreateModal}>
            + {t("execPipeline.newChannelLink")}
          </button>
        </div>
      ) : null}

      {kind === "discord" && mode === "edit" ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
          <div className="min-w-0 flex-1 space-y-1.5">
            <label className="text-xs font-medium text-slate-600">{t("execPipeline.pickChannel")}</label>
            <UiSelect
              value={sourceId}
              onChange={onSourceIdChange}
              options={discordOptions}
              placeholder={t("execPipeline.pickSource")}
            />
          </div>
        </div>
      ) : null}

      {kind === "webhook" && mode === "new" ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
          <p className="text-sm text-slate-600">{t("dashboard.webhookHint")}</p>
          {webhookError ? (
            <p className="rounded-lg border border-loss/20 bg-loss/5 px-3 py-2 text-sm text-loss">{webhookError}</p>
          ) : null}
          <button
            type="button"
            className="btn-secondary text-sm"
            disabled={webhookBusy}
            onClick={() => void handleCreateWebhook()}
          >
            + {t("execPipeline.newWebhook")}
          </button>
          {sessionWebhookId && sourceId === sessionWebhookId ? (
            <p className="text-xs text-profit">{t("execPipeline.webhookLinked")}</p>
          ) : null}
          {sessionWebhookId && selectedWebhookUrl ? (
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-600">{t("dashboard.copyUrl")}</label>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-800 break-all">
                  {selectedWebhookUrl}
                </div>
                <button type="button" className="btn-secondary shrink-0 text-xs" onClick={() => void copyWebhookUrl()}>
                  {copied ? t("dashboard.copied") : t("dashboard.copy")}
                </button>
              </div>
              <WebhookJsonGuide compact />
            </div>
          ) : null}
        </div>
      ) : null}

      {kind === "webhook" && mode === "edit" ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
          <p className="text-sm text-slate-600">{t("dashboard.webhookHint")}</p>
          {webhookError ? (
            <p className="rounded-lg border border-loss/20 bg-loss/5 px-3 py-2 text-sm text-loss">{webhookError}</p>
          ) : null}
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-1.5">
              <label className="text-xs font-medium text-slate-600">{t("execPipeline.pickWebhook")}</label>
              {webhookOptions.length === 0 ? (
                <p className="text-sm text-slate-500">{t("execPipeline.noWebhookYet")}</p>
              ) : (
                <UiSelect
                  value={sourceId}
                  onChange={onSourceIdChange}
                  options={webhookOptions}
                  placeholder={t("execPipeline.pickWebhook")}
                />
              )}
            </div>
            <button
              type="button"
              className="btn-secondary shrink-0 text-sm"
              disabled={webhookBusy}
              onClick={() => void handleCreateWebhook()}
            >
              + {t("execPipeline.newWebhook")}
            </button>
          </div>
          {selectedWebhookUrl ? (
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-600">{t("dashboard.copyUrl")}</label>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-800 break-all">
                  {selectedWebhookUrl}
                </div>
                <button type="button" className="btn-secondary shrink-0 text-xs" onClick={() => void copyWebhookUrl()}>
                  {copied ? t("dashboard.copied") : t("dashboard.copy")}
                </button>
              </div>
              <WebhookJsonGuide compact />
            </div>
          ) : null}
        </div>
      ) : null}

      {kind === "telegram" ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
          <p className="text-sm text-slate-600">{t("execPipeline.telegramHint")}</p>
          <ol className="list-decimal space-y-1 pl-5 text-xs text-slate-500">
            <li>{t("execPipeline.telegramStepAddBot")}</li>
            <li>{t("execPipeline.telegramStepGetChatId")}</li>
            <li>{t("execPipeline.telegramStepSave")}</li>
          </ol>
          {tgError ? (
            <p className="rounded-lg border border-loss/20 bg-loss/5 px-3 py-2 text-sm text-loss">{tgError}</p>
          ) : null}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600">{t("execPipeline.telegramChatIds")}</label>
            <input
              className="input font-mono text-sm"
              value={tgChatIds}
              onChange={(e) => setTgChatIds(e.target.value)}
              placeholder={t("execPipeline.telegramChatIdsPlaceholder")}
            />
          </div>
          {mode === "new" ? (
            <button
              type="button"
              className="btn-secondary text-sm"
              disabled={tgBusy}
              onClick={() => void handleCreateTelegram()}
            >
              + {t("execPipeline.newTelegram")}
            </button>
          ) : (
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-0 flex-1 space-y-1.5">
                <label className="text-xs font-medium text-slate-600">{t("execPipeline.pickTelegram")}</label>
                {telegramOptions.length === 0 ? (
                  <p className="text-sm text-slate-500">{t("execPipeline.noTelegramYet")}</p>
                ) : (
                  <UiSelect
                    value={sourceId}
                    onChange={onSourceIdChange}
                    options={telegramOptions}
                    placeholder={t("execPipeline.pickTelegram")}
                  />
                )}
              </div>
              <button
                type="button"
                className="btn-secondary shrink-0 text-sm"
                disabled={tgBusy}
                onClick={() => void handleCreateTelegram()}
              >
                + {t("execPipeline.newTelegram")}
              </button>
            </div>
          )}
          {sessionTelegramId && sourceId === sessionTelegramId ? (
            <p className="text-xs text-profit">{t("execPipeline.telegramLinked")}</p>
          ) : null}
        </div>
      ) : null}

      {kind === "discord" ? (
        <DiscordPersonalSection
          discordSources={discordSources}
          dcLabel={effectiveLabel}
          userToken={dcUserToken}
          onDcLabelChange={setEffectiveLabel}
          onUserTokenChange={setDcUserToken}
          onCreateBridgeSource={createDiscordBridge}
          onSourcesChanged={onReload}
          pipelineMode
          embedWizard={false}
          createWizardOpen={createOpen}
          onCreateWizardOpenChange={setCreateOpen}
          onSourceCreated={(id) => {
            onSourceIdChange(id);
            const src = discordSources.find((s) => s.source_id === id);
            onSourceCreated?.(id, src);
          }}
        />
      ) : null}
    </div>
  );
}
