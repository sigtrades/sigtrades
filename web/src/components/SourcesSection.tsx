import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { stopDiscordBridgeSource } from "../lib/discordBridge";
import { deleteSource, deleteWebhook } from "../lib/sources";
import { formatApiError } from "../lib/apiError";
import { groupWebhooksBySource, webhookIngestUrl } from "../lib/webhookSources";
import { sourceChannelDisplayName } from "../lib/sourcePipeline";
import ConfirmDialog from "./ConfirmDialog";
import DiscordPersonalSection from "./DiscordPersonalSection";
import ModalShell from "./ModalShell";
import WebhookJsonGuide from "./WebhookJsonGuide";

type Webhook = { url_path: string; source_id: string; token: string; label?: string };
type TelegramSource = { source_id: string; name: string; chat_ids: string[] };
type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  bridge_mode?: string;
  is_active?: boolean;
};

type SourceKind = "all" | "discord" | "webhook" | "telegram";

type WebhookTokenRow = { token: string; label?: string; url: string };

type SourceItem = {
  key: string;
  kind: "discord" | "webhook" | "telegram";
  name: string;
  detail: string;
  sourceId: string;
  webhookToken?: string;
  webhookTokens?: WebhookTokenRow[];
  active: boolean;
  hasPipeline: boolean;
};

type DeleteTarget = {
  kind: "discord" | "webhook" | "telegram";
  id: string;
  name: string;
  webhookToken?: string;
};

type Props = {
  ingestBase: string;
  webhooks: Webhook[];
  discordSources: DiscordSource[];
  telegramSources: TelegramSource[];
  linkedSourceIds: Set<string>;
  dcLabel: string;
  dcUserToken: string;
  onDcLabelChange: (v: string) => void;
  onDcUserTokenChange: (v: string) => void;
  onCreateWebhook: (label: string) => Promise<{ source_id: string; url: string }>;
  onCreateDiscordBridge: (payload: {
    label: string;
    user_token?: string;
    channel_ids: string[];
    channel_labels: Record<string, string>;
    guild_id?: string;
  }) => Promise<void>;
  onDiscordSourcesChanged?: () => void;
  onCreateTelegram: (label: string, chatIds: string[]) => Promise<void>;
  onGoToPipelines: () => void;
};

function KindIcon({ kind }: { kind: "discord" | "webhook" | "telegram" }) {
  if (kind === "discord") {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden>
        <path d="M20.3 4.4A17.2 17.2 0 0015.5 3c-.2.4-.5 1-.7 1.4a15.9 15.9 0 00-4.6 0C10 4 9.7 3.4 9.5 3a17.2 17.2 0 00-4.8 1.4C2.5 8.2 1.8 11.9 2.1 15.5a17.4 17.4 0 005.3 2.7c.4-.6.8-1.2 1.1-1.8-.6-.2-1.2-.5-1.7-.9.1-.1.2-.2.3-.3 3.3 1.5 6.8 1.5 10 0l.3.3c-.5.3-1.1.6-1.7.9.3.6.7 1.2 1.1 1.8a17.4 17.4 0 005.3-2.7c.4-4.2-.7-7.8-2.9-11.1ZM8.7 13.2c-.8 0-1.5-.8-1.5-1.7s.6-1.7 1.5-1.7 1.5.8 1.5 1.7-.7 1.7-1.5 1.7Zm6.6 0c-.8 0-1.5-.8-1.5-1.7s.6-1.7 1.5-1.7 1.5.8 1.5 1.7-.7 1.7-1.5 1.7Z" />
      </svg>
    );
  }
  if (kind === "webhook") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" strokeLinecap="round" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden>
      <path d="M21.9 4.6 2.8 11.5c-1.2.5-1.2 1.2-.2 1.5l4.9 1.5 1.9 5.8c.2.6.8.8 1.2.3l2.6-2.5 5.4 4c.9.5 1.5.2 1.7-.9L23.7 6.4c.3-1.3-.5-1.9-1.8-1.8Z" />
    </svg>
  );
}

function CopyButton({ value }: { value: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button type="button" onClick={copy} className="btn-secondary shrink-0 px-2.5 py-1 text-xs">
      {copied ? t("dashboard.copied") : t("dashboard.copy")}
    </button>
  );
}

export default function SourcesSection({
  ingestBase,
  webhooks,
  discordSources,
  telegramSources,
  linkedSourceIds,
  dcLabel,
  dcUserToken,
  onDcLabelChange,
  onDcUserTokenChange,
  onCreateWebhook,
  onCreateDiscordBridge,
  onDiscordSourcesChanged,
  onCreateTelegram,
  onGoToPipelines,
}: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<SourceKind>("all");
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [discordCreateOpen, setDiscordCreateOpen] = useState(false);
  const [discordEditId, setDiscordEditId] = useState<string | null>(null);
  const [webhookModalOpen, setWebhookModalOpen] = useState(false);
  const [webhookLabel, setWebhookLabel] = useState("");
  const [telegramModalOpen, setTelegramModalOpen] = useState(false);
  const [webhookBusy, setWebhookBusy] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [webhookError, setWebhookError] = useState("");
  const [tgLabel, setTgLabel] = useState("My Telegram");
  const [tgChats, setTgChats] = useState("");
  const [tgBusy, setTgBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [canWebhook, setCanWebhook] = useState(true);

  useEffect(() => {
    api
      .get("/config/entitlements")
      .then((r) => setCanWebhook(Boolean(r.data?.features?.webhook)))
      .catch(() => setCanWebhook(false));
  }, []);

  const discordMonitors = useMemo(
    () => discordSources.filter((s) => s.bridge_mode === "personal" && (s.channel_ids?.length ?? 0) > 0),
    [discordSources],
  );

  const allItems = useMemo((): SourceItem[] => {
    const discord: SourceItem[] = discordMonitors.map((s) => ({
      key: s.source_id,
      kind: "discord",
      name: sourceChannelDisplayName(s),
      detail:
        Object.values(s.channel_labels || {}).join(" · ") || s.channel_ids.join(", "),
      sourceId: s.source_id,
      active: s.is_active !== false,
      hasPipeline: linkedSourceIds.has(s.source_id),
    }));
    const wh: SourceItem[] = groupWebhooksBySource(
      webhooks.map((w) => ({
        token: w.token,
        source_id: w.source_id,
        label: w.label,
        url_path: w.url_path,
      })),
      t("dashboard.webhook"),
    ).map((g) => ({
      key: g.sourceId,
      kind: "webhook" as const,
      name: g.name,
      detail:
        g.tokens.length === 1
          ? webhookIngestUrl(ingestBase, g.tokens[0].url_path)
          : t("sourcesPage.webhookUrlCount", { count: g.tokens.length }),
      sourceId: g.sourceId,
      webhookTokens: g.tokens.map((row) => ({
        token: row.token,
        label: row.label,
        url: webhookIngestUrl(ingestBase, row.url_path),
      })),
      active: true,
      hasPipeline: linkedSourceIds.has(g.sourceId),
    }));
    const tg: SourceItem[] = telegramSources.map((s) => ({
      key: s.source_id,
      kind: "telegram",
      name: s.name,
      detail: s.chat_ids.join(", "),
      sourceId: s.source_id,
      active: true,
      hasPipeline: linkedSourceIds.has(s.source_id),
    }));
    return [...discord, ...wh, ...tg];
  }, [discordMonitors, webhooks, telegramSources, ingestBase, linkedSourceIds, t]);

  const filteredItems = useMemo(() => {
    if (filter === "all") return allItems;
    return allItems.filter((item) => item.kind === filter);
  }, [allItems, filter]);

  const counts = useMemo(
    () => ({
      all: allItems.length,
      discord: allItems.filter((i) => i.kind === "discord").length,
      webhook: allItems.filter((i) => i.kind === "webhook").length,
      telegram: allItems.filter((i) => i.kind === "telegram").length,
    }),
    [allItems],
  );

  const showDiscord = filter === "all" || filter === "discord";

  const openAdd = (kind: "discord" | "webhook" | "telegram") => {
    setAddMenuOpen(false);
    if (kind === "discord") setDiscordCreateOpen(true);
    if (kind === "webhook") {
      setWebhookLabel("");
      setWebhookUrl(null);
      setWebhookError("");
      setWebhookModalOpen(true);
    }
    if (kind === "telegram") {
      setTgLabel("My Telegram");
      setTgChats("");
      setTelegramModalOpen(true);
    }
  };

  const webhookLocked = !canWebhook;

  const handleCreateWebhook = async () => {
    setWebhookBusy(true);
    setWebhookError("");
    try {
      const result = await onCreateWebhook(webhookLabel.trim() || t("dashboard.webhook"));
      if (result) setWebhookUrl(result.url);
    } catch (e) {
      setWebhookError(formatApiError(e, t));
    } finally {
      setWebhookBusy(false);
    }
  };

  const handleCreateTelegram = async () => {
    const ids = tgChats.split(/[\s,]+/).filter(Boolean);
    if (!ids.length || !tgLabel.trim()) return;
    setTgBusy(true);
    try {
      await onCreateTelegram(tgLabel.trim(), ids);
      setTelegramModalOpen(false);
    } finally {
      setTgBusy(false);
    }
  };

  const stopDiscord = async (sourceId: string) => {
    setActionBusyId(sourceId);
    setActionError("");
    try {
      await stopDiscordBridgeSource(sourceId);
      onDiscordSourcesChanged?.();
    } catch {
      setActionError(t("sourcesPage.stopFailed"));
    } finally {
      setActionBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setActionError("");
    try {
      if (deleteTarget.kind === "webhook" && deleteTarget.webhookToken) {
        await deleteWebhook(deleteTarget.webhookToken);
      } else {
        await deleteSource(deleteTarget.id);
      }
      setDeleteTarget(null);
      onDiscordSourcesChanged?.();
    } catch {
      setActionError(t("sourcesPage.deleteFailed"));
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  };

  const kindBadge = (kind: SourceItem["kind"]) => (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
      <KindIcon kind={kind} />
      {t(`sourcesPage.kind.${kind}`)}
    </span>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{t("sourcesPage.title")}</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">{t("sourcesPage.subtitle")}</p>
        </div>
        <div className="relative">
          <button type="button" className="btn-primary" onClick={() => setAddMenuOpen((o) => !o)}>
            + {t("sourcesPage.add")}
          </button>
          {addMenuOpen ? (
            <>
              <button type="button" className="fixed inset-0 z-40 cursor-default" aria-label={t("common.close")} onClick={() => setAddMenuOpen(false)} />
              <div className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                {(["discord", "webhook", "telegram"] as const).map((kind) => {
                  const locked = kind === "webhook" && webhookLocked;
                  return (
                    <button
                      key={kind}
                      type="button"
                      className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-slate-50 ${
                        locked ? "text-slate-400" : "text-slate-700"
                      }`}
                      onClick={() => openAdd(kind)}
                    >
                      <span className="text-slate-500">
                        <KindIcon kind={kind} />
                      </span>
                      <span className="flex-1">
                        {t(`sourcesPage.add${kind === "discord" ? "Discord" : kind === "webhook" ? "Webhook" : "Telegram"}`)}
                      </span>
                      {locked ? (
                        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                          {t("nav.pricing")}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}
        </div>
      </div>

      {webhookLocked ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50/80 px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-amber-950">{t("dashboard.webhookUpgradeTitle")}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-amber-900/90">{t("dashboard.webhookUpgradeHint")}</p>
          </div>
          <Link to="/pricing" className="btn-primary shrink-0 px-3 py-1.5 text-xs">
            {t("dashboard.webhookUpgradeCta")}
          </Link>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {(["all", "discord", "webhook", "telegram"] as const).map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === id
                ? "bg-brand-400 text-slate-950 shadow-sm"
                : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            }`}
          >
            {t(`sourcesPage.filter.${id}`)}
            <span className="ml-1 tabular-nums opacity-70">({counts[id]})</span>
          </button>
        ))}
      </div>

      {showDiscord ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-500">
            {t("sourcesPage.discordTokenSection")}
          </p>
          <DiscordPersonalSection
            discordSources={discordSources}
            dcLabel={dcLabel}
            userToken={dcUserToken}
            onDcLabelChange={onDcLabelChange}
            onUserTokenChange={onDcUserTokenChange}
            onCreateBridgeSource={onCreateDiscordBridge}
            onSourcesChanged={onDiscordSourcesChanged}
            hideToolbar
            hideList
            createWizardOpen={discordCreateOpen}
            onCreateWizardOpenChange={setDiscordCreateOpen}
            externalEditSourceId={discordEditId}
            onExternalEditConsumed={() => setDiscordEditId(null)}
          />
        </div>
      ) : null}

      {filteredItems.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-12 text-center">
          <p className="text-sm text-slate-600">
            {filter === "all" ? t("sourcesPage.empty") : t("sourcesPage.emptyKind", { kind: t(`sourcesPage.kind.${filter}`) })}
          </p>
          <button type="button" className="btn-primary mt-4" onClick={() => openAdd(filter === "all" ? "discord" : filter)}>
            {t("sourcesPage.addFirst")}
          </button>
        </div>
      ) : (
        <ul className="space-y-3">
          {filteredItems.map((item) => (
            <li
              key={item.key}
              className={`rounded-xl border bg-white p-4 shadow-sm ${
                item.kind === "discord" && !item.active ? "border-slate-200 bg-slate-50" : "border-slate-200"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {kindBadge(item.kind)}
                    <p className="font-medium text-slate-900">{item.name}</p>
                    {item.kind === "discord" ? (
                      <span className={item.active ? "badge-success text-[10px]" : "badge-neutral text-[10px]"}>
                        {item.active ? t("dashboard.discordSourceActive") : t("dashboard.discordSourceStopped")}
                      </span>
                    ) : null}
                    {item.hasPipeline ? (
                      <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-medium text-brand-800 ring-1 ring-brand-100">
                        {t("sourcesPage.linkedPipeline")}
                      </span>
                    ) : null}
                  </div>
                  {item.kind === "webhook" && item.webhookTokens ? (
                    <>
                      {item.webhookTokens.length > 1 ? (
                        <p className="mt-1.5 text-sm text-slate-600">
                          {t("sourcesPage.webhookUrlCount", { count: item.webhookTokens.length })}
                        </p>
                      ) : null}
                      <ul className="mt-2 space-y-2">
                        {item.webhookTokens.map((row) => (
                          <li
                            key={row.token}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-2.5 py-2"
                          >
                            <div className="min-w-0 flex-1">
                              {row.label?.trim() && row.label.trim() !== item.name ? (
                                <p className="text-xs font-medium text-slate-700">{row.label}</p>
                              ) : null}
                              <p className="font-mono text-xs text-slate-600 break-all">{row.url}</p>
                            </div>
                            <div className="flex shrink-0 items-center gap-1.5">
                              <CopyButton value={row.url} />
                              {item.webhookTokens && item.webhookTokens.length > 1 ? (
                                <button
                                  type="button"
                                  className="btn-secondary border-loss/30 px-2 py-1 text-[10px] text-loss hover:bg-loss/5"
                                  disabled={deleteBusy}
                                  onClick={() =>
                                    setDeleteTarget({
                                      kind: "webhook",
                                      id: item.sourceId,
                                      name: row.label?.trim() || item.name,
                                      webhookToken: row.token,
                                    })
                                  }
                                >
                                  {t("sourcesPage.deleteUrl")}
                                </button>
                              ) : null}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <>
                      <p className="mt-1.5 text-sm text-slate-600 break-words">{item.detail}</p>
                      {item.kind === "webhook" ? (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <CopyButton value={item.detail} />
                        </div>
                      ) : null}
                    </>
                  )}
                  <p className="mt-1.5 text-xs text-slate-400">
                    {t("dashboard.sourceId")}: <span className="font-mono text-slate-500">{item.sourceId}</span>
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {item.kind === "discord" ? (
                    <>
                      <button
                        type="button"
                        className="btn-secondary px-2.5 py-1 text-xs"
                        disabled={actionBusyId === item.sourceId}
                        onClick={() => setDiscordEditId(item.sourceId)}
                      >
                        {t("dashboard.dcPersonalEdit")}
                      </button>
                      {item.active ? (
                        <button
                          type="button"
                          className="btn-secondary px-2.5 py-1 text-xs"
                          disabled={actionBusyId === item.sourceId}
                          onClick={() => void stopDiscord(item.sourceId)}
                        >
                          {t("dashboard.dcPersonalStop")}
                        </button>
                      ) : null}
                    </>
                  ) : null}
                  <button
                    type="button"
                    className="btn-secondary border-loss/30 px-2.5 py-1 text-xs text-loss hover:bg-loss/5"
                    disabled={deleteBusy}
                    onClick={() =>
                      setDeleteTarget({
                        kind: item.kind,
                        id: item.sourceId,
                        name: item.name,
                        webhookToken:
                          item.kind === "webhook" && (item.webhookTokens?.length ?? 0) === 1
                            ? item.webhookTokens?.[0]?.token
                            : undefined,
                      })
                    }
                  >
                    {item.kind === "webhook" && (item.webhookTokens?.length ?? 0) > 1
                      ? t("sourcesPage.deleteSource")
                      : t("sourcesPage.delete")}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {actionError ? <p className="text-sm text-loss">{actionError}</p> : null}

      <div className="rounded-xl border border-brand-100 bg-brand-50/60 px-4 py-3 text-sm text-brand-900">
        {t("sourcesPage.pipelineHint")}{" "}
        <button type="button" className="font-medium underline underline-offset-2 hover:text-brand-700" onClick={onGoToPipelines}>
          {t("sourcesPage.goPipelines")}
        </button>
      </div>

      <ConfirmDialog
        open={deleteTarget != null}
        title={t("sourcesPage.deleteTitle")}
        message={
          deleteTarget && linkedSourceIds.has(deleteTarget.id)
            ? t("sourcesPage.deleteConfirmWithPipeline", { name: deleteTarget.name })
            : t("sourcesPage.deleteConfirm", { name: deleteTarget?.name ?? "" })
        }
        confirmLabel={t("sourcesPage.delete")}
        cancelLabel={t("common.cancel")}
        variant="danger"
        busy={deleteBusy}
        onClose={() => !deleteBusy && setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />

      <ModalShell
        open={webhookModalOpen}
        title={t("sourcesPage.webhookModalTitle")}
        onClose={() => setWebhookModalOpen(false)}
        panelClassName={webhookUrl ? "max-w-2xl" : "max-w-lg"}
      >
        {webhookLocked && !webhookUrl ? (
          <div className="space-y-4">
            <p className="text-sm font-semibold text-amber-950">{t("dashboard.webhookUpgradeTitle")}</p>
            <p className="text-sm leading-relaxed text-slate-600">{t("dashboard.webhookUpgradeHint")}</p>
            <Link to="/pricing" className="btn-primary inline-flex" onClick={() => setWebhookModalOpen(false)}>
              {t("dashboard.webhookUpgradeCta")}
            </Link>
          </div>
        ) : (
          <>
        <p className="text-sm text-slate-600">{t("dashboard.webhookHint")}</p>
        {webhookError ? (
          <p className="mt-3 rounded-lg border border-loss/20 bg-loss/5 px-3 py-2 text-sm text-loss">{webhookError}</p>
        ) : null}
        {webhookUrl ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-800">
                <span className="break-all">{webhookUrl}</span>
              </div>
              <CopyButton value={webhookUrl} />
            </div>
            <WebhookJsonGuide compact />
            <button type="button" className="btn-primary w-full sm:w-auto" onClick={() => setWebhookModalOpen(false)}>
              {t("common.done")}
            </button>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <div>
              <label className="text-xs font-medium text-slate-600">{t("sourcesPage.webhookLabel")}</label>
              <input
                className="input mt-1 w-full"
                value={webhookLabel}
                onChange={(e) => setWebhookLabel(e.target.value)}
                placeholder={t("sourcesPage.webhookLabelPlaceholder")}
              />
            </div>
            <button type="button" className="btn-primary" disabled={webhookBusy} onClick={() => void handleCreateWebhook()}>
              {webhookBusy ? t("common.loading") : t("dashboard.createWebhook")}
            </button>
          </div>
        )}
          </>
        )}
      </ModalShell>

      <ModalShell open={telegramModalOpen} title={t("sourcesPage.telegramModalTitle")} onClose={() => setTelegramModalOpen(false)}>
        <p className="text-sm text-slate-600">{t("dashboard.telegramHint")}</p>
        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-600">{t("dashboard.tgLabel")}</label>
            <input className="input mt-1 w-full" value={tgLabel} onChange={(e) => setTgLabel(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600">{t("dashboard.tgChats")}</label>
            <input className="input mt-1 w-full font-mono text-sm" value={tgChats} onChange={(e) => setTgChats(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={() => setTelegramModalOpen(false)}>
              {t("common.cancel")}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={tgBusy || !tgLabel.trim() || !tgChats.trim()}
              onClick={() => void handleCreateTelegram()}
            >
              {tgBusy ? t("common.loading") : t("dashboard.tgConnect")}
            </button>
          </div>
        </div>
      </ModalShell>
    </div>
  );
}
