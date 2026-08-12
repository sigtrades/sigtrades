import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TimelineExecution } from "./SignalTimeline";
import {
  executionAgeMs,
  executionAttempt,
  executionStatusLabel,
  formatElapsedSec,
  formatFillPrice,
  inferExecutionDetailMessage,
  isInFlightExecutionStatus,
  isTerminalExecutionStatus,
  parseFillDetail,
  shouldStopTrackingExecution,
} from "../lib/executionFlow";

const FAIL_CHIP_STATUSES = new Set([
  "FAILED",
  "REJECTED",
  "EXPIRED",
  "DISCARDED_AGENT_OFFLINE",
  "PROTECTIVE_FAILED",
  "CANCELLED",
  "SKIPPED",
]);

const SUCCESS_CHIP_STATUSES = new Set(["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED"]);

export type ExecutionDetailLine = {
  text: string;
  tone: "success" | "fail";
};

/** 卡片第二行：成交摘要（绿）或失败原因（红）。 */
export function executionDetailLine(
  execution: TimelineExecution,
  t: (key: string, opts?: Record<string, unknown>) => string,
): ExecutionDetailLine | null {
  const statusUpper = execution.status.toUpperCase();
  const isSuccess = SUCCESS_CHIP_STATUSES.has(statusUpper);
  const isFail =
    FAIL_CHIP_STATUSES.has(statusUpper) ||
    (!isSuccess && shouldStopTrackingExecution(execution) && statusUpper !== "PENDING_CONFIRM");
  if (!isSuccess && !isFail) return null;
  const text = inferExecutionDetailMessage(execution, t);
  if (!text) return null;
  return { text, tone: isSuccess ? "success" : "fail" };
}

/** @deprecated 仅失败；新代码请用 executionDetailLine */
export function executionFailReason(
  execution: TimelineExecution,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  const line = executionDetailLine(execution, t);
  return line?.tone === "fail" ? line.text : null;
}

function isLiveElapsed(execution: TimelineExecution): boolean {
  // 仅执行中（派发/提交/等待）开计时；终态/待确认/同步超时一律关掉
  if (isTerminalExecutionStatus(execution.status) || shouldStopTrackingExecution(execution)) {
    return false;
  }
  if (execution.status.toUpperCase() === "PENDING_CONFIRM") return false;
  return isInFlightExecutionStatus(execution.status);
}

/** 流水线卡片内联：耗时 · 重试 · 状态 · 成交价（原因由外层第二行展示） */
export default function ExecutionInlineMeta({
  execution,
  compact = false,
  showReason = false,
}: {
  execution: TimelineExecution;
  compact?: boolean;
  /** 默认 false：原因放外层第二行，避免与徽章挤在同一行 */
  showReason?: boolean;
}) {
  const { t } = useTranslation();
  const live = isLiveElapsed(execution);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!live) {
      setElapsedSec(0);
      return;
    }
    const update = () => {
      const age = executionAgeMs(execution);
      setElapsedSec(age == null ? 0 : Math.floor(age / 1000));
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [live, execution.signal_id, execution.created_at, execution.status, execution.detail]);

  const attemptInfo = executionAttempt(execution);
  const parsed = parseFillDetail(execution.detail);
  const fillPrice = execution.fill_price ?? parsed.fillPrice ?? null;
  const statusLabel = executionStatusLabel(
    execution.status,
    t,
    execution.detail,
    execution.order_id,
    execution,
  );
  const statusUpper = execution.status.toUpperCase();
  const detailLine = showReason ? executionDetailLine(execution, t) : null;

  const chip = compact
    ? "rounded px-1.5 py-0.5 text-[10px] font-medium leading-none"
    : "rounded-md px-2 py-0.5 text-[11px] font-medium";

  return (
    <div className={`flex min-w-0 flex-col ${compact ? "gap-1" : "gap-1.5"}`}>
      <div className={`flex flex-wrap items-center ${compact ? "gap-1" : "gap-1.5"}`}>
        {live ? (
          <span className={`${chip} bg-slate-100 text-slate-600 tabular-nums`}>
            {t("pipeline.flow.execElapsed")} {formatElapsedSec(elapsedSec, t)}
          </span>
        ) : null}
        {attemptInfo ? (
          <span className={`${chip} bg-amber-50 text-amber-800 ring-1 ring-amber-100`}>
            {t("pipeline.flow.execAttemptOf", {
              n: attemptInfo.attempt,
              max: attemptInfo.maxAttempts,
            })}
          </span>
        ) : null}
        <span
          className={`${chip} ${
            ["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED"].includes(statusUpper)
              ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100"
              : FAIL_CHIP_STATUSES.has(statusUpper)
                ? "bg-red-50 text-red-700 ring-1 ring-red-100"
                : "bg-slate-100 text-slate-700"
          }`}
        >
          {statusLabel}
        </span>
        {fillPrice != null ? (
          <span className={`${chip} tabular-nums text-emerald-700 bg-emerald-50 ring-1 ring-emerald-100`}>
            {fillPrice < 0
              ? `${t("timeline.metaFillCredit")} ${formatFillPrice(Math.abs(fillPrice))} · ${t("timeline.metaFillCreditSide")}`
              : `${t("timeline.metaFillPrice")} ${formatFillPrice(fillPrice)}`}
          </span>
        ) : null}
      </div>
      {detailLine ? (
        <p
          className={`min-w-0 ${
            detailLine.tone === "success" ? "text-emerald-700" : "text-red-600/90"
          } ${compact ? "text-[10px] leading-snug line-clamp-2" : "text-[11px] leading-snug line-clamp-3"}`}
          title={detailLine.text}
        >
          {detailLine.text}
        </p>
      ) : null}
    </div>
  );
}
