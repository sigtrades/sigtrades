import type { TimelineExecution } from "../components/SignalTimeline";
import { parseEtTimestamp } from "./datetime";

export type SignalExecutionGroup = {
  signalId: string;
  sourceId?: string;
  sortTime: number;
  signal: Record<string, unknown>;
  createdAt?: string;
  /** 同一信号下按券商账号去重后的执行记录（最新一条） */
  attempts: TimelineExecution[];
};

function attemptKey(e: TimelineExecution): string {
  return `${(e.broker || "").toLowerCase()}:${e.account_label || e.account_id || ""}`;
}

/** 同一 broker+账号只保留最新一条，避免重复路由产生多条顶层记录。 */
export function dedupeAttemptsByAccount(items: TimelineExecution[]): TimelineExecution[] {
  const byKey = new Map<string, TimelineExecution>();
  for (const e of items) {
    const key = attemptKey(e);
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, e);
      continue;
    }
    const ts = parseEtTimestamp(e.created_at);
    const prevTs = parseEtTimestamp(prev.created_at);
    if (ts >= prevTs) byKey.set(key, e);
  }
  return [...byKey.values()].sort((a, b) => parseEtTimestamp(b.created_at) - parseEtTimestamp(a.created_at));
}

export function pickPrimaryAttempt(attempts: TimelineExecution[]): TimelineExecution {
  const pending = attempts.find((a) => a.status.toUpperCase() === "PENDING_CONFIRM");
  if (pending) return pending;
  const inFlight = attempts.find((a) => !["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED", "FAILED", "REJECTED", "EXPIRED", "CANCELLED", "SKIPPED"].includes(a.status.toUpperCase()));
  if (inFlight) return inFlight;
  return attempts[0];
}

export function groupExecutionsBySignal(
  items: Array<TimelineExecution & { source_id?: string }>,
): SignalExecutionGroup[] {
  const raw = new Map<string, TimelineExecution[]>();
  for (const e of items) {
    const list = raw.get(e.signal_id) || [];
    list.push(e);
    raw.set(e.signal_id, list);
  }

  const groups: SignalExecutionGroup[] = [];
  for (const [signalId, list] of raw) {
    const attempts = dedupeAttemptsByAccount(list);
    const primary = attempts[0];
    groups.push({
      signalId,
      sourceId: (list[0] as { source_id?: string }).source_id,
      sortTime: parseEtTimestamp(primary?.created_at),
      signal: primary?.signal || {},
      createdAt: primary?.created_at,
      attempts,
    });
  }

  return groups.sort((a, b) => b.sortTime - a.sortTime);
}
