import { isEtToday } from "./datetime";

export type PipelineStepId = "connect" | "parse" | "execute";

export type SourceKind = "discord" | "webhook" | "telegram";

export type ParseRule = {
  source_id: string;
  parse_mode: string;
  label?: string;
};

export type RouteRule = {
  id?: string;
  source_id: string;
  action: string;
  order_type_policy: string;
  signal_subtype?: string | null;
  default_quantity?: number | null;
  broker?: string | null;
  account_id?: string | null;
  account_label?: string | null;
  is_active?: boolean;
};

export type BrokerBinding = {
  broker: string;
  account_id: string;
  label?: string;
  enabled?: boolean;
};

export type BrokerCredential = {
  broker: string;
  account_id: string;
  label?: string;
  env?: string;
};

function resolvePipelineCredential(
  broker: string | null | undefined,
  accountId: string | null | undefined,
  accountLabel: string | null | undefined,
  credentials: BrokerCredential[],
): BrokerCredential | undefined {
  if (!broker) return undefined;
  const label = (accountLabel || "").trim();
  const account = (accountId || "").trim();
  if (label) {
    const byLabel = credentials.find((c) => c.broker === broker && (c.label || "") === label);
    if (byLabel) return byLabel;
  }
  if (account) {
    const byAccount = credentials.find(
      (c) => c.broker === broker && (c.account_id || "") === account,
    );
    if (byAccount) return byAccount;
  }
  return undefined;
}

/** 路由指定的券商是否已配置（Agent 绑定或云端凭证均可） */
export function pipelineBrokerReady(
  broker: string | null | undefined,
  accountId: string | null | undefined,
  bindings: BrokerBinding[],
  credentials: BrokerCredential[],
  accountLabel?: string | null,
): boolean {
  // 流水线必须显式指定券商；有全局券商账号 ≠ 已关联该信号源
  if (!broker) return false;
  const enabledBindings = bindings.filter((b) => b.enabled !== false);
  const label = (accountLabel || "").trim();
  const account = (accountId || "").trim();
  if (label) {
    if (enabledBindings.some((b) => b.broker === broker && (b.label || "") === label)) {
      return true;
    }
    if (credentials.some((c) => c.broker === broker && (c.label || "") === label)) {
      return true;
    }
    // 账号改名后 label 会漂，仍按 account_id 认同一资金账号
    if (account) {
      if (enabledBindings.some((b) => b.broker === broker && (b.account_id || "") === account)) {
        return true;
      }
      if (credentials.some((c) => c.broker === broker && (c.account_id || "") === account)) {
        return true;
      }
    }
    return false;
  }
  const bindingOk = enabledBindings.some(
    (b) => b.broker === broker && (!account || (b.account_id || "") === account),
  );
  if (bindingOk) return true;
  return credentials.some(
    (c) => c.broker === broker && (!account || (c.account_id || "") === account),
  );
}

export type ChannelBrokerDuplicate = {
  sourceId: string;
  name: string;
  channelIds: string[];
};

/** 是否已有其他流水线监听相同频道并使用相同券商账号 */
export function findDuplicateChannelBroker(params: {
  sourceId: string;
  channelIds: string[];
  broker: string;
  accountId: string;
  accountLabel?: string;
  discordSources: Array<{
    source_id: string;
    name: string;
    channel_ids?: string[];
    bridge_mode?: string;
  }>;
  routeRules: RouteRule[];
}): ChannelBrokerDuplicate | null {
  const { sourceId, channelIds, broker, accountId, accountLabel, discordSources, routeRules } = params;
  if (!channelIds.length || !broker) return null;

  const channelSet = new Set(channelIds);
  const ruleBySource = new Map(routeRules.map((r) => [r.source_id, r]));
  const targetLabel = (accountLabel || "").trim();
  const targetAccount = accountId || "";

  for (const src of discordSources) {
    if (src.source_id === sourceId) continue;
    if (src.bridge_mode && src.bridge_mode !== "personal") continue;
    const otherChannels = src.channel_ids || [];
    const overlap = otherChannels.filter((id) => channelSet.has(id));
    if (!overlap.length) continue;

    const rule = ruleBySource.get(src.source_id);
    if (!rule?.broker || rule.broker !== broker) continue;
    if (targetLabel) {
      if ((rule.account_label || "") !== targetLabel) continue;
    } else if ((rule.account_id || "") !== targetAccount) {
      continue;
    }

    return { sourceId: src.source_id, name: src.name, channelIds: overlap };
  }
  return null;
}

export function formatChannelLabels(
  channelIds: string[],
  labels?: Record<string, string>,
): string {
  return channelIds.map((id) => labels?.[id] || id).join(" · ");
}

/** 流水线选频道等场景：自定义名【频道名】；二者相同时只显示一项。 */
export function sourceChannelDisplayName(source: {
  channel_ids?: string[];
  channel_labels?: Record<string, string>;
  name?: string;
}): string {
  const channels = formatChannelLabels(source.channel_ids || [], source.channel_labels);
  const custom = source.name?.trim() || "";
  if (custom && channels) {
    if (custom === channels) return custom;
    return `${custom}【${channels}】`;
  }
  return custom || channels || "My Discord";
}

export type PipelineSource = {
  source_id: string;
  name: string;
  kind: SourceKind;
  is_active?: boolean;
  channel_ids?: string[];
  channel_labels?: Record<string, string>;
  chat_ids?: string[];
};

export type PipelineExecution = {
  source_id: string;
  signal_id: string;
  status: string;
  broker: string;
  fill_price?: number | null;
  created_at?: string;
  signal?: Record<string, unknown>;
  detail?: string | null;
};

export type SourcePipelineStatus = {
  sourceId: string;
  routeRuleId?: string;
  pipelineKey: string;
  name: string;
  kind: SourceKind;
  connected: boolean;
  paused: boolean;
  hasParse: boolean;
  parseMode?: string;
  hasAction: boolean;
  action?: string;
  orderTypePolicy?: string;
  hasBroker: boolean;
  brokers: string[];
  /** 路由关联的资金账号 / 连接模式 id（用于正式/模拟判断） */
  brokerAccountId?: string;
  /** 云端凭证 env（paper/live/sandbox 等） */
  brokerEnv?: string;
  isActive: boolean;
  todaySignals: number;
  todayFilled: number;
  todayPending: number;
  ready: boolean;
  nextStep?: PipelineStepId;
};

export type PipelineStepState = {
  id: PipelineStepId;
  done: boolean;
  warning?: boolean;
  label: string;
  detail?: string;
};

const FILLED_STATUSES = new Set(["FILLED", "PARTIALLY_FILLED", "cloud_executed"]);
const PENDING_STATUSES = new Set(["PENDING_CONFIRM", "ROUTING", "DISPATCHED", "DEFERRED"]);

function inferSourceKind(sourceId: string): SourceKind {
  if (sourceId.startsWith("wh-")) return "webhook";
  if (sourceId.startsWith("tg-")) return "telegram";
  return "discord";
}

/** 合并 Discord / Webhook 源与已保存的路由/解析规则，避免「已保存但未出现在列表」的流水线丢失。 */
export function mergePipelineSources(
  discordSources: Array<{
    source_id: string;
    name: string;
    bridge_mode?: string;
    channel_ids?: string[];
    channel_labels?: Record<string, string>;
    is_active?: boolean;
  }>,
  routeRules: RouteRule[],
  parseRules: ParseRule[],
  webhooks: Array<{ source_id: string; label?: string }> = [],
  telegramSources: Array<{
    source_id: string;
    name: string;
    chat_ids?: string[];
    chat_labels?: Record<string, string>;
    is_active?: boolean;
  }> = [],
): PipelineSource[] {
  const byId = new Map<string, PipelineSource>();

  for (const s of discordSources) {
    if (s.bridge_mode !== "personal") continue;
    byId.set(s.source_id, {
      source_id: s.source_id,
      name: s.name || s.source_id,
      kind: "discord",
      is_active: s.is_active,
      channel_ids: s.channel_ids,
      channel_labels: s.channel_labels,
    });
  }

  for (const w of webhooks) {
    byId.set(w.source_id, {
      source_id: w.source_id,
      name: w.label?.trim() || "Webhook",
      kind: "webhook",
      is_active: true,
    });
  }

  for (const s of telegramSources) {
    byId.set(s.source_id, {
      source_id: s.source_id,
      name: s.name || s.source_id,
      kind: "telegram",
      is_active: s.is_active,
      chat_ids: s.chat_ids,
      channel_ids: s.chat_ids,
      channel_labels: s.chat_labels,
    });
  }

  const ensure = (sourceId: string) => {
    if (!sourceId || byId.has(sourceId)) return;
    byId.set(sourceId, {
      source_id: sourceId,
      name: sourceId,
      kind: inferSourceKind(sourceId),
      is_active: true,
    });
  };

  for (const r of routeRules) ensure(r.source_id);
  for (const p of parseRules) ensure(p.source_id);

  return Array.from(byId.values()).sort((a, b) => a.source_id.localeCompare(b.source_id));
}

/** 列表标题：流水线 ID 来自 route rule，与信号源无关 */
export function pipelineIdSuffix(status: SourcePipelineStatus): string {
  if (status.routeRuleId) return status.routeRuleId.replace(/-/g, "").slice(-6);
  return status.sourceId.replace(/^dc-|^wh-|^tg-/, "").slice(-6);
}

export function pipelineDisplayName(status: SourcePipelineStatus): string {
  const broker = status.brokers[0];
  const suffix = pipelineIdSuffix(status);
  if (broker) return `${status.name} · ${broker.toUpperCase()} (${suffix})`;
  return `${status.name} (${suffix})`;
}

export function pipelineKeyFromRule(rule: RouteRule): string {
  if (rule.id) return rule.id;
  return `${rule.source_id}:${rule.broker || "_"}:${rule.account_label || rule.account_id || "_"}`;
}

function buildStatusForSource(
  src: PipelineSource,
  routeRule: RouteRule | undefined,
  parseRules: ParseRule[],
  bindings: BrokerBinding[],
  executions: PipelineExecution[],
  credentials: BrokerCredential[],
): SourcePipelineStatus {
  const sourceParseRules = parseRules.filter((r) => r.source_id === src.source_id);
  const hasChannels =
    src.kind === "discord"
      ? (src.channel_ids?.length ?? 0) > 0
      : src.kind === "telegram"
        ? (src.chat_ids?.length ?? src.channel_ids?.length ?? 0) > 0
        : true;
  const sourceConnected =
    src.kind === "discord" || src.kind === "telegram"
      ? src.is_active !== false && hasChannels
      : true;
  const paused = routeRule != null && routeRule.is_active === false;
  const connected = sourceConnected;
  const hasParse = src.kind === "webhook" || sourceParseRules.length > 0;
  const hasAction = Boolean(routeRule);
  const pipelineBroker = routeRule?.broker;
  const hasBroker = pipelineBrokerReady(
    pipelineBroker,
    routeRule?.account_id,
    bindings,
    credentials,
    routeRule?.account_label,
  );
  const hasExecute = hasAction && hasBroker;
  const brokerLabels = pipelineBroker ? [pipelineBroker] : [];
  const matchedCred = resolvePipelineCredential(
    pipelineBroker,
    routeRule?.account_id,
    routeRule?.account_label,
    credentials,
  );
  const brokerAccountId = (routeRule?.account_id || matchedCred?.account_id || "").trim() || undefined;
  const brokerEnv = (matchedCred?.env || "").trim() || undefined;

  const srcExecs = executions.filter((e) => {
    if (e.source_id !== src.source_id || !isEtToday(e.created_at)) return false;
    if (!routeRule?.broker) return true;
    if ((e.broker || "").toLowerCase() !== routeRule.broker.toLowerCase()) return false;
    return true;
  });

  const steps: PipelineStepId[] =
    src.kind === "webhook" ? ["connect", "execute"] : ["connect", "parse", "execute"];
  const doneFlags =
    src.kind === "webhook" ? [connected, hasExecute] : [connected, hasParse, hasExecute];
  const nextIdx = doneFlags.findIndex((d) => !d);
  const nextStep = nextIdx >= 0 ? steps[nextIdx] : undefined;

  return {
    sourceId: src.source_id,
    routeRuleId: routeRule?.id,
    pipelineKey: routeRule ? pipelineKeyFromRule(routeRule) : src.source_id,
    name: src.name,
    kind: src.kind,
    connected,
    paused,
    hasParse,
    parseMode:
      sourceParseRules.length > 1
        ? String(sourceParseRules.length)
        : sourceParseRules[0]?.parse_mode,
    hasAction,
    action: routeRule?.action,
    orderTypePolicy: routeRule?.order_type_policy,
    hasBroker,
    brokers: brokerLabels,
    brokerAccountId,
    brokerEnv,
    isActive: connected && hasParse && hasAction && hasBroker && !paused,
    todaySignals: srcExecs.length,
    todayFilled: srcExecs.filter((e) => FILLED_STATUSES.has(e.status.toUpperCase())).length,
    todayPending: srcExecs.filter((e) => PENDING_STATUSES.has(e.status.toUpperCase())).length,
    ready: doneFlags.every(Boolean),
    nextStep,
  };
}

export function buildPipelineStatuses(
  sources: PipelineSource[],
  parseRules: ParseRule[],
  routeRules: RouteRule[],
  bindings: BrokerBinding[],
  executions: PipelineExecution[],
  credentials: BrokerCredential[] = [],
): SourcePipelineStatus[] {
  const sourceById = new Map(sources.map((s) => [s.source_id, s]));

  // 仅展示已关联路由的流水线；信号源在向导中间步创建，最后一步 PUT route-rules 才挂上。
  const statuses: SourcePipelineStatus[] = [];

  for (const rule of routeRules) {
    const src = sourceById.get(rule.source_id) || {
      source_id: rule.source_id,
      name: rule.source_id,
      kind: inferSourceKind(rule.source_id),
      is_active: true,
    };
    statuses.push(buildStatusForSource(src, rule, parseRules, bindings, executions, credentials));
  }

  return statuses.sort((a, b) => a.pipelineKey.localeCompare(b.pipelineKey));
}

function executeStepDetail(
  status: SourcePipelineStatus,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (status.hasAction && status.hasBroker) {
    return t("pipeline.stepExecuteOk", {
      action: actionLabel(status.action, t),
      brokers: status.brokers.join(", "),
    });
  }
  if (!status.hasAction) return t("pipeline.stepActionMissing");
  return t("pipeline.stepBrokerMissing");
}

export function wizardStepIndex(step: PipelineStepId | undefined, kind: SourceKind): number {
  if (kind === "webhook") {
    if (step === "execute") return 1;
    return 0;
  }
  const map: Record<PipelineStepId, number> = { connect: 0, parse: 1, execute: 2 };
  return step ? map[step] : 0;
}

export function pipelineSteps(
  status: SourcePipelineStatus,
  t: (key: string, opts?: Record<string, unknown>) => string,
): PipelineStepState[] {
  const executeReady = status.hasAction && status.hasBroker;
  const connectStep: PipelineStepState = {
    id: "connect",
    done: status.connected,
    label: t("pipeline.stepConnect"),
    detail: status.connected ? t("pipeline.stepConnectOk") : t("pipeline.stepConnectMissing"),
  };
  const executeStep: PipelineStepState = {
    id: "execute",
    done: executeReady && !status.paused,
    warning: status.paused,
    label: t("pipeline.stepExecute"),
    detail: status.paused
      ? t("pipeline.stepExecutePaused")
      : executeStepDetail(status, t),
  };
  if (status.kind === "webhook") {
    return [connectStep, executeStep];
  }
  return [
    connectStep,
    {
      id: "parse",
      done: status.hasParse,
      label: t("pipeline.stepParse"),
      detail: status.hasParse
        ? Number(status.parseMode) > 1
          ? t("pipeline.stepParseOkMulti", { count: status.parseMode })
          : t("pipeline.stepParseOk", { mode: status.parseMode || "—" })
        : t("pipeline.stepParseMissing"),
    },
    executeStep,
  ];
}

export function actionLabel(action: string | undefined, t: (key: string) => string): string {
  if (!action) return "—";
  const map: Record<string, string> = {
    auto_trade: t("pipeline.actionAuto"),
    notify_only: t("pipeline.actionNotify"),
    confirm_trade: t("pipeline.actionConfirm"),
    both: t("pipeline.actionBoth"),
  };
  return map[action] || action;
}
