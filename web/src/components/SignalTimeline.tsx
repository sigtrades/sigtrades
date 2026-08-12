import { useTranslation } from "react-i18next";
import { formatEtDateTime } from "../lib/datetime";
import {
  buildExecutionFlowStages,
  canManualRetryExecution,
  executionAttempt,
  executionPhaseLabel,
  executionStatusLabel,
  formatFillPrice,
  inferExecutionDetailMessage,
  isExecutionSyncTimedOut,
  isTerminalExecutionStatus,
  parseFillDetail,
  parseOrderIdFromDetail,
  type FlowStageState,
} from "../lib/executionFlow";

export type TimelineExecution = {
  signal_id: string;
  status: string;
  broker: string;
  account_label?: string | null;
  account_id?: string | null;
  fill_price?: number | null;
  filled_qty?: number | null;
  order_id?: string | null;
  attempt?: number | null;
  detail?: string | null;
  created_at?: string;
  signal?: Record<string, unknown>;
};

type Props = {
  execution: TimelineExecution;
  onConfirm?: (signalId: string, accountLabel?: string | null) => void;
  onReject?: (signalId: string, accountLabel?: string | null) => void;
  onRetry?: (signalId: string, accountLabel?: string | null) => void;
  confirmBusy?: boolean;
  /** 正在轮询执行进度 */
  tracking?: boolean;
  /** 弹窗模式展示更多字段 */
  showMeta?: boolean;
  /** inline=列表卡片；modal=执行详情弹窗（纵向步骤条） */
  variant?: "inline" | "modal";
  /** 嵌入信号分组卡片时去掉外层边框与标题 */
  embedded?: boolean;
};

function dotClass(state: FlowStageState, pulsing: boolean) {
  if (state === "done") return "bg-profit";
  if (state === "failed") return "bg-loss";
  if (state === "active") {
    return pulsing
      ? "bg-brand-500 ring-4 ring-brand-100 animate-pulse"
      : "bg-brand-500 ring-4 ring-brand-100";
  }
  if (state === "skipped") return "bg-slate-300";
  return "bg-slate-200";
}

function badgeClass(status: string): string {
  const s = status.toUpperCase();
  if (["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED"].includes(s)) return "badge-success";
  if (["FAILED", "REJECTED", "DISCARDED_AGENT_OFFLINE", "PROTECTIVE_FAILED"].includes(s)) {
    return "badge-danger";
  }
  if (s === "PENDING_CONFIRM") return "bg-brand-50 text-brand-700 ring-1 ring-brand-200";
  if (["ROUTING", "DISPATCHED", "SUBMITTED", "PENDING", "NEW", "UNKNOWN"].includes(s)) {
    return "badge-neutral";
  }
  return "badge-neutral";
}

export default function SignalTimeline({
  execution,
  onConfirm,
  onReject,
  onRetry,
  confirmBusy,
  tracking = false,
  showMeta = false,
  variant = "inline",
  embedded = false,
}: Props) {
  const { t } = useTranslation();
  const signal = execution.signal || {};
  const symbol = String(signal.symbol || execution.signal_id.slice(0, 12));
  const action = String(signal.action || "");
  const isPendingConfirm = execution.status.toUpperCase() === "PENDING_CONFIRM";
  const canRetry = Boolean(onRetry) && canManualRetryExecution(execution);
  const stages = buildExecutionFlowStages(execution, t);
  const phase = executionPhaseLabel(execution, t);
  const syncTimedOut = isExecutionSyncTimedOut(execution);
  const terminal = isTerminalExecutionStatus(execution.status) || syncTimedOut;
  const statusLabel = executionStatusLabel(
    execution.status,
    t,
    execution.detail,
    execution.order_id,
    execution,
  );
  const parsedFill = parseFillDetail(execution.detail);
  const orderId =
    parseOrderIdFromDetail(execution.detail, execution.order_id) || parsedFill.orderId || null;
  const fillPrice = execution.fill_price ?? parsedFill.fillPrice ?? null;
  const attemptInfo = executionAttempt(execution);
  const isModal = variant === "modal";

  const metaGrid = showMeta ? (
    <dl className={`grid gap-3 text-sm sm:grid-cols-2 ${isModal ? "mt-0" : "mt-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3 text-xs"}`}>
      <div className={isModal ? "rounded-xl border border-slate-100 bg-slate-50 px-4 py-3" : ""}>
        <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("timeline.metaSignalId")}</dt>
        <dd className="mt-1 font-mono text-sm text-slate-800 break-all">{execution.signal_id}</dd>
      </div>
      {execution.account_label ? (
        <div className={isModal ? "rounded-xl border border-slate-100 bg-slate-50 px-4 py-3" : ""}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("timeline.metaAccount")}</dt>
          <dd className="mt-1 font-semibold text-slate-900">{execution.account_label}</dd>
        </div>
      ) : null}
      {attemptInfo ? (
        <div className={isModal ? "rounded-xl border border-slate-100 bg-slate-50 px-4 py-3" : ""}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("timeline.metaAttempt")}</dt>
          <dd className="mt-1 text-lg font-bold text-slate-900">
            {t("timeline.attemptOf", { n: attemptInfo.attempt, max: attemptInfo.maxAttempts })}
          </dd>
        </div>
      ) : null}
      {orderId ? (
        <div className={isModal ? "rounded-xl border border-slate-100 bg-slate-50 px-4 py-3" : ""}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("timeline.metaOrderId")}</dt>
          <dd className="mt-1 font-mono text-sm text-slate-800 break-all">{orderId}</dd>
        </div>
      ) : null}
      {fillPrice != null ? (
        <div className={isModal ? "rounded-xl border border-slate-100 bg-slate-50 px-4 py-3" : ""}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {fillPrice < 0 ? t("timeline.metaFillCredit") : t("timeline.metaFillPrice")}
          </dt>
          <dd className="mt-1 flex flex-wrap items-baseline gap-2">
            <span className="text-lg font-bold tabular-nums text-emerald-600">
              {formatFillPrice(fillPrice < 0 ? Math.abs(fillPrice) : fillPrice)}
            </span>
            {fillPrice < 0 ? (
              <span className="inline-flex items-center rounded-md bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200/80">
                {t("timeline.metaFillCreditSide")}
              </span>
            ) : null}
          </dd>
        </div>
      ) : null}
      {execution.filled_qty != null ? (
        <div className={isModal ? "rounded-xl border border-slate-100 bg-slate-50 px-4 py-3" : ""}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("timeline.metaFillQty")}</dt>
          <dd className="mt-1 font-semibold text-slate-900">{execution.filled_qty}</dd>
        </div>
      ) : null}
    </dl>
  ) : null;

  const stageList = isModal ? (
    <div className="mt-6">
      <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-500">{t("timeline.flowStages")}</p>
      <ol className="space-y-0">
        {stages.map((stage, i) => (
          <li key={stage.key} className="relative flex gap-4 pb-6 last:pb-0">
            {i < stages.length - 1 ? (
              <span
                className={`absolute left-[11px] top-6 bottom-0 w-px ${
                  stage.state === "done" ? "bg-emerald-200" : "bg-slate-200"
                }`}
                aria-hidden
              />
            ) : null}
            <span
              className={`relative z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ring-4 ${
                stage.state === "done"
                  ? "bg-emerald-500 ring-emerald-100"
                  : stage.state === "failed"
                    ? "bg-red-500 ring-red-100"
                    : stage.state === "active"
                      ? "bg-brand-500 ring-brand-100"
                      : stage.state === "skipped"
                        ? "bg-slate-300 ring-slate-100"
                        : "bg-slate-200 ring-slate-50"
              } ${tracking && stage.state === "active" ? "animate-pulse" : ""}`}
            >
              {stage.state === "done" ? (
                <svg viewBox="0 0 12 12" className="h-3 w-3 text-white" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M2 6l3 3 5-5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : stage.state === "failed" ? (
                <svg viewBox="0 0 12 12" className="h-3 w-3 text-white" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M3 3l6 6M9 3L3 9" strokeLinecap="round" />
                </svg>
              ) : (
                <span className="h-2 w-2 rounded-full bg-white/90" />
              )}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <p
                className={`text-sm font-medium ${
                  stage.state === "active"
                    ? "text-brand-700"
                    : stage.state === "failed"
                      ? "text-red-700"
                      : stage.state === "done"
                        ? "text-slate-900"
                        : "text-slate-400"
                }`}
              >
                {stage.label}
              </p>
              {stage.hint ? <p className="mt-0.5 text-xs text-slate-500">{stage.hint}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  ) : (
    <div className="mt-4 space-y-2">
      <div className="flex flex-wrap items-center gap-x-1 gap-y-1">
        {stages.map((stage, i) => (
          <div key={stage.key} className="flex items-center gap-1">
            <span
              className={`h-2.5 w-2.5 shrink-0 rounded-full ${dotClass(
                stage.state,
                tracking && stage.state === "active",
              )}`}
            />
            <span
              className={`whitespace-nowrap text-xs ${
                stage.state === "active"
                  ? "font-medium text-brand-700"
                  : stage.state === "failed"
                    ? "text-loss"
                    : stage.state === "done"
                      ? "text-slate-700"
                      : "text-slate-400"
              }`}
            >
              {stage.label}
            </span>
            {i < stages.length - 1 ? (
              <span className="px-0.5 text-slate-300 leading-none" aria-hidden>
                →
              </span>
            ) : null}
          </div>
        ))}
      </div>
      {stages.some((s) => s.hint) ? (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {stages
            .filter((s) => s.hint)
            .map((stage) => (
              <p key={`${stage.key}-hint`} className="text-[10px] leading-snug text-slate-500">
                <span className="font-medium text-slate-600">{stage.label}：</span>
                {stage.hint}
              </p>
            ))}
        </div>
      ) : null}
    </div>
  );

  return (
    <div className={embedded ? "mt-3" : isModal ? "" : "rounded-xl border border-slate-200 bg-white p-4"}>
      {!isModal && !embedded ? (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-sm font-medium text-slate-900">
              {action ? `${action} ` : ""}{symbol}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              {formatEtDateTime(execution.created_at)} · {execution.broker}
            </p>
          </div>
          <span className={`badge text-[10px] ${syncTimedOut ? "badge-danger" : badgeClass(execution.status)}`}>
            {statusLabel}
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span>{formatEtDateTime(execution.created_at)}</span>
            <span className="text-slate-300">·</span>
            <span className="font-medium text-slate-800">{execution.broker}</span>
          </div>
          <span className={`badge ${syncTimedOut ? "badge-danger" : badgeClass(execution.status)}`}>{statusLabel}</span>
        </div>
      )}

      {metaGrid}

      {!terminal && (tracking || !isPendingConfirm) ? (
        <p className={`rounded-xl border border-brand-100 bg-brand-50/60 px-4 py-3 text-sm text-brand-800 ${isModal ? "mt-4" : "mt-3"}`}>
          {tracking ? t("timeline.tracking") : phase}
          {orderId && execution.status.toUpperCase() === "UNKNOWN" ? (
            <span className="mt-1 block text-brand-700">{t("timeline.hintSyncing")}</span>
          ) : null}
        </p>
      ) : null}

      {syncTimedOut ? (
        <p className={`rounded-xl border border-loss/20 bg-loss-soft px-4 py-3 text-sm text-loss ${isModal ? "mt-4" : "mt-3"}`}>
          {t("timeline.hintSyncTimeout")}
        </p>
      ) : null}

      {stageList}

      {isPendingConfirm && onConfirm && onReject ? (
        <div className={`flex flex-wrap gap-2 ${isModal ? "mt-6" : "mt-4"}`}>
          <button
            type="button"
            className="btn-primary text-sm"
            disabled={confirmBusy}
            onClick={() => onConfirm(execution.signal_id, execution.account_label)}
          >
            {confirmBusy ? t("execPipeline.saving") : t("timeline.confirmTrade")}
          </button>
          <button
            type="button"
            className="btn-secondary text-sm"
            disabled={confirmBusy}
            onClick={() => onReject(execution.signal_id, execution.account_label)}
          >
            {t("timeline.rejectTrade")}
          </button>
        </div>
      ) : null}

      {canRetry && onRetry ? (
        <div className={`flex flex-wrap gap-2 ${isModal ? "mt-6" : "mt-4"}`}>
          <button
            type="button"
            className="btn-primary text-sm"
            disabled={confirmBusy}
            onClick={() => onRetry(execution.signal_id, execution.account_label)}
          >
            {confirmBusy ? t("pipeline.flow.retrying") : t("pipeline.flow.retryExecute")}
          </button>
        </div>
      ) : null}

      {(() => {
        if (embedded) return null;
        let friendlyDetail = inferExecutionDetailMessage(execution, t);
        if (!friendlyDetail && execution.status.toUpperCase() === "EXPIRED") {
          friendlyDetail = t("timeline.detailExpiredGeneric");
        }
        if (!friendlyDetail) return null;
        const failedLike = ["FAILED", "REJECTED", "EXPIRED", "CANCELLED"].includes(execution.status.toUpperCase());
        return (
          <p
            className={`text-sm leading-relaxed break-words ${
              isModal
                ? `mt-4 rounded-lg px-3 py-2.5 ${
                    failedLike
                      ? "border border-amber-200 bg-amber-50 text-amber-950"
                      : "border border-slate-200 bg-slate-50 text-slate-700"
                  }`
                : `mt-3 ${failedLike ? "text-amber-800" : "text-slate-600"}`
            }`}
          >
            {friendlyDetail}
          </p>
        );
      })()}
    </div>
  );
}
