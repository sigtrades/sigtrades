import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatApiError } from "../lib/apiError";
import { formatChannelLabels } from "../lib/sourcePipeline";
import {
  discordGuildIconCdnUrl,
  discordGuildIconUrl,
  formatTokenHint,
  fetchDiscordTokenStatus,
  fetchGuildChannels,
  fetchGuilds,
  fetchPreviewMessages,
  fetchTestMessages,
  saveDiscordToken,
  startTestListen,
  stopDiscordBridgeSource,
  stopTestListen,
  updateDiscordBridgeSource,
  validateDiscordToken,
  type DiscordChannel,
  type DiscordGuild,
  type TestMessage,
} from "../lib/discordBridge";

const FORWARDMSG_EXTENSION_URL =
  "https://chromewebstore.google.com/detail/discord-token-manager-%E2%80%94-f/pbapfagmjkedhheojjadjdcbkafjndoi";

type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  bridge_mode?: string;
  has_user_token?: boolean;
  user_token_hint?: string;
  discord_username?: string;
  is_active?: boolean;
};

type Props = {
  discordSources: DiscordSource[];
  dcLabel: string;
  userToken: string;
  onDcLabelChange: (v: string) => void;
  onUserTokenChange: (v: string) => void;
  onCreateBridgeSource: (payload: {
    label: string;
    user_token?: string;
    channel_ids: string[];
    channel_labels: Record<string, string>;
    guild_id?: string;
  }) => Promise<string | void>;
  onSourcesChanged?: () => void;
  pipelineMode?: boolean;
  embedWizard?: boolean;
  autoOpenWizard?: boolean;
  onSourceCreated?: (sourceId: string) => void;
  /** 流水线内由父组件控制「新建频道关联」弹窗 */
  createWizardOpen?: boolean;
  onCreateWizardOpenChange?: (open: boolean) => void;
  /** 信号源页：隐藏顶部工具栏，由父级统一「新增」入口 */
  hideToolbar?: boolean;
  /** 信号源页：列表由父级渲染，此处仅保留 Token 与弹窗 */
  hideList?: boolean;
  /** 父级触发的编辑（打开向导） */
  externalEditSourceId?: string | null;
  onExternalEditConsumed?: () => void;
};

function SetupRow({
  n,
  title,
  details,
  link,
  right,
  isLast,
}: {
  n: number;
  title: string;
  details?: string[];
  link?: { href: string; label: string };
  right: React.ReactNode;
  isLast?: boolean;
}) {
  return (
    <div className={`grid gap-4 lg:grid-cols-2 lg:gap-6 ${isLast ? "" : "border-b border-brand-100 pb-5"}`}>
      <div className="flex items-start gap-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
          {n}
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-sm font-medium text-slate-800">{title}</p>
          {link ? (
            <a
              href={link.href}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-600 hover:text-brand-700 hover:underline"
            >
              {link.label}
            </a>
          ) : null}
          {details?.map((line) => (
            <p key={line} className="text-sm leading-relaxed text-slate-600">
              {line}
            </p>
          ))}
        </div>
      </div>
      <div className="lg:pt-0.5">{right}</div>
    </div>
  );
}

type ChannelMessageGroup = {
  channelId: string;
  channelName: string;
  messages: TestMessage[];
};

function groupMessagesByChannel(messages: TestMessage[]): ChannelMessageGroup[] {
  const order: string[] = [];
  const groups = new Map<string, ChannelMessageGroup>();
  for (const m of messages) {
    let group = groups.get(m.channel_id);
    if (!group) {
      group = { channelId: m.channel_id, channelName: m.channel_name, messages: [] };
      groups.set(m.channel_id, group);
      order.push(m.channel_id);
    }
    group.messages.push(m);
  }
  return order.map((id) => groups.get(id)!);
}

function MessagePreviewPanel({
  messages,
  emptyText,
  compact,
}: {
  messages: TestMessage[];
  emptyText: string;
  compact?: boolean;
}) {
  const groups = useMemo(() => groupMessagesByChannel(messages), [messages]);

  if (messages.length === 0) {
    return <p className="text-xs text-slate-500">{emptyText}</p>;
  }

  return (
    <div
      className={`overflow-auto rounded-lg border border-slate-200 bg-white ${compact ? "max-h-36" : "max-h-52"}`}
    >
      {groups.map((group) => (
        <section key={group.channelId} className="border-b border-slate-100 last:border-b-0">
          <header className="sticky top-0 border-b border-slate-100 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-700">
            {group.channelName}
          </header>
          <ul className="space-y-1 px-2.5 py-2">
            {group.messages.map((m) => (
              <li key={m.message_id} className="text-xs leading-relaxed text-slate-600">
                <span className="font-medium text-slate-800">{m.author}</span>
                <span className="text-slate-400">: </span>
                <span className="whitespace-pre-wrap break-words">{m.content}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

type SelectionSummaryItem = {
  guildId: string;
  guildName: string;
  channels: string[];
};

function buildSelectionSummary(
  selectedGuilds: string[],
  selectedChannels: Record<string, string>,
  guildMap: Record<string, DiscordGuild>,
  channelsByGuild: Record<string, DiscordChannel[]>,
): SelectionSummaryItem[] {
  return selectedGuilds
    .map((guildId) => {
      const guild = guildMap[guildId];
      if (!guild) return null;
      const guildChannelIds = new Set((channelsByGuild[guildId] || []).map((c) => c.id));
      const channels = Object.entries(selectedChannels)
        .filter(([id]) => guildChannelIds.has(id))
        .map(([, label]) => label);
      if (!channels.length) return null;
      return { guildId, guildName: guild.name, channels };
    })
    .filter((item): item is SelectionSummaryItem => item !== null);
}

type ChannelPickerModalProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  tokenValid: boolean;
  guildSearch: string;
  onGuildSearchChange: (value: string) => void;
  guildLoading: boolean;
  onReload: () => void;
  filteredGuilds: DiscordGuild[];
  channelsByGuild: Record<string, DiscordChannel[]>;
  draftGuilds: string[];
  draftChannels: Record<string, string>;
  guildMap: Record<string, DiscordGuild>;
  onToggleGuild: (guildId: string) => void;
  onToggleChannel: (guild: DiscordGuild, ch: DiscordChannel) => void;
  channelUsedBy: Map<string, string[]>;
  labels: {
    title: string;
    searchGuild: string;
    reloadGuilds: string;
    guildLoading: string;
    noGuilds: string;
    channelCount: (count: number) => string;
    channelCountLoading: string;
    selectedGuilds: (count: number) => string;
    noChannels: string;
    noGuildSelected: string;
    cancel: string;
    confirm: string;
    usedInOtherPipeline: (names: string) => string;
  };
};

function ConfirmModal({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  busy,
  onClose,
  onConfirm,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={cancelLabel}
        disabled={busy}
        onClick={onClose}
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="relative w-full max-w-md rounded-t-2xl border border-slate-200 bg-white p-5 shadow-xl sm:rounded-xl"
      >
        <h3 id="confirm-modal-title" className="text-base font-semibold text-slate-900">
          {title}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{message}</p>
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" className="btn-secondary w-full text-sm sm:w-auto" disabled={busy} onClick={onClose}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className="btn-primary border-loss/20 bg-loss text-sm text-white hover:bg-loss/90"
            disabled={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function MonitorWizardModal({
  open,
  title,
  cancelLabel,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  cancelLabel: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={cancelLabel}
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-xl sm:max-h-[90vh] sm:rounded-xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button type="button" className="text-sm text-slate-500 hover:text-slate-700" onClick={onClose}>
            {cancelLabel}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto bg-white p-4 lg:p-5">{children}</div>
      </div>
    </div>
  );
}

function ChannelPickerModal({
  open,
  onClose,
  onConfirm,
  tokenValid,
  guildSearch,
  onGuildSearchChange,
  guildLoading,
  onReload,
  filteredGuilds,
  channelsByGuild,
  draftGuilds,
  draftChannels,
  guildMap,
  onToggleGuild,
  onToggleChannel,
  channelUsedBy,
  labels,
}: ChannelPickerModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={labels.cancel}
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-xl sm:max-h-[85vh] sm:rounded-xl"
      >
        <div className="border-b border-slate-200 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{labels.title}</h3>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4 lg:flex-row">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
            <div className="flex gap-2">
              <input
                className="input min-w-0 flex-1"
                placeholder={labels.searchGuild}
                value={guildSearch}
                onChange={(e) => onGuildSearchChange(e.target.value)}
                disabled={!tokenValid}
              />
              <button
                type="button"
                className="btn-secondary shrink-0 px-3 text-sm"
                disabled={!tokenValid || guildLoading}
                onClick={onReload}
              >
                {labels.reloadGuilds}
              </button>
            </div>
            <ul className="min-h-0 flex-1 space-y-2 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2">
              {filteredGuilds.length === 0 ? (
                <li className="px-2 py-3 text-center text-xs text-slate-500">
                  {guildLoading ? labels.guildLoading : labels.noGuilds}
                </li>
              ) : (
                filteredGuilds.map((g) => {
                  const selected = draftGuilds.includes(g.id);
                  const channels = channelsByGuild[g.id];
                  const count = channels?.length;
                  return (
                    <li key={g.id}>
                      <label
                        className={`flex w-full cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition ${
                          selected
                            ? "border-brand-400 bg-white ring-1 ring-brand-200"
                            : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="shrink-0"
                          disabled={!tokenValid}
                          checked={selected}
                          onChange={() => onToggleGuild(g.id)}
                        />
                        <GuildAvatar guild={g} size={36} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-slate-900">{g.name}</p>
                          <p className="text-xs text-slate-500">
                            {count === undefined
                              ? labels.channelCountLoading
                              : labels.channelCount(count)}
                          </p>
                        </div>
                      </label>
                    </li>
                  );
                })
              )}
            </ul>
            {draftGuilds.length > 0 ? (
              <p className="text-xs text-slate-500">{labels.selectedGuilds(draftGuilds.length)}</p>
            ) : null}
          </div>
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2">
              {draftGuilds.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-slate-500">{labels.noGuildSelected}</p>
              ) : (
                <div className="space-y-3">
                  {draftGuilds.map((guildId) => {
                    const guild = guildMap[guildId];
                    const channels = channelsByGuild[guildId] || [];
                    if (!guild) return null;
                    return (
                      <div key={guildId} className="space-y-1">
                        <div className="flex items-center gap-2 px-1 py-0.5">
                          <GuildAvatar guild={guild} size={22} />
                          <p className="truncate text-xs font-semibold text-slate-700">{guild.name}</p>
                        </div>
                        <ul className="space-y-0.5">
                          {channels.map((ch) => {
                            const usedBy = channelUsedBy.get(ch.id);
                            return (
                            <li key={ch.id}>
                              <label className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-1.5 text-sm hover:bg-white">
                                <input
                                  type="checkbox"
                                  checked={Boolean(draftChannels[ch.id])}
                                  onChange={() => onToggleChannel(guild, ch)}
                                />
                                <span className="min-w-0 truncate text-slate-700">#{ch.name}</span>
                                {usedBy?.length ? (
                                  <span className="ml-auto shrink-0 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-800 ring-1 ring-amber-200">
                                    {labels.usedInOtherPipeline(usedBy.join("、"))}
                                  </span>
                                ) : null}
                              </label>
                            </li>
                            );
                          })}
                          {channels.length === 0 ? (
                            <li className="px-2 py-1 text-xs text-slate-500">{labels.noChannels}</li>
                          ) : null}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" className="btn-secondary text-sm" onClick={onClose}>
            {labels.cancel}
          </button>
          <button type="button" className="btn-primary text-sm" onClick={onConfirm}>
            {labels.confirm}
          </button>
        </div>
      </div>
    </div>
  );
}

function MonitorLivePreview({
  sourceId,
  active,
  emptyText,
  stoppedText,
}: {
  sourceId: string;
  active: boolean;
  emptyText: string;
  stoppedText: string;
}) {
  const [messages, setMessages] = useState<TestMessage[]>([]);

  useEffect(() => {
    if (!active) {
      setMessages([]);
      return;
    }
    const poll = () => {
      fetchPreviewMessages(sourceId)
        .then((list) => setMessages(list.slice(-12)))
        .catch(() => setMessages([]));
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => window.clearInterval(timer);
  }, [sourceId, active]);

  if (!active) {
    return <p className="text-xs text-slate-400">{stoppedText}</p>;
  }

  return <MessagePreviewPanel messages={messages} emptyText={emptyText} compact />;
}

function TokenStatusBar({
  hint,
  user,
  onChange,
  labels,
}: {
  hint: string;
  user: string;
  onChange: () => void;
  labels: { userLabel: string; change: string };
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="inline-block rounded-lg bg-slate-200/80 px-3 py-2 font-mono text-sm tracking-wide text-slate-800">
          {formatTokenHint(hint)}
        </p>
        {user ? <p className="mt-1.5 text-xs text-profit">{labels.userLabel}</p> : null}
      </div>
      <button type="button" className="btn-secondary shrink-0 text-sm" onClick={onChange}>
        {labels.change}
      </button>
    </div>
  );
}

function GuildAvatar({ guild, size = 40 }: { guild: DiscordGuild; size?: number }) {
  const [srcIndex, setSrcIndex] = useState(0);
  useEffect(() => {
    setSrcIndex(0);
  }, [guild.id, guild.icon, size]);
  const iconSources = useMemo(() => {
    const px = size * 2;
    const proxy = discordGuildIconUrl(guild, px);
    const cdn = discordGuildIconCdnUrl(guild, px);
    return [proxy, cdn].filter((url): url is string => Boolean(url));
  }, [guild, size]);
  const initial = (guild.name || "?").trim().charAt(0).toUpperCase();
  const iconUrl = iconSources[srcIndex];

  if (!iconUrl || srcIndex >= iconSources.length) {
    return (
      <span
        className="flex shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700"
        style={{ width: size, height: size }}
        aria-hidden
      >
        {initial}
      </span>
    );
  }

  return (
    <img
      key={iconUrl}
      src={iconUrl}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      className="shrink-0 rounded-full object-cover"
      onError={() => setSrcIndex((i) => i + 1)}
    />
  );
}

export default function DiscordPersonalSection({
  discordSources,
  dcLabel,
  userToken,
  onDcLabelChange,
  onUserTokenChange,
  onCreateBridgeSource,
  onSourcesChanged,
  pipelineMode = false,
  embedWizard = false,
  autoOpenWizard = false,
  onSourceCreated,
  createWizardOpen,
  onCreateWizardOpenChange,
  hideToolbar = false,
  hideList = false,
  externalEditSourceId = null,
  onExternalEditConsumed,
}: Props) {
  const { t } = useTranslation();
  const [tokenUser, setTokenUser] = useState("");
  const [tokenValid, setTokenValid] = useState(false);
  const [tokenError, setTokenError] = useState("");
  const [hasSavedToken, setHasSavedToken] = useState(false);
  const [savedTokenHint, setSavedTokenHint] = useState("");
  const [savedTokenUser, setSavedTokenUser] = useState("");
  const [tokenEditing, setTokenEditing] = useState(false);
  const [guilds, setGuilds] = useState<DiscordGuild[]>([]);
  const [guildSearch, setGuildSearch] = useState("");
  const [guildLoading, setGuildLoading] = useState(false);
  const [channelsByGuild, setChannelsByGuild] = useState<Record<string, DiscordChannel[]>>({});
  const [selectedGuilds, setSelectedGuilds] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<Record<string, string>>({});
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftGuilds, setDraftGuilds] = useState<string[]>([]);
  const [draftChannels, setDraftChannels] = useState<Record<string, string>>({});
  const [testSessionId, setTestSessionId] = useState("");
  const [testMessages, setTestMessages] = useState<TestMessage[]>([]);
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [editingSourceId, setEditingSourceId] = useState("");
  const [sourceActionError, setSourceActionError] = useState("");
  const [sourceActionBusy, setSourceActionBusy] = useState(false);
  const [stopConfirmSource, setStopConfirmSource] = useState<DiscordSource | null>(null);
  const [wizardMode, setWizardMode] = useState<"hidden" | "create" | "edit">("hidden");

  const monitors = discordSources.filter(
    (s) => s.bridge_mode === "personal" && (s.channel_ids?.length ?? 0) > 0,
  );

  const channelsUsedElsewhere = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const s of monitors) {
      if (editingSourceId && s.source_id === editingSourceId) continue;
      for (const cid of s.channel_ids) {
        const prev = map.get(cid) || [];
        map.set(cid, [...prev, s.name]);
      }
    }
    return map;
  }, [monitors, editingSourceId]);

  const showWizard = wizardMode !== "hidden";
  /** 向导内始终展示 Token 步骤，便于查看脱敏提示并随时修改 */
  const showTokenStep = showWizard || !hasSavedToken || tokenEditing;

  const applySavedTokenState = useCallback((hint: string, user: string) => {
    setHasSavedToken(true);
    setSavedTokenHint(hint);
    setSavedTokenUser(user);
    setTokenUser(user);
    setTokenValid(true);
    setTokenEditing(false);
  }, []);

  useEffect(() => {
    if (autoOpenWizard && pipelineMode && embedWizard) {
      setWizardMode("create");
    }
  }, [autoOpenWizard, pipelineMode, embedWizard]);

  useEffect(() => {
    void fetchDiscordTokenStatus()
      .then((status) => {
        if (status.saved && status.hint) {
          applySavedTokenState(status.hint, status.user || "");
        }
      })
      .catch(() => {});
  }, [applySavedTokenState, discordSources]);

  const loadGuilds = useCallback(async () => {
    if (!tokenValid) return;
    const inlineToken = userToken.trim().length >= 50 ? userToken.trim() : undefined;
    if (!inlineToken && !hasSavedToken) return;
    setGuildLoading(true);
    try {
      const list = await fetchGuilds(inlineToken);
      setGuilds(list);
      setChannelsByGuild({});
      void Promise.all(
        list.map(async (g) => {
          try {
            const chs = await fetchGuildChannels(inlineToken, g.id);
            setChannelsByGuild((prev) => ({ ...prev, [g.id]: chs }));
          } catch {
            setChannelsByGuild((prev) => ({ ...prev, [g.id]: [] }));
          }
        }),
      );
    } catch {
      setGuilds([]);
    } finally {
      setGuildLoading(false);
    }
  }, [tokenValid, userToken, hasSavedToken]);

  useEffect(() => {
    void loadGuilds();
  }, [loadGuilds]);

  useEffect(() => {
    if (!tokenEditing) return;
    setSelectedGuilds([]);
    setSelectedChannels({});
    setDraftGuilds([]);
    setDraftChannels({});
    setPickerOpen(false);
  }, [userToken, tokenEditing]);

  const filteredGuilds = useMemo(() => {
    const q = guildSearch.trim().toLowerCase();
    if (!q) return guilds;
    return guilds.filter((g) => g.name.toLowerCase().includes(q));
  }, [guilds, guildSearch]);

  const guildMap = useMemo(() => Object.fromEntries(guilds.map((g) => [g.id, g])), [guilds]);

  const selectionSummary = useMemo(
    () => buildSelectionSummary(selectedGuilds, selectedChannels, guildMap, channelsByGuild),
    [selectedGuilds, selectedChannels, guildMap, channelsByGuild],
  );

  const channelLabel = (guildIds: string[], guild: DiscordGuild, ch: DiscordChannel) =>
    guildIds.length > 1 ? `${guild.name} / #${ch.name}` : `#${ch.name}`;

  const toggleDraftGuild = (guildId: string) => {
    setDraftGuilds((prev) => {
      const on = prev.includes(guildId);
      if (on) {
        const guildChannelIds = new Set((channelsByGuild[guildId] || []).map((c) => c.id));
        setDraftChannels((chs) => {
          const next = { ...chs };
          guildChannelIds.forEach((id) => delete next[id]);
          return next;
        });
        return prev.filter((id) => id !== guildId);
      }
      return [...prev, guildId];
    });
  };

  const toggleDraftChannel = (guild: DiscordGuild, ch: DiscordChannel) => {
    setDraftChannels((prev) => {
      const next = { ...prev };
      if (next[ch.id]) delete next[ch.id];
      else next[ch.id] = channelLabel(draftGuilds, guild, ch);
      return next;
    });
  };

  const openPicker = () => {
    setDraftGuilds([...selectedGuilds]);
    setDraftChannels({ ...selectedChannels });
    setGuildSearch("");
    setPickerOpen(true);
  };

  const confirmPicker = () => {
    const nextChannels: Record<string, string> = {};
    for (const guildId of draftGuilds) {
      const guild = guildMap[guildId];
      if (!guild) continue;
      for (const ch of channelsByGuild[guildId] || []) {
        if (draftChannels[ch.id]) {
          nextChannels[ch.id] = channelLabel(draftGuilds, guild, ch);
        }
      }
    }
    setSelectedGuilds([...draftGuilds]);
    setSelectedChannels(nextChannels);
    setPickerOpen(false);
    if (pipelineMode) {
      const label = formatChannelLabels(Object.keys(nextChannels), nextChannels);
      if (label) onDcLabelChange(label);
    }
  };

  useEffect(() => {
    if (!editingSourceId || !pickerOpen) return;
    const source = monitors.find((s) => s.source_id === editingSourceId);
    if (!source) return;
    const guildIds = Object.entries(channelsByGuild)
      .filter(([, channels]) => channels.some((c) => source.channel_ids.includes(c.id)))
      .map(([guildId]) => guildId);
    if (!guildIds.length || draftGuilds.length > 0) return;
    setSelectedGuilds(guildIds);
    setDraftGuilds(guildIds);
  }, [editingSourceId, pickerOpen, channelsByGuild, monitors, draftGuilds.length]);

  const closePicker = () => {
    setPickerOpen(false);
  };

  const clearTestState = () => {
    setTestMessages([]);
    setTestSessionId("");
    setTesting(false);
  };

  const resetWizardChannels = () => {
    setSelectedGuilds([]);
    setSelectedChannels({});
    setDraftGuilds([]);
    setDraftChannels({});
    setPickerOpen(false);
    clearTestState();
    setSaveError("");
  };

  const startNewMonitor = () => {
    if (!hasSavedToken && !tokenValid) {
      setWizardMode("create");
      return;
    }
    setWizardMode("create");
    setEditingSourceId("");
    onDcLabelChange(t("dashboard.dcPersonalDefaultLabel"));
    resetWizardChannels();
  };

  const cancelWizard = () => {
    if (testSessionId) void stopTestListen(testSessionId).catch(() => {});
    setWizardMode("hidden");
    setEditingSourceId("");
    resetWizardChannels();
    onCreateWizardOpenChange?.(false);
  };

  useEffect(() => {
    if (createWizardOpen === undefined) return;
    if (createWizardOpen) {
      setWizardMode("create");
      setEditingSourceId("");
      onDcLabelChange(t("dashboard.dcPersonalDefaultLabel"));
      resetWizardChannels();
    } else if (wizardMode !== "hidden") {
      cancelWizard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open/close driven by parent flag only
  }, [createWizardOpen]);

  const displayStep = (step: number) => (showTokenStep ? step : step - 1);

  useEffect(() => {
    if (!testSessionId || wizardMode === "hidden") return;
    const poll = () => {
      fetchTestMessages(testSessionId)
        .then(setTestMessages)
        .catch(() => setTestMessages([]));
    };
    poll();
    const timer = window.setInterval(poll, 3000);
    return () => window.clearInterval(timer);
  }, [testSessionId, wizardMode]);

  const handleValidateToken = async () => {
    setTokenError("");
    setBusy(true);
    try {
      const trimmed = userToken.trim();
      const user = await validateDiscordToken(trimmed);
      const saved = await saveDiscordToken(trimmed);
      applySavedTokenState(saved.hint, user.global_name || user.username || saved.user || "");
      onUserTokenChange("");
      onSourcesChanged?.();
      if (wizardMode === "hidden" && !hasSavedToken) setWizardMode("create");
    } catch (e) {
      setTokenValid(false);
      setTokenError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const handleChangeToken = () => {
    setTokenEditing(true);
    setTokenValid(false);
    setTokenError("");
    onUserTokenChange("");
  };

  const inlineToken = () => (userToken.trim().length >= 50 ? userToken.trim() : undefined);

  const handleStartTest = async () => {
    const ids = Object.keys(selectedChannels);
    if (!ids.length || (!inlineToken() && !hasSavedToken)) return;
    setSaveError("");
    setBusy(true);
    try {
      const sessionId = await startTestListen(ids, selectedChannels, inlineToken());
      setTestSessionId(sessionId);
      setTesting(true);
    } catch (e) {
      setSaveError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const handleStopTest = async () => {
    if (!testSessionId) {
      setTesting(false);
      return;
    }
    setSaveError("");
    setBusy(true);
    try {
      await stopTestListen(testSessionId);
    } catch (e) {
      setSaveError(formatApiError(e, t));
    } finally {
      setTestSessionId("");
      setTesting(false);
      setBusy(false);
    }
  };

  const handleConnect = async () => {
    const ids = Object.keys(selectedChannels);
    if (!ids.length || !dcLabel.trim() || !tokenValid) return;
    setSaveError("");
    setBusy(true);
    try {
      if (testSessionId) {
        await stopTestListen(testSessionId).catch(() => {});
        setTestSessionId("");
        setTesting(false);
      }
      const payload: {
        label: string;
        channel_ids: string[];
        channel_labels: Record<string, string>;
        guild_id?: string;
        user_token?: string;
      } = {
        label:
          dcLabel.trim() ||
          formatChannelLabels(ids, selectedChannels),
        channel_ids: ids,
        channel_labels: selectedChannels,
        guild_id: selectedGuilds[0] || undefined,
      };
      const token = inlineToken();
      if (token) payload.user_token = token;

      if (wizardMode === "edit" && editingSourceId) {
        await updateDiscordBridgeSource(editingSourceId, payload);
        onSourceCreated?.(editingSourceId);
      } else {
        const createdId = await onCreateBridgeSource(payload);
        if (typeof createdId === "string" && createdId) {
          onSourceCreated?.(createdId);
        }
      }

      clearTestState();
      setWizardMode("hidden");
      setEditingSourceId("");
      onUserTokenChange("");
      setTokenEditing(false);
      onCreateWizardOpenChange?.(false);
      // 流水线向导内也要刷新父级列表，否则「已保存频道」不出现
      await Promise.resolve(onSourcesChanged?.());
    } catch (e) {
      setSaveError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const canSave =
    tokenValid && Object.keys(selectedChannels).length > 0 && dcLabel.trim();

  const handleEditSource = (source: DiscordSource) => {
    const labels = { ...(source.channel_labels || {}) };
    const guildIds = Object.entries(channelsByGuild)
      .filter(([, channels]) => channels.some((c) => source.channel_ids.includes(c.id)))
      .map(([guildId]) => guildId);

    setWizardMode("edit");
    setEditingSourceId(source.source_id);
    setSourceActionError("");
    onDcLabelChange(source.name);
    setSelectedGuilds(guildIds);
    setSelectedChannels(labels);
    clearTestState();
  };

  useEffect(() => {
    if (!externalEditSourceId) return;
    const source = monitors.find((s) => s.source_id === externalEditSourceId);
    if (source) handleEditSource(source);
    onExternalEditConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- external edit trigger only
  }, [externalEditSourceId]);

  const handleStopSource = (source: DiscordSource) => {
    setStopConfirmSource(source);
  };

  const confirmStopSource = async () => {
    if (!stopConfirmSource) return;
    const source = stopConfirmSource;
    setSourceActionError("");
    setSourceActionBusy(true);
    try {
      await stopDiscordBridgeSource(source.source_id);
      setStopConfirmSource(null);
      if (editingSourceId === source.source_id) {
        setEditingSourceId("");
        setWizardMode("hidden");
        resetWizardChannels();
      }
      onSourcesChanged?.();
    } catch (e) {
      setSourceActionError(formatApiError(e, t));
    } finally {
      setSourceActionBusy(false);
    }
  };

  const tokenInputBlock = (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-slate-700">{t("dashboard.dcPersonalToken")}</label>
      {hasSavedToken && !tokenEditing ? (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
          <p className="rounded-lg bg-slate-200/80 px-3 py-2 font-mono text-sm tracking-wide text-slate-800">
            {formatTokenHint(savedTokenHint)}
          </p>
          {tokenUser ? (
            <p className="text-xs text-profit">{t("dashboard.dcPersonalTokenOk", { user: tokenUser })}</p>
          ) : null}
          <button type="button" className="btn-secondary text-sm" onClick={handleChangeToken}>
            {t("dashboard.dcPersonalChangeToken")}
          </button>
        </div>
      ) : (
        <>
          <input
            className="input w-full font-mono text-xs"
            type="text"
            autoComplete="off"
            spellCheck={false}
            placeholder={t("dashboard.dcPersonalTokenPlaceholder")}
            value={userToken}
            onChange={(e) => {
              onUserTokenChange(e.target.value);
              setTokenValid(false);
              setTokenUser("");
            }}
          />
          <button
            type="button"
            className="btn-secondary text-sm"
            disabled={userToken.trim().length < 50 || busy}
            onClick={handleValidateToken}
          >
            {t("dashboard.dcPersonalValidateToken")}
          </button>
          {hasSavedToken ? (
            <button
              type="button"
              className="text-xs text-slate-500 hover:text-slate-700"
              onClick={() => {
                setTokenEditing(false);
                setTokenValid(true);
                setTokenUser(savedTokenUser);
                onUserTokenChange("");
                setTokenError("");
              }}
            >
              {t("dashboard.dcPersonalCancelChangeToken")}
            </button>
          ) : null}
        </>
      )}
      {tokenError ? <p className="text-xs text-loss">{tokenError}</p> : null}
      <p className="text-xs text-slate-500">{t("dashboard.dcPersonalTokenStoredHint")}</p>
    </div>
  );

  const channelStepBlock = (
    <div className="space-y-3">
      <button type="button" className="btn-secondary text-sm" disabled={!tokenValid} onClick={openPicker}>
        {t("dashboard.dcPersonalOpenPicker")}
      </button>
      {selectionSummary.length === 0 ? (
        <p className="text-xs text-slate-500">{t("dashboard.dcPersonalSelectionEmpty")}</p>
      ) : (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
          {selectionSummary.map((item) => (
            <div key={item.guildId} className="text-sm leading-relaxed text-slate-700">
              <span className="font-medium text-slate-900">{item.guildName}</span>
              <span className="text-slate-400"> ｜ </span>
              <span>{item.channels.join(t("dashboard.dcPersonalChannelSep"))}</span>
            </div>
          ))}
          <p className="border-t border-slate-100 pt-2 text-xs text-slate-500">
            {t("dashboard.dcPersonalSelected", { count: Object.keys(selectedChannels).length })}
          </p>
        </div>
      )}
    </div>
  );

  const wizardBody = (
    <div className="space-y-5">
      <div className="mb-2 hidden text-xs font-medium uppercase tracking-wide text-slate-400 lg:grid lg:grid-cols-2 lg:gap-6 lg:px-1">
        <span>{t("dashboard.discordColGuide")}</span>
        <span>{t("dashboard.discordColForm")}</span>
      </div>
      {showTokenStep ? (
        <SetupRow
          n={1}
          title={t("dashboard.dcPersonalStep1Title")}
          link={{ href: FORWARDMSG_EXTENSION_URL, label: t("dashboard.dcPersonalExtensionLink") }}
          details={[t("dashboard.dcPersonalStep1a"), t("dashboard.dcPersonalStep1b")]}
          right={tokenInputBlock}
        />
      ) : null}
      <SetupRow
        n={displayStep(2)}
        title={t("dashboard.dcPersonalStep2Title")}
        details={[t("dashboard.dcPersonalStep2a")]}
        right={channelStepBlock}
      />
      <SetupRow
        n={displayStep(3)}
        title={t("dashboard.dcPersonalStep3Title")}
        details={[t("dashboard.dcPersonalStep3a")]}
        right={
          <div className="space-y-2">
            <button
              type="button"
              className={`text-sm ${testing ? "btn-secondary border-loss/30 text-loss hover:bg-loss/5" : "btn-secondary"}`}
              disabled={
                busy || (testing ? !testSessionId : !tokenValid || !Object.keys(selectedChannels).length)
              }
              onClick={testing ? handleStopTest : handleStartTest}
            >
              {testing ? t("dashboard.dcPersonalStopTest") : t("dashboard.dcPersonalStartTest")}
            </button>
            {testing ? (
              <p className="text-xs text-profit">{t("dashboard.dcPersonalListening")}</p>
            ) : (
              <p className="text-xs text-slate-500">{t("dashboard.dcPersonalIdle")}</p>
            )}
            <MessagePreviewPanel messages={testMessages} emptyText={t("dashboard.dcPersonalNoMessages")} />
          </div>
        }
      />
      <SetupRow
        n={displayStep(4)}
        title={wizardMode === "edit" ? t("dashboard.dcPersonalStep4EditTitle") : t("dashboard.dcPersonalStep4Title")}
        isLast
        right={
          <div className="space-y-2">
            <input
              className="input w-full"
              placeholder={t("dashboard.dcLabelPlaceholder")}
              value={dcLabel}
              onChange={(e) => onDcLabelChange(e.target.value)}
            />
            <button type="button" className="btn-primary" disabled={!canSave || busy} onClick={handleConnect}>
              {wizardMode === "edit"
                ? t("dashboard.dcPersonalSaveMonitor")
                : pipelineMode
                  ? t("dashboard.dcSaveChannel")
                  : t("dashboard.dcConnect")}
            </button>
            {saveError ? <p className="text-xs text-loss">{saveError}</p> : null}
          </div>
        }
      />
    </div>
  );

  return (
    <div className="space-y-4">
      {!pipelineMode && !hideToolbar ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-600">{t("dashboard.dcPersonalMonitorHint")}</p>
          <button
            type="button"
            className="btn-primary text-sm"
            disabled={sourceActionBusy}
            onClick={startNewMonitor}
          >
            {t("dashboard.dcPersonalNewMonitor")}
          </button>
        </div>
      ) : null}

      {hasSavedToken && !tokenEditing && !pipelineMode ? (
        <TokenStatusBar
          hint={savedTokenHint}
          user={savedTokenUser}
          onChange={handleChangeToken}
          labels={{
            userLabel: t("dashboard.dcPersonalTokenOk", { user: savedTokenUser }),
            change: t("dashboard.dcPersonalChangeToken"),
          }}
        />
      ) : hasSavedToken && tokenEditing ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">{tokenInputBlock}</div>
      ) : null}

      {pipelineMode && embedWizard && showWizard ? (
        <div className="rounded-xl border border-brand-100 bg-white p-4">
          <p className="mb-4 text-sm font-medium text-slate-800">
            {wizardMode === "edit" ? t("dashboard.dcPersonalEditMonitor") : t("dashboard.dcPersonalNewMonitor")}
          </p>
          {wizardBody}
        </div>
      ) : null}

      {!pipelineMode && !hideList && monitors.length > 0 ? (
        <div className="space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.dcPersonalMonitorList")}
          </p>
          <ul className="space-y-3">
            {monitors.map((s) => {
              const active = s.is_active !== false;
              return (
                <li
                  key={s.source_id}
                  className={`rounded-xl border p-4 shadow-sm ${
                    active ? "border-slate-200 bg-white" : "border-slate-200 bg-slate-50"
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className={`font-medium ${active ? "text-slate-900" : "text-slate-600"}`}>{s.name}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {Object.values(s.channel_labels || {}).join(t("dashboard.dcPersonalChannelSep")) ||
                          s.channel_ids.join(", ")}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <span className={active ? "badge-success" : "badge-neutral"}>
                        {active ? t("dashboard.discordSourceActive") : t("dashboard.discordSourceStopped")}
                      </span>
                      <button
                        type="button"
                        className="btn-secondary px-2.5 py-1 text-xs"
                        disabled={sourceActionBusy}
                        onClick={() => handleEditSource(s)}
                      >
                        {t("dashboard.dcPersonalEdit")}
                      </button>
                      {active ? (
                        <button
                          type="button"
                          className="btn-secondary border-loss/30 px-2.5 py-1 text-xs text-loss hover:bg-loss/5"
                          disabled={sourceActionBusy}
                          onClick={() => handleStopSource(s)}
                        >
                          {t("dashboard.dcPersonalStop")}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-3">
                    <p className="mb-1.5 text-xs font-medium text-slate-500">{t("dashboard.dcPersonalLatestMessages")}</p>
                    <MonitorLivePreview
                      sourceId={s.source_id}
                      active={active}
                      emptyText={t("dashboard.dcPersonalNoLiveMessages")}
                      stoppedText={t("dashboard.dcPersonalStoppedHint")}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
          {sourceActionError ? <p className="text-xs text-loss">{sourceActionError}</p> : null}
        </div>
      ) : null}

      {!embedWizard ? (
        <MonitorWizardModal
          open={showWizard}
          title={
            pipelineMode && wizardMode === "create"
              ? t("execPipeline.newChannelLink")
              : wizardMode === "edit"
                ? t("dashboard.dcPersonalEditMonitor")
                : t("dashboard.dcPersonalNewMonitor")
          }
          cancelLabel={t("dashboard.dcPersonalCancelWizard")}
          onClose={cancelWizard}
        >
          {wizardBody}
        </MonitorWizardModal>
      ) : null}

      <ChannelPickerModal
        open={pickerOpen}
        onClose={closePicker}
        onConfirm={confirmPicker}
        tokenValid={tokenValid}
        guildSearch={guildSearch}
        onGuildSearchChange={setGuildSearch}
        guildLoading={guildLoading}
        onReload={() => void loadGuilds()}
        filteredGuilds={filteredGuilds}
        channelsByGuild={channelsByGuild}
        draftGuilds={draftGuilds}
        draftChannels={draftChannels}
        guildMap={guildMap}
        onToggleGuild={toggleDraftGuild}
        onToggleChannel={toggleDraftChannel}
        channelUsedBy={channelsUsedElsewhere}
        labels={{
          title: t("dashboard.dcPersonalPickerTitle"),
          searchGuild: t("dashboard.dcPersonalSearchGuild"),
          reloadGuilds: t("dashboard.dcPersonalReloadGuilds"),
          guildLoading: t("dashboard.dcPersonalGuildLoading"),
          noGuilds: t("dashboard.dcPersonalNoGuilds"),
          channelCount: (count) => t("dashboard.dcPersonalChannelCount", { count }),
          channelCountLoading: t("dashboard.dcPersonalChannelCountLoading"),
          selectedGuilds: (count) => t("dashboard.dcPersonalSelectedGuilds", { count }),
          noChannels: t("dashboard.dcPersonalNoChannels"),
          noGuildSelected: t("dashboard.dcPersonalPickerNoGuildSelected"),
          cancel: t("dashboard.dcPersonalPickerCancel"),
          confirm: t("dashboard.dcPersonalPickerConfirm"),
          usedInOtherPipeline: (names) => t("execPipeline.channelUsedElsewhere", { names }),
        }}
      />

      <ConfirmModal
        open={stopConfirmSource !== null}
        title={t("dashboard.dcPersonalStopConfirmTitle")}
        message={t("dashboard.dcPersonalStopConfirm")}
        confirmLabel={t("dashboard.dcPersonalStop")}
        cancelLabel={t("dashboard.dcPersonalCancelWizard")}
        busy={sourceActionBusy}
        onClose={() => {
          if (!sourceActionBusy) setStopConfirmSource(null);
        }}
        onConfirm={() => void confirmStopSource()}
      />
    </div>
  );
}
