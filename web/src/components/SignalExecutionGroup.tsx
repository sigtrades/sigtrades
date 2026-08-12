import { useTranslation } from "react-i18next";
import { formatEtDateTime } from "../lib/datetime";
import {
  executionStatusLabel,
  formatExecutionDetailMessage,
  isExecutionSyncTimedOut,
  isTerminalExecutionStatus,
} from "../lib/executionFlow";
import { pickPrimaryAttempt, type SignalExecutionGroup } from "../lib/executionGroups";
import ExecutionBrokerLine from "./ExecutionBrokerLine";
import SignalTimeline, { type TimelineExecution } from "./SignalTimeline";

type Props = {
  group: SignalExecutionGroup;
  confirmBusy?: boolean;
  onConfirm?: (signalId: string, accountLabel?: string | null) => void;
  onReject?: (signalId: string, accountLabel?: string | null) => void;
};

function aggregateStatusLabel(group: SignalExecutionGroup, t: (key: string) => string): string {
  const attempts = group.attempts;
  if (attempts.some((a) => a.status.toUpperCase() === "PENDING_CONFIRM")) {
    return t("timeline.status.PENDING_CONFIRM");
  }
  if (attempts.some((a) => isExecutionSyncTimedOut(a))) {
    return t("timeline.statusSyncTimeout");
  }
  const primary = pickPrimaryAttempt(attempts);
  return executionStatusLabel(primary.status, t, primary.detail, primary.order_id, primary);
}

export default function SignalExecutionGroup({ group, confirmBusy, onConfirm, onReject }: Props) {
  const { t } = useTranslation();
  const primary = pickPrimaryAttempt(group.attempts);
  const signal = group.signal || {};
  const symbol = String(signal.symbol || group.signalId.slice(0, 16));
  const action = String(signal.action || "");
  const multi = group.attempts.length > 1;

  const friendlyDetail = (() => {
    for (const a of group.attempts) {
      const msg = formatExecutionDetailMessage(a.detail, t);
      if (msg) return msg;
    }
    if (group.attempts.some((a) => a.status.toUpperCase() === "EXPIRED")) {
      return t("timeline.detailExpiredGeneric");
    }
    return null;
  })();

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-sm font-medium text-slate-900">
            {action ? `${action} ` : ""}
            {symbol}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">
            {formatEtDateTime(group.createdAt)}
            {multi ? ` · ${t("executionGroup.attemptCount", { count: group.attempts.length })}` : null}
          </p>
        </div>
        <span className="badge text-[10px] badge-neutral">{aggregateStatusLabel(group, t)}</span>
      </div>

      <SignalTimeline
        execution={primary}
        embedded={multi}
        confirmBusy={confirmBusy}
        tracking={
          !isTerminalExecutionStatus(primary.status) &&
          primary.status.toUpperCase() !== "PENDING_CONFIRM" &&
          !multi
        }
        onConfirm={
          !multi && primary.status.toUpperCase() === "PENDING_CONFIRM" && onConfirm
            ? (id, label) => onConfirm(id, label)
            : undefined
        }
        onReject={
          !multi && primary.status.toUpperCase() === "PENDING_CONFIRM" && onReject
            ? (id, label) => onReject(id, label)
            : undefined
        }
      />

      {multi ? (
        <div className="mt-3 space-y-2 rounded-lg border border-slate-100 bg-slate-50/80 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {t("executionGroup.subOrders")}
          </p>
          <ul className="space-y-2">
            {group.attempts.map((attempt) => (
              <SubOrderRow
                key={`${attempt.broker}-${attempt.account_label || attempt.account_id || attempt.created_at}`}
                attempt={attempt}
                confirmBusy={confirmBusy}
                onConfirm={onConfirm}
                onReject={onReject}
              />
            ))}
          </ul>
        </div>
      ) : null}

      {multi && friendlyDetail ? (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-relaxed text-amber-950">
          {friendlyDetail}
        </p>
      ) : null}
    </div>
  );
}

function SubOrderRow({
  attempt,
  confirmBusy,
  onConfirm,
  onReject,
}: {
  attempt: TimelineExecution;
  confirmBusy?: boolean;
  onConfirm?: (signalId: string, accountLabel?: string | null) => void;
  onReject?: (signalId: string, accountLabel?: string | null) => void;
}) {
  const { t } = useTranslation();
  const pending = attempt.status.toUpperCase() === "PENDING_CONFIRM";

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2">
      <ExecutionBrokerLine
        broker={attempt.broker}
        status={attempt.status}
        fillPrice={attempt.fill_price}
        compact
      />
      <div className="flex shrink-0 flex-wrap gap-1.5">
        {pending && onConfirm && onReject ? (
          <>
            <button
              type="button"
              className="btn-primary px-2 py-1 text-[10px]"
              disabled={confirmBusy}
              onClick={() => onConfirm(attempt.signal_id, attempt.account_label)}
            >
              {confirmBusy ? t("execPipeline.saving") : t("timeline.confirmTrade")}
            </button>
            <button
              type="button"
              className="btn-secondary px-2 py-1 text-[10px]"
              disabled={confirmBusy}
              onClick={() => onReject(attempt.signal_id, attempt.account_label)}
            >
              {t("timeline.rejectTrade")}
            </button>
          </>
        ) : null}
      </div>
    </li>
  );
}
