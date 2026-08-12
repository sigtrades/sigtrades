import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { normalizeExecutionsResponse } from "../lib/executions";
import {
  buildPipelineFlowRows,
  filterPipelineFlowRows,
  formatMessageAuthorContent,
  formatMessageChannelTime,
  rowMessageTime,
  rowOrderTimeLabel,
  rowOrderTimestampMs,
  summarizeParseLabel,
  type FlowFilter,
  type PipelineFlowRow,
  type RawMessage,
} from "../lib/pipelineFlow";
import { formatEtDateTimeCompact, getRelativeAge } from "../lib/datetime";
import {
  canManualRetryExecution,
  isTerminalExecutionStatus,
  shouldStopTrackingExecution,
} from "../lib/executionFlow";
import { markExecutionModalOpen } from "../lib/executionModalGate";
import ExecutionDetailModal from "./ExecutionDetailModal";
import ExecutionBrokerLine from "./ExecutionBrokerLine";
import ExecutionInlineMeta, { executionDetailLine } from "./ExecutionInlineMeta";
import ParseSignalDetail from "./ParseSignalDetail";
import SignalTimeline, { type TimelineExecution } from "./SignalTimeline";

function formatFlowRelativeAge(
  ms: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
  nowMs = Date.now(),
): string {
  const age = getRelativeAge(ms, nowMs);
  if (!age) return "";
  if (age.unit === "just_now") return t("pipeline.flow.relativeJustNow");
  if (age.unit === "minutes") return t("pipeline.flow.relativeMinutes", { n: age.n });
  if (age.unit === "hours") return t("pipeline.flow.relativeHours", { n: age.n });
  return t("pipeline.flow.relativeDays", { n: age.n });
}

type Props = {
  sourceId: string;
  sourceKind: "discord" | "telegram" | "webhook";
  /** 当前流水线绑定的券商，仅展示该券商的执行记录 */
  pipelineBroker?: string | null;
  pipelineAccountLabel?: string | null;
  /** 资金账号 ID（优先于 label，避免改名后流水线列表漏单） */
  pipelineAccountId?: string | null;
  onAction?: () => void;
  /** Max rows shown when expanded; older rows hidden until list expand */
  maxRows?: number;
  /** Tighter layout for embedding in pipeline list cards */
  compact?: boolean;
  /** Collapse signal list by default (show latest signal only) */
  defaultCollapsed?: boolean;
};

function FlowArrow({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center text-slate-300 ${className}`} aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
        <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ParseBadge({ status }: { status: PipelineFlowRow["parseStatus"] }) {
  const { t } = useTranslation();
  const map = {
    parsed: "badge-success",
    pending: "badge bg-slate-200 text-slate-700",
    failed: "badge-danger",
    skipped: "badge bg-slate-100 text-slate-600",
  } as const;
  const label = {
    parsed: t("pipeline.flow.parseOk"),
    pending: t("pipeline.flow.parsePending"),
    failed: t("pipeline.flow.parseFailed"),
    skipped: t("pipeline.flow.parseSkipped"),
  }[status];
  return <span className={`badge text-[10px] ${map[status]}`}>{label}</span>;
}

function ExecBadge({ status }: { status: string }) {
  const s = status.toUpperCase();
  const cls =
    ["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED"].includes(s)
      ? "badge-success"
      : ["FAILED", "REJECTED", "DISCARDED_AGENT_OFFLINE", "PROTECTIVE_FAILED"].includes(s)
        ? "badge-danger"
        : s === "PENDING_CONFIRM"
          ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
          : ["ROUTING", "DISPATCHED"].includes(s)
            ? "badge-neutral"
            : "badge-neutral";
  return <span className={`badge text-[10px] ${cls}`}>{status}</span>;
}

function DetailModal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-slate-200 bg-white p-4 shadow-xl sm:max-h-[85vh] sm:rounded-2xl sm:p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="min-w-0 pr-2 font-semibold text-slate-900">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="close"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function CompactFlowRow({
  row,
  actingSignalId,
  onParseDetail,
  onExecDetail,
  onConfirm,
  onReject,
  onRetry,
}: {
  row: PipelineFlowRow;
  actingSignalId: string | null;
  onParseDetail: () => void;
  onExecDetail: () => void;
  onConfirm: () => void;
  onReject: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const parseLabel = summarizeParseLabel(row.execution?.signal);
  const time = rowOrderTimeLabel(row);
  const timeMs = rowOrderTimestampMs(row);
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const relative = timeMs ? formatFlowRelativeAge(timeMs, t, nowMs) : "";
  const detailLine = row.execution ? executionDetailLine(row.execution, t) : null;
  const canRetry = canManualRetryExecution(row.execution);
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-slate-200 bg-slate-50/50 px-2.5 py-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span
          className="shrink-0 text-[11px] tabular-nums text-slate-400"
          title={relative ? `${time} · ${relative}` : time}
        >
          {time}
          {relative ? <span className="ml-1.5 text-slate-400">{relative}</span> : null}
        </span>
        <span className="min-w-0 font-mono text-xs font-semibold text-slate-900">{parseLabel}</span>
        <ParseBadge status={row.parseStatus} />
        {row.execution ? (
          <ExecutionBrokerLine
            broker={row.execution.broker}
            status={row.execution.status}
            compact
            showStatus={false}
            showFill={false}
          />
        ) : (
          <span className="text-[10px] text-slate-500">{t("pipeline.flow.execPending")}</span>
        )}
        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1.5">
          {row.execution ? <ExecutionInlineMeta execution={row.execution} compact /> : null}
          {row.execution?.signal ? (
            <button type="button" className="btn-secondary px-2 py-1 text-[10px]" onClick={onParseDetail}>
              {t("pipeline.flow.parseDetailShort")}
            </button>
          ) : null}
          {row.execution ? (
            <button type="button" className="btn-secondary px-2 py-1 text-[10px]" onClick={onExecDetail}>
              {t("pipeline.flow.execDetailShort")}
            </button>
          ) : null}
          {canRetry ? (
            <button
              type="button"
              className="btn-primary px-2 py-1 text-[10px]"
              disabled={actingSignalId === row.signalId}
              onClick={onRetry}
            >
              {actingSignalId === row.signalId ? t("pipeline.flow.retrying") : t("pipeline.flow.retryExecute")}
            </button>
          ) : null}
          {row.execution?.status.toUpperCase() === "PENDING_CONFIRM" ? (
            <>
              <button
                type="button"
                className="btn-primary px-2 py-1 text-[10px]"
                disabled={actingSignalId === row.signalId}
                onClick={onConfirm}
              >
                {actingSignalId === row.signalId ? t("execPipeline.saving") : t("pipeline.flow.confirmExecute")}
              </button>
              <button
                type="button"
                className="btn-secondary px-2 py-1 text-[10px]"
                disabled={actingSignalId === row.signalId}
                onClick={onReject}
              >
                {t("pipeline.flow.rejectExecute")}
              </button>
            </>
          ) : null}
        </div>
      </div>
      {detailLine ? (
        <p
          className={`text-[10px] leading-snug line-clamp-2 ${
            detailLine.tone === "success" ? "text-emerald-700" : "text-red-600/90"
          }`}
          title={detailLine.text}
        >
          {detailLine.text}
        </p>
      ) : null}
    </div>
  );
}

export default function PipelineFlowBoard({
  sourceId,
  sourceKind,
  pipelineBroker,
  pipelineAccountLabel,
  pipelineAccountId,
  onAction,
  maxRows,
  compact = false,
  defaultCollapsed = true,
}: Props) {
  const { t } = useTranslation();
  const [executions, setExecutions] = useState<TimelineExecution[]>([]);
  const [messages, setMessages] = useState<RawMessage[]>([]);
  const [flowFilter, setFlowFilter] = useState<FlowFilter>("all");
  const [actingSignalId, setActingSignalId] = useState<string | null>(null);
  const [parseDetail, setParseDetail] = useState<PipelineFlowRow | null>(null);
  const [execDetail, setExecDetail] = useState<TimelineExecution | null>(null);
  const [boardExpanded, setBoardExpanded] = useState(!defaultCollapsed);
  const [listExpanded, setListExpanded] = useState(false);
  const modalOpenRef = useRef(false);

  useEffect(() => {
    modalOpenRef.current = execDetail != null;
  }, [execDetail]);

  useEffect(
    () => () => {
      if (modalOpenRef.current) markExecutionModalOpen(false);
    },
    [],
  );

  /** 仅手动点「执行详情」打开；执行中/刷新不再自动弹窗 */
  const openExecDetail = useCallback((execution: TimelineExecution) => {
    setExecDetail(execution);
    markExecutionModalOpen(true);
  }, []);

  const filterTags: { value: FlowFilter; label: string }[] = useMemo(
    () => [
      { value: "all", label: t("pipeline.flow.filterAll") },
      { value: "parsed", label: t("pipeline.flow.filterParsed") },
      { value: "executed", label: t("pipeline.flow.filterExecuted") },
    ],
    [t],
  );

  const load = useCallback(async () => {
    const execPromise = api.get("/config/executions", { params: { source_id: sourceId, limit: 50 } });
    const msgPromise =
      sourceKind === "discord"
        ? api.get(`/config/discord-user/preview-messages/${sourceId}`).catch(() => ({ data: { messages: [] } }))
        : Promise.resolve({ data: { messages: [] } });

    const [execRes, msgRes] = await Promise.all([execPromise, msgPromise]);
    setExecutions(normalizeExecutionsResponse(execRes.data).items);
    setMessages((msgRes.data?.messages || []) as RawMessage[]);
  }, [sourceId, sourceKind]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  const allRows = useMemo(
    () =>
      filterPipelineFlowRows(
        buildPipelineFlowRows(
          messages,
          executions,
          sourceKind,
          pipelineBroker,
          pipelineAccountLabel,
          pipelineAccountId,
        ),
        flowFilter,
      ),
    [messages, executions, sourceKind, flowFilter, pipelineBroker, pipelineAccountLabel, pipelineAccountId],
  );

  const limit = maxRows && !listExpanded ? maxRows : undefined;
  const rows = limit ? allRows.slice(0, limit) : allRows;
  const hiddenCount = limit ? Math.max(0, allRows.length - limit) : 0;
  const latestRow = allRows[0] ?? null;

  const latestExecution = useCallback((list: TimelineExecution[], signalId: string) => {
    return list.find((e) => e.signal_id === signalId) ?? null;
  }, []);

  const syncExecution = useCallback(
    async (signalId: string): Promise<TimelineExecution | null> => {
      const res = await api.get("/config/executions", { params: { source_id: sourceId, limit: 50 } });
      const list = normalizeExecutionsResponse(res.data).items;
      setExecutions(list);
      const found = latestExecution(list, signalId);
      if (found) {
        setExecDetail((current) => (current?.signal_id === signalId ? found : current));
      }
      return found;
    },
    [sourceId, latestExecution],
  );

  const closeExecDetail = useCallback(() => {
    setExecDetail(null);
    markExecutionModalOpen(false);
  }, []);

  const confirm = async (signalId: string, execution?: TimelineExecution | null) => {
    setActingSignalId(signalId);
    const accountLabel =
      execution?.account_label ||
      (execution?.detail
        ? (() => {
            try {
              const parsed = JSON.parse(execution.detail) as { account_label?: string };
              return parsed.account_label || undefined;
            } catch {
              return undefined;
            }
          })()
        : undefined);
    try {
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/confirm`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      await syncExecution(signalId);
    } finally {
      setActingSignalId(null);
    }
  };

  const reject = async (signalId: string, execution?: TimelineExecution | null) => {
    setActingSignalId(signalId);
    try {
      const accountLabel =
        execution?.account_label ||
        (execution?.detail
          ? (() => {
              try {
                const parsed = JSON.parse(execution.detail) as { account_label?: string };
                return parsed.account_label || undefined;
              } catch {
                return undefined;
              }
            })()
          : undefined);
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/reject`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      await syncExecution(signalId);
      onAction?.();
    } finally {
      setActingSignalId(null);
    }
  };

  const retry = async (signalId: string, execution?: TimelineExecution | null) => {
    setActingSignalId(signalId);
    const accountLabel =
      execution?.account_label ||
      (execution?.detail
        ? (() => {
            try {
              const parsed = JSON.parse(execution.detail) as { account_label?: string };
              return parsed.account_label || undefined;
            } catch {
              return undefined;
            }
          })()
        : undefined);
    try {
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/retry`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      await syncExecution(signalId);
      onAction?.();
    } finally {
      setActingSignalId(null);
    }
  };

  const pollExecDetail = useCallback(async () => {
    if (!execDetail) return;
    if (shouldStopTrackingExecution(execDetail)) return;
    const latest = await syncExecution(execDetail.signal_id);
    if (latest && isTerminalExecutionStatus(latest.status)) {
      onAction?.();
    }
  }, [execDetail, syncExecution, onAction]);

  useEffect(() => {
    setExecDetail((current) => {
      if (!current) return current;
      return executions.find((e) => e.signal_id === current.signal_id) ?? current;
    });
  }, [executions]);

  const emptyMessage =
    flowFilter === "all" ? t("pipeline.noSignalsYet") : t("pipeline.flow.filterEmpty");

  return (
    <div className={`space-y-1.5 ${compact ? "text-sm" : "space-y-3"}`}>
      {boardExpanded ? (
        <div className="space-y-1">
          <h3 className="text-xs font-semibold text-slate-800">{t("pipeline.flow.title")}</h3>
          <p className="text-[11px] leading-snug text-slate-500">{t("pipeline.flow.subtitle")}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        {boardExpanded ? (
          <div className="flex flex-wrap gap-1" role="tablist" aria-label={t("pipeline.flow.filterLabel")}>
            {filterTags.map((tag) => {
              const active = flowFilter === tag.value;
              return (
                <button
                  key={tag.value}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                    active
                      ? "bg-brand-500 text-white"
                      : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-brand-200 hover:text-brand-700"
                  }`}
                  onClick={() => {
                    setFlowFilter(tag.value);
                    setListExpanded(false);
                  }}
                >
                  {tag.label}
                </button>
              );
            })}
          </div>
        ) : allRows.length > 0 ? (
          <span className="text-[11px] text-slate-500">
            {t("pipeline.flow.collapsedHint", { count: allRows.length })}
          </span>
        ) : (
          <span className="text-[11px] text-slate-400">{t("pipeline.noSignalsYet")}</span>
        )}
        <div className="flex items-center gap-1.5">
          {boardExpanded && allRows.length > 0 ? (
            <span className="text-[11px] text-slate-500">{t("pipeline.flow.rowCount", { count: allRows.length })}</span>
          ) : null}
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:border-slate-300 hover:text-slate-900"
            onClick={() => {
              setBoardExpanded((v) => !v);
              setListExpanded(false);
            }}
          >
            <ChevronIcon expanded={boardExpanded} />
            {boardExpanded ? t("pipeline.flow.collapseBoard") : t("pipeline.flow.expandBoard")}
          </button>
        </div>
      </div>

      {!boardExpanded ? (
        latestRow ? (
          <CompactFlowRow
            row={latestRow}
            actingSignalId={actingSignalId}
            onParseDetail={() => latestRow.execution?.signal && setParseDetail(latestRow)}
            onExecDetail={() => latestRow.execution && openExecDetail(latestRow.execution)}
            onConfirm={() => void confirm(latestRow.signalId, latestRow.execution)}
            onReject={() => void reject(latestRow.signalId, latestRow.execution)}
            onRetry={() => void retry(latestRow.signalId, latestRow.execution)}
          />
        ) : (
          <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-xs text-slate-500">
            {emptyMessage}
          </p>
        )
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-5 text-center text-xs text-slate-500">
          {emptyMessage}
        </p>
      ) : (
        <>
      {/* Column headers */}
      <div className="hidden items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-slate-600 lg:grid lg:grid-cols-[1fr_28px_1fr_28px_1fr]">
        <span>{t("pipeline.flow.colMessages")}</span>
        <span />
        <span>{t("pipeline.flow.colParse")}</span>
        <span />
        <span>{t("pipeline.flow.colExecute")}</span>
      </div>

      <div className={compact ? "max-h-[28rem] space-y-1.5 overflow-y-auto pr-1" : "space-y-2"}>
      {rows.map((row) => (
        <div
          key={row.id}
          className={`rounded-xl border border-slate-200 bg-white shadow-sm lg:grid lg:grid-cols-[1fr_28px_1fr_28px_1fr] lg:items-stretch lg:gap-0 ${
            compact ? "p-1.5" : "p-2"
          }`}
        >
          {/* Col 1: Message */}
          <div className="min-w-0 rounded-lg border border-slate-100 bg-white px-2 py-1.5">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-600 lg:hidden">
              {t("pipeline.flow.colMessages")}
            </p>
            {row.message ? (
              <div className={compact ? "mt-0.5" : "mt-1"}>
                <p className="text-[10px] tabular-nums text-slate-500">
                  {row.message.channel_name || row.message.channel_id
                    ? formatMessageChannelTime(row.message, row.execution?.created_at)
                    : rowMessageTime(row)}
                </p>
                <p className="mt-0.5 line-clamp-3 whitespace-pre-wrap text-xs leading-snug text-slate-800">
                  {formatMessageAuthorContent(row.message)}
                </p>
              </div>
            ) : (
              <div>
                {row.execution?.created_at ? (
                  <p className="text-[10px] tabular-nums text-slate-500">{rowMessageTime(row)}</p>
                ) : null}
                <p className="text-xs text-slate-600">{t("pipeline.flow.noMessage")}</p>
              </div>
            )}
          </div>

          <FlowArrow className="hidden lg:flex" />

          {/* Col 2: Parse */}
          <button
            type="button"
            onClick={() => row.execution?.signal && setParseDetail(row)}
            disabled={!row.execution?.signal}
            className="mt-2 min-w-0 rounded-lg border border-slate-100 bg-white px-2 py-1.5 text-left transition-colors hover:border-brand-200 hover:bg-brand-50/40 disabled:cursor-default disabled:opacity-60 lg:mt-0"
          >
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-600 lg:hidden">
              {t("pipeline.flow.colParse")}
            </p>
            <div className="flex items-center justify-between gap-2">
              <ParseBadge status={row.parseStatus} />
              {row.execution?.signal ? (
                <span className="text-[10px] text-brand-600">{t("pipeline.flow.viewDetail")}</span>
              ) : null}
            </div>
            <p className="mt-0.5 font-mono text-xs font-medium text-slate-800">
              {summarizeParseLabel(row.execution?.signal)}
            </p>
            {row.execution?.signal?.parse_mode ? (
              <p className="text-[10px] text-slate-600">
                {String(row.execution.signal.parse_mode)}
              </p>
            ) : null}
          </button>

          <FlowArrow className="hidden lg:flex" />

          {/* Col 3: Execute */}
          <div
            className={`mt-2 min-w-0 rounded-lg border border-slate-100 bg-white px-2 py-1.5 lg:mt-0 ${
              row.execution?.status.toUpperCase() === "PENDING_CONFIRM"
                ? "border-brand-200 bg-brand-50/30"
                : ""
            }`}
          >
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-600 lg:hidden">
              {t("pipeline.flow.colExecute")}
            </p>
            {row.execution ? (
              <>
                <div className="flex items-center justify-between gap-2">
                  <ExecutionBrokerLine
                    broker={row.execution.broker}
                    status={row.execution.status}
                    showStatus={false}
                    showFill={false}
                  />
                  <button
                    type="button"
                    className="shrink-0 text-[10px] text-brand-600 hover:underline"
                    onClick={() => {
                      if (row.execution) openExecDetail(row.execution);
                    }}
                  >
                    {t("pipeline.flow.viewDetail")}
                  </button>
                </div>
                <div className="mt-1.5">
                  <ExecutionInlineMeta execution={row.execution} compact />
                </div>
                {(() => {
                  const line = executionDetailLine(row.execution, t);
                  return line ? (
                    <p
                      className={`mt-1 text-[10px] leading-snug line-clamp-2 ${
                        line.tone === "success" ? "text-emerald-700" : "text-red-600/90"
                      }`}
                      title={line.text}
                    >
                      {line.text}
                    </p>
                  ) : null;
                })()}
                <p className="mt-1 text-[10px] tabular-nums text-slate-600">
                  {formatEtDateTimeCompact(row.execution.created_at)}
                </p>
                {canManualRetryExecution(row.execution) ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      className="btn-primary px-2.5 py-1 text-[10px]"
                      disabled={actingSignalId === row.signalId}
                      onClick={() => void retry(row.signalId, row.execution)}
                    >
                      {actingSignalId === row.signalId
                        ? t("pipeline.flow.retrying")
                        : t("pipeline.flow.retryExecute")}
                    </button>
                  </div>
                ) : null}
                {row.execution.status.toUpperCase() === "PENDING_CONFIRM" ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      className="btn-primary px-2.5 py-1 text-[10px]"
                      disabled={actingSignalId === row.signalId}
                      onClick={() => void confirm(row.signalId, row.execution)}
                    >
                      {actingSignalId === row.signalId
                        ? t("execPipeline.saving")
                        : t("pipeline.flow.confirmExecute")}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary px-2.5 py-1 text-[10px]"
                      disabled={actingSignalId === row.signalId}
                      onClick={() => void reject(row.signalId, row.execution)}
                    >
                      {t("pipeline.flow.rejectExecute")}
                    </button>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-xs font-medium text-slate-700">{t("pipeline.flow.execPending")}</p>
            )}
          </div>

          {/* Mobile flow arrows */}
          <div className="flex justify-center py-1 text-slate-300 lg:hidden" aria-hidden>↓</div>
        </div>
      ))}
      </div>

      {hiddenCount > 0 ? (
        <button
          type="button"
          className="w-full rounded-lg border border-dashed border-slate-200 py-2 text-xs text-brand-600 hover:border-brand-200 hover:bg-brand-50/50"
          onClick={() => setListExpanded(true)}
        >
          {t("pipeline.flow.showMore", { count: hiddenCount })}
        </button>
      ) : listExpanded && maxRows && allRows.length > maxRows ? (
        <button
          type="button"
          className="w-full rounded-lg border border-dashed border-slate-200 py-2 text-xs text-slate-500 hover:bg-slate-50"
          onClick={() => setListExpanded(false)}
        >
          {t("pipeline.flow.showLess")}
        </button>
      ) : null}
        </>
      )}

      {parseDetail?.execution?.signal ? (
        <DetailModal title={t("pipeline.flow.parseDetailTitle")} onClose={() => setParseDetail(null)}>
          <ParseSignalDetail
            signalId={parseDetail.signalId}
            signal={parseDetail.execution.signal as Record<string, unknown>}
          />
        </DetailModal>
      ) : null}

      {execDetail ? (
        <ExecutionDetailModal
          execution={execDetail}
          onClose={closeExecDetail}
          onPoll={pollExecDetail}
          autoCloseOnComplete={false}
          confirmBusy={actingSignalId === execDetail.signal_id}
          onConfirm={
            execDetail.status.toUpperCase() === "PENDING_CONFIRM"
              ? (id) => void confirm(id, execDetail)
              : undefined
          }
          onReject={
            execDetail.status.toUpperCase() === "PENDING_CONFIRM"
              ? (id) => void reject(id, execDetail)
              : undefined
          }
          onRetry={
            canManualRetryExecution(execDetail)
              ? (id) => void retry(id, execDetail)
              : undefined
          }
        />
      ) : null}
    </div>
  );
}
