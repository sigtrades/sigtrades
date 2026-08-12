import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  executionAgeMs,
  executionSyncRemainingMs,
  isExecutionSyncTimedOut,
  isTerminalExecutionStatus,
  shouldStopTrackingExecution,
} from "../lib/executionFlow";
import { useExecutionPolling } from "../lib/useExecutionPolling";
import SignalTimeline, { type TimelineExecution } from "./SignalTimeline";

type Props = {
  execution: TimelineExecution;
  onClose: () => void;
  onPoll: () => void | Promise<void>;
  onConfirm?: (signalId: string, accountLabel?: string | null) => void;
  onReject?: (signalId: string) => void;
  onRetry?: (signalId: string, accountLabel?: string | null) => void;
  confirmBusy?: boolean;
  pollIntervalMs?: number;
  autoCloseMs?: number;
  /** 仅自动跟单弹窗在终态后倒计时关闭；手动查看详情时为 false */
  autoCloseOnComplete?: boolean;
};

function elapsedLabel(seconds: number, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return t("timeline.elapsedMinSec", { min: m, sec: s });
  return t("timeline.elapsedSec", { sec: s });
}

export default function ExecutionDetailModal({
  execution,
  onClose,
  onPoll,
  onConfirm,
  onReject,
  onRetry,
  confirmBusy,
  pollIntervalMs = 1000,
  autoCloseMs = 4000,
  autoCloseOnComplete = false,
}: Props) {
  const { t } = useTranslation();
  const openedAtRef = useRef(Date.now());
  const [elapsedSec, setElapsedSec] = useState(0);
  const pollSec = Math.max(1, Math.round(pollIntervalMs / 1000));
  const [pollTick, setPollTick] = useState(pollSec);
  const [closeCountdown, setCloseCountdown] = useState<number | null>(null);
  const terminal = isTerminalExecutionStatus(execution.status);
  const syncTimedOut = isExecutionSyncTimedOut(execution);
  const stopTracking = shouldStopTrackingExecution(execution);
  /** 手动点开详情：不计时、不展示刷新倒计时；仅自动跟单弹窗在进行中计时 */
  const liveTiming = autoCloseOnComplete && !stopTracking;
  const signal = execution.signal || {};
  const symbol = String(signal.symbol || execution.signal_id.slice(0, 16));
  const action = String(signal.action || "").toUpperCase();

  useEffect(() => {
    openedAtRef.current = Date.now();
    setElapsedSec(0);
    setCloseCountdown(null);
  }, [execution.signal_id]);

  useEffect(() => {
    if (!liveTiming) {
      setElapsedSec(0);
      return;
    }
    const update = () => {
      const ageMs = executionAgeMs(execution);
      setElapsedSec(Math.max(0, Math.floor((ageMs ?? Date.now() - openedAtRef.current) / 1000)));
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [liveTiming, execution.signal_id, execution.created_at, execution.status]);

  useEffect(() => {
    if (!liveTiming) {
      setPollTick(pollSec);
      return;
    }
    setPollTick(pollSec);
    const timer = window.setInterval(() => {
      setPollTick((v) => (v <= 1 ? pollSec : v - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [liveTiming, pollSec, execution.status, execution.detail, execution.created_at]);

  useEffect(() => {
    if (!autoCloseOnComplete || !terminal) {
      setCloseCountdown(null);
      return;
    }
    const closeSec = Math.ceil(autoCloseMs / 1000);
    setCloseCountdown(closeSec);
    const countdown = window.setInterval(() => {
      setCloseCountdown((v) => (v == null || v <= 1 ? 0 : v - 1));
    }, 1000);
    const timer = window.setTimeout(onClose, autoCloseMs);
    return () => {
      window.clearTimeout(timer);
      window.clearInterval(countdown);
    };
  }, [autoCloseOnComplete, terminal, autoCloseMs, onClose, execution.signal_id]);

  useExecutionPolling(liveTiming, execution, async () => {
    await onPoll();
    if (liveTiming) setPollTick(pollSec);
  }, pollSec * 1000);

  const syncRemainingSec = (() => {
    const ms = executionSyncRemainingMs(execution);
    return ms == null ? null : Math.ceil(ms / 1000);
  })();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-900/50 p-0 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label={t("common.close")} onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[94vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 px-6 py-5 text-white">
          <div className="absolute -right-8 -top-8 h-32 w-32 rounded-full bg-brand-400/10 blur-2xl" aria-hidden />
          <div className="relative flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wider text-brand-300">
                {t("pipeline.flow.execDetailTitle")}
              </p>
              <h3 className="mt-1 truncate text-2xl font-bold tracking-tight">
                {action ? (
                  <>
                    <span className="text-brand-300">{action}</span> {symbol}
                  </>
                ) : (
                  symbol
                )}
              </h3>
              <p className="mt-2 text-sm text-slate-400">{t("timeline.modalSubtitle")}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-xl border border-white/10 bg-white/5 p-2 text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
              aria-label={t("common.close")}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              </svg>
            </button>
          </div>
          <div className="relative mt-4 flex flex-wrap gap-2">
            {liveTiming ? (
              <>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-slate-200 ring-1 ring-white/10">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-400" />
                  {t("timeline.elapsed")}: {elapsedLabel(elapsedSec, t)}
                </span>
                <span className="rounded-full bg-brand-500/20 px-3 py-1 text-xs font-medium text-brand-200 ring-1 ring-brand-400/30">
                  {t("timeline.nextRefresh", { sec: Math.max(1, Math.round(pollTick)) })}
                </span>
                {syncRemainingSec != null ? (
                  <span className="rounded-full bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-200 ring-1 ring-amber-400/30">
                    {t("timeline.syncTimeoutIn", { sec: syncRemainingSec })}
                  </span>
                ) : null}
              </>
            ) : syncTimedOut ? (
              <span className="rounded-full bg-red-500/20 px-3 py-1 text-xs font-medium text-red-200 ring-1 ring-red-400/30">
                {t("timeline.statusSyncTimeout")}
              </span>
            ) : autoCloseOnComplete && closeCountdown != null && closeCountdown > 0 ? (
              <span className="rounded-full bg-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-200 ring-1 ring-emerald-400/30">
                {t("timeline.autoCloseHint", { sec: closeCountdown })}
              </span>
            ) : null}
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-5">
          <SignalTimeline
            execution={execution}
            tracking={!stopTracking}
            confirmBusy={confirmBusy}
            onConfirm={onConfirm}
            onReject={onReject}
            onRetry={onRetry}
            showMeta
            variant="modal"
          />
        </div>
      </div>
    </div>
  );
}
