import type { TimelineExecution } from "../components/SignalTimeline";
import { formatEtDateTimeCompact, parseEtTimestamp } from "./datetime";
import { dedupeAttemptsByAccount, pickPrimaryAttempt } from "./executionGroups";

export type RawMessage = {
  message_id: string;
  channel_id?: string;
  channel_name?: string;
  author?: string;
  content: string;
  ts?: number;
};

export type ParseStatus = "pending" | "parsed" | "failed" | "skipped";

export type FlowFilter = "all" | "parsed" | "executed";

export type PipelineFlowRow = {
  id: string;
  signalId: string;
  sortTime: number;
  message: RawMessage | null;
  execution: TimelineExecution | null;
  parseStatus: ParseStatus;
};

export function signalIdFromMessageId(messageId: string, kind: "discord" | "telegram" | "webhook"): string {
  if (kind === "discord") return `dc-${messageId}`;
  if (kind === "telegram") return `tg-${messageId}`;
  return messageId;
}

export function messageIdFromSignalId(signalId: string): string | null {
  const m = signalId.match(/^(?:dc|tg)-(.+)$/);
  return m ? m[1] : null;
}

function rawTextFromSignal(signal?: Record<string, unknown>): string {
  const meta = (signal?.metadata || {}) as Record<string, unknown>;
  if (typeof meta.raw_text === "string" && meta.raw_text.trim()) return meta.raw_text.trim();
  if (typeof signal?.raw_text === "string") return signal.raw_text;
  const raw = meta.raw;
  if (raw != null) {
    if (typeof raw === "string" && raw.trim()) return raw.trim();
    try {
      return JSON.stringify(raw);
    } catch {
      return String(raw);
    }
  }
  return "";
}

/** 仅保留当前流水线配置的券商（及可选账号）对应的执行记录。
 * 账号身份以 account_id 为准；label 改名后仍应显示同一资金账号的成交。
 */
export function filterExecutionsForPipeline(
  executions: TimelineExecution[],
  pipelineBroker?: string | null,
  pipelineAccountLabel?: string | null,
  pipelineAccountId?: string | null,
): TimelineExecution[] {
  if (!pipelineBroker) return executions;
  const broker = pipelineBroker.toLowerCase();
  const wantedId = (pipelineAccountId || "").trim();
  const wantedLabel = (pipelineAccountLabel || "").trim();
  return executions.filter((e) => {
    const execBroker = (e.broker || "").trim().toLowerCase();
    // 路由/权益拦截等用占位 broker="-"，仍属本信号源，需在流水线可见
    if (!execBroker || execBroker === "-") return true;
    if (execBroker !== broker) return false;
    if (wantedId) {
      const execId = (e.account_id || "").trim();
      if (execId) return execId === wantedId;
      // 历史行可能缺 account_id：再按 label 兜底
    }
    if (!wantedLabel) return true;
    let label = (e.account_label || "").trim();
    if (!label && e.detail) {
      try {
        const parsed = JSON.parse(e.detail) as { account_label?: string };
        label = String(parsed.account_label || "").trim();
      } catch {
        label = "";
      }
    }
    return !label || label === wantedLabel;
  });
}

function parseStatusFromExecution(exec: TimelineExecution | null): ParseStatus {
  if (!exec) return "pending";
  const s = exec.status.toUpperCase();
  if (s === "SKIPPED") return "skipped";
  if (["FAILED", "REJECTED"].includes(s) && !exec.signal?.symbol) return "failed";
  return exec.signal?.symbol || exec.signal?.action ? "parsed" : "pending";
}

export function formatExpiryCompact(raw: unknown): string {
  if (raw == null || raw === "") return "";
  const text = String(raw).trim();
  const iso = text.match(/^(\d{4})[-/](\d{2})[-/](\d{2})/);
  if (iso) return `${iso[2]}/${iso[3]}`;
  const digits = text.replace(/[-/\s]/g, "");
  if (/^\d{8}$/.test(digits)) return `${digits.slice(4, 6)}/${digits.slice(6, 8)}`;
  if (/^\d{6}$/.test(digits)) return `${digits.slice(2, 4)}/${digits.slice(4, 6)}`;
  return "";
}

/** 从 OCC/紧凑期权代码提取到期日，如 SPXW260729P07370000 → 07/29 */
export function expiryFromOccSymbol(symbol: string): string {
  const compact = symbol.replace(/\s+/g, "").toUpperCase();
  const m = compact.match(/(\d{6})[CP]\d{5,8}$/);
  if (!m) return "";
  const yymmdd = m[1];
  const month = Number(yymmdd.slice(2, 4));
  const day = Number(yymmdd.slice(4, 6));
  if (month < 1 || month > 12 || day < 1 || day > 31) return "";
  return `${yymmdd.slice(2, 4)}/${yymmdd.slice(4, 6)}`;
}

export function legExpiryLabel(leg: Record<string, unknown>): string {
  return (
    formatExpiryCompact(leg.expiry ?? leg.expiry_date) ||
    expiryFromOccSymbol(String(leg.symbol || ""))
  );
}

export function signalExpiryLabel(signal: Record<string, unknown>): string {
  return optionExpiryLabel(signal);
}

function isOptionSignal(signal: Record<string, unknown>): boolean {
  const asset = String(signal.asset_class || "").toUpperCase();
  if (asset.includes("OPTION")) return true;
  if (Array.isArray(signal.legs) && signal.legs.length > 0) return true;
  if (signal.strike != null || signal.right || signal.option_type) return true;
  if (signal.expiry || signal.expiry_date) return true;
  const meta = (signal.metadata || {}) as Record<string, unknown>;
  return Boolean(meta.expiry || meta.expiry_date);
}

function optionExpiryLabel(signal: Record<string, unknown>): string {
  const meta = (signal.metadata || {}) as Record<string, unknown>;
  const direct = [
    signal.expiry,
    signal.expiry_date,
    meta.expiry,
    meta.expiry_date,
  ];
  for (const value of direct) {
    const label = formatExpiryCompact(value);
    if (label) return label;
  }
  const legs = Array.isArray(signal.legs) ? (signal.legs as Record<string, unknown>[]) : [];
  for (const leg of legs) {
    const label = legExpiryLabel(leg);
    if (label) return label;
  }
  return expiryFromOccSymbol(String(signal.symbol || ""));
}

function summarizeParse(signal?: Record<string, unknown>): string {
  if (!signal || !Object.keys(signal).length) return "";
  const action = signal.action ? String(signal.action).toUpperCase() : "";
  const symbol = signal.symbol ? String(signal.symbol) : "";
  const qty = signal.quantity != null ? String(signal.quantity) : "";
  const parts = [action, symbol, qty ? `×${qty}` : ""].filter(Boolean);
  let label = parts.join(" ") || String(signal.signal_id || "").slice(0, 16);
  if (isOptionSignal(signal)) {
    const expiry = optionExpiryLabel(signal);
    if (expiry) label = `${label} · ${expiry}`;
  }
  return label;
}

export function summarizeParseLabel(signal?: Record<string, unknown>): string {
  return summarizeParse(signal) || "—";
}

export function isSuccessfullyParsedExecution(exec: TimelineExecution): boolean {
  const signal = exec.signal || {};
  return Boolean(signal.symbol && signal.action);
}

function messageFromExecution(execution: TimelineExecution): RawMessage | null {
  const raw = rawTextFromSignal(execution.signal);
  const meta = (execution.signal?.metadata || {}) as Record<string, unknown>;
  const signalId = execution.signal_id;
  const messageId = messageIdFromSignalId(signalId);
  const tsFromSignal = execution.signal?.timestamp ? Number(execution.signal.timestamp) : undefined;
  const tsFromCreated = execution.created_at ? parseEtTimestamp(execution.created_at) / 1000 : undefined;
  if (!raw && !execution.created_at) return null;
  return {
    message_id: messageId || signalId,
    channel_id: meta.channel_id ? String(meta.channel_id) : undefined,
    channel_name: meta.channel_name ? String(meta.channel_name) : undefined,
    author: String(meta.author || ""),
    content: raw || summarizeParseLabel(execution.signal),
    ts: tsFromSignal ?? tsFromCreated,
  };
}

/** 合并监听消息与执行记录；消息为内存临时数据，执行记录来自数据库 */
export function buildPipelineFlowRows(
  messages: RawMessage[],
  executions: TimelineExecution[],
  sourceKind: "discord" | "telegram" | "webhook",
  pipelineBroker?: string | null,
  pipelineAccountLabel?: string | null,
  pipelineAccountId?: string | null,
): PipelineFlowRow[] {
  const scopedExecutions = filterExecutionsForPipeline(
    executions,
    pipelineBroker,
    pipelineAccountLabel,
    pipelineAccountId,
  );
  // API 按 created_at 降序；同 signal_id 合并多券商/重试，取主执行记录展示
  const execBySignal = new Map<string, TimelineExecution>();
  const bySignal = new Map<string, TimelineExecution[]>();
  for (const e of scopedExecutions) {
    const list = bySignal.get(e.signal_id) || [];
    list.push(e);
    bySignal.set(e.signal_id, list);
  }
  for (const [signalId, list] of bySignal) {
    const attempts = dedupeAttemptsByAccount(list);
    execBySignal.set(signalId, pickPrimaryAttempt(attempts));
  }
  const msgById = new Map(messages.map((m) => [m.message_id, m]));
  const ids = new Set<string>();

  for (const m of messages) ids.add(signalIdFromMessageId(m.message_id, sourceKind));
  for (const e of scopedExecutions) ids.add(e.signal_id);

  const rows: PipelineFlowRow[] = [];

  for (const signalId of ids) {
    const messageId = messageIdFromSignalId(signalId);
    const message = messageId ? msgById.get(messageId) ?? null : null;
    const execution = execBySignal.get(signalId) ?? null;

    let syntheticMessage = message;
    if (!syntheticMessage && execution) {
      syntheticMessage = messageFromExecution(execution);
    }

    const sortTime = execution?.created_at
      ? parseEtTimestamp(execution.created_at)
      : syntheticMessage?.ts
        ? syntheticMessage.ts * 1000
        : 0;

    rows.push({
      id: signalId,
      signalId,
      sortTime: Number.isFinite(sortTime) ? sortTime : 0,
      message: syntheticMessage,
      execution,
      parseStatus: parseStatusFromExecution(execution),
    });
  }

  return rows.sort((a, b) => b.sortTime - a.sortTime);
}

export function filterPipelineFlowRows(rows: PipelineFlowRow[], filter: FlowFilter): PipelineFlowRow[] {
  if (filter === "all") return rows;
  if (filter === "parsed") {
    return rows.filter((r) => r.parseStatus === "parsed");
  }
  return rows.filter((r) => r.execution != null);
}

export function formatMessageAuthorContent(msg: RawMessage): string {
  const content = (msg.content || "").trim();
  const author = (msg.author || "").trim();
  if (author && content) return `${author}：${content}`;
  if (author) return `${author}：`;
  return content;
}

/** @deprecated use formatMessageAuthorContent */
export function formatMessageBody(msg: RawMessage): string {
  return formatMessageAuthorContent(msg);
}

export function formatMessageChannelTime(msg: RawMessage, fallback?: string): string {
  const channel = (msg.channel_name || msg.channel_id || "").trim() || "—";
  const time = formatMessageTime(msg, fallback);
  return time ? `${channel}  ${time}` : channel;
}

export function formatMessageTime(msg: RawMessage, fallback?: string): string {
  if (msg.ts) return formatEtDateTimeCompact(new Date(msg.ts * 1000).toISOString());
  return fallback ? formatEtDateTimeCompact(fallback) : "";
}

export function rowMessageTime(row: PipelineFlowRow): string {
  if (row.message) {
    const time = formatMessageTime(row.message, row.execution?.created_at);
    if (time) return time;
  }
  if (row.execution?.created_at) return formatEtDateTimeCompact(row.execution.created_at);
  return "—";
}

/** 流水线行时间戳（优先下单/执行时间，其次原始消息）。 */
export function rowOrderTimestampMs(row: PipelineFlowRow): number {
  if (row.execution?.created_at) {
    const ms = parseEtTimestamp(row.execution.created_at);
    if (ms) return ms;
  }
  if (row.message?.ts) return row.message.ts * 1000;
  return 0;
}

export function rowOrderTimeLabel(row: PipelineFlowRow): string {
  if (row.execution?.created_at) {
    const label = formatEtDateTimeCompact(row.execution.created_at);
    if (label) return label;
  }
  if (row.message) {
    const time = formatMessageTime(row.message);
    if (time) return time;
  }
  return "—";
}
