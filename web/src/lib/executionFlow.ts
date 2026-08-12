import type { TimelineExecution } from "../components/SignalTimeline";
import { parseEtTimestamp } from "./datetime";

export const EXECUTION_SYNC_TIMEOUT_MS = 60_000;

export type FlowStageState = "done" | "active" | "failed" | "pending" | "skipped";

export type ExecutionFlowStage = {
  key: string;
  label: string;
  state: FlowStageState;
  hint?: string;
};

const SUCCESS_STATUSES = new Set(["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED"]);
const FAIL_STATUSES = new Set([
  "FAILED",
  "REJECTED",
  "CANCELLED",
  "EXPIRED",
  "DISCARDED_AGENT_OFFLINE",
  "PROTECTIVE_FAILED",
  "SKIPPED",
]);
const DISPATCH_STATUSES = new Set(["ROUTING", "DISPATCHED"]);
const SUBMIT_STATUSES = new Set(["SUBMITTED", "NEW"]);
const WAIT_STATUSES = new Set(["PENDING", "UNKNOWN"]);

export function parseOrderIdFromDetail(detail?: string | null, orderId?: string | null): string | null {
  if (orderId) return orderId;
  if (!detail) return null;
  const match = detail.match(/order=([^;\s]+)/i);
  return match?.[1] ?? null;
}

export function executionAgeMs(execution: TimelineExecution): number | null {
  const ts = parseEtTimestamp(execution.created_at);
  if (!ts) return null;
  return Math.max(0, Date.now() - ts);
}

export function executionSyncRemainingMs(execution: TimelineExecution): number | null {
  const age = executionAgeMs(execution);
  if (age == null) return null;
  return Math.max(0, EXECUTION_SYNC_TIMEOUT_MS - age);
}

function isSyncTrackableExecution(execution: TimelineExecution): boolean {
  const s = execution.status.toUpperCase();
  if (s === "PENDING_CONFIRM" || isTerminalExecutionStatus(s)) return false;
  const orderId = parseOrderIdFromDetail(execution.detail, execution.order_id);
  if (s === "UNKNOWN" && orderId) return true;
  return isInFlightExecutionStatus(s);
}

export function isExecutionSyncTimedOut(execution: TimelineExecution): boolean {
  if (!isSyncTrackableExecution(execution)) return false;
  const age = executionAgeMs(execution);
  return age != null && age >= EXECUTION_SYNC_TIMEOUT_MS;
}

export function shouldStopTrackingExecution(execution: TimelineExecution): boolean {
  return isTerminalExecutionStatus(execution.status) || isExecutionSyncTimedOut(execution);
}

export function executionStatusLabel(
  status: string,
  t: (key: string) => string,
  detail?: string | null,
  orderId?: string | null,
  execution?: TimelineExecution,
): string {
  if (execution && isExecutionSyncTimedOut(execution)) {
    return t("timeline.statusSyncTimeout");
  }
  const s = status.toUpperCase();
  if (s === "UNKNOWN" && parseOrderIdFromDetail(detail, orderId)) {
    return t("timeline.statusSyncing");
  }
  const key = `timeline.status.${s}`;
  const mapped = t(key);
  return mapped !== key ? mapped : status;
}

export function isTrackingExecutionStatus(
  status: string,
  detail?: string | null,
  orderId?: string | null,
  execution?: TimelineExecution,
): boolean {
  if (execution) return !shouldStopTrackingExecution(execution) && status.toUpperCase() !== "PENDING_CONFIRM";
  const s = status.toUpperCase();
  if (isTerminalExecutionStatus(s) || s === "PENDING_CONFIRM") return false;
  if (s === "UNKNOWN" && parseOrderIdFromDetail(detail, orderId)) return true;
  return !isTerminalExecutionStatus(s);
}

export function isTerminalExecutionStatus(status: string): boolean {
  const s = status.toUpperCase();
  return SUCCESS_STATUSES.has(s) || FAIL_STATUSES.has(s);
}

export function isInFlightExecutionStatus(status: string): boolean {
  const s = status.toUpperCase();
  return DISPATCH_STATUSES.has(s) || SUBMIT_STATUSES.has(s) || WAIT_STATUSES.has(s);
}

function stageAt(
  key: string,
  label: string,
  state: FlowStageState,
  hint?: string,
): ExecutionFlowStage {
  return { key, label, state, hint };
}

function isUserRejected(detail?: string | null): boolean {
  return (detail || "").toLowerCase().includes("user rejected");
}

const MANUAL_RETRY_STATUSES = new Set([
  "FAILED",
  "REJECTED",
  "CANCELLED",
  "EXPIRED",
  "DISCARDED_AGENT_OFFLINE",
  "PROTECTIVE_FAILED",
]);

/** 流水线手动「重新尝试」：仅失败类终态，且非用户主动忽略 */
export function canManualRetryExecution(execution?: TimelineExecution | null): boolean {
  if (!execution) return false;
  const status = (execution.status || "").toUpperCase();
  if (!MANUAL_RETRY_STATUSES.has(status)) return false;
  if (status === "REJECTED" && isUserRejected(execution.detail)) return false;
  if (!(execution.signal && Object.keys(execution.signal).length)) return false;
  const broker = (execution.broker || "").trim();
  // 路由占位 broker="-" 也可重试（会按当前流水线重新解析绑定）
  if (!broker) return false;
  return true;
}

/** 解析 detail 中的 fill= / order= / attempt= 字段（后台回报格式）。 */
export function parseFillDetail(detail?: string | null): {
  fillPrice?: number;
  orderId?: string;
  attempt?: number;
} {
  const text = detail?.trim() || "";
  if (!text) return {};
  const fillMatch = text.match(/(?:^|;\s*)fill=(-?\d+(?:\.\d+)?)/i);
  const orderMatch = text.match(/(?:^|;\s*)order=([^;\s]+)/i);
  const attemptMatch = text.match(/(?:^|;\s*)attempt=(\d+)/i);
  const fillPrice = fillMatch ? Number(fillMatch[1]) : undefined;
  const attempt = attemptMatch ? Number(attemptMatch[1]) : undefined;
  return {
    fillPrice: fillPrice != null && Number.isFinite(fillPrice) ? fillPrice : undefined,
    orderId: orderMatch?.[1],
    attempt: attempt != null && Number.isFinite(attempt) ? attempt : undefined,
  };
}

/** LMT→MKT 当前第几次尝试（优先 API attempt 字段）。 */
export function executionAttempt(
  execution: TimelineExecution,
): { attempt: number; maxAttempts: number } | null {
  const parsed = parseFillDetail(execution.detail);
  const fromApi =
    typeof (execution as { attempt?: number | null }).attempt === "number"
      ? (execution as { attempt?: number }).attempt
      : undefined;
  const attempt = fromApi ?? parsed.attempt;
  if (attempt == null || attempt < 1) return null;
  const cfg = execution.signal?.execution_config;
  let maxAttempts = 5;
  if (cfg && typeof cfg === "object" && cfg !== null && "max_retry_attempts" in cfg) {
    const n = Number((cfg as { max_retry_attempts?: unknown }).max_retry_attempts);
    if (Number.isFinite(n) && n >= 1) maxAttempts = n;
  }
  return { attempt, maxAttempts };
}

export function formatElapsedSec(
  sec: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const s = Math.max(0, Math.floor(sec));
  if (s < 60) return t("timeline.elapsedSec", { sec: s });
  const min = Math.floor(s / 60);
  const rem = s % 60;
  return t("timeline.elapsedMinSec", { min, sec: rem });
}

/** 从 `attempt=1; err=...` 这类复合 detail 中取出 err 正文。 */
export function extractExecutionError(detail?: string | null): string | null {
  const text = detail?.trim() || "";
  if (!text) return null;
  const match = text.match(/(?:^|;\s*)err=(.+)$/is);
  const err = match?.[1]?.trim();
  return err || null;
}

function isFillOrderDetail(detail?: string | null): boolean {
  const text = detail?.trim() || "";
  if (!text) return false;
  // 含 err= 时必须展示拒绝/失败原因，不能当纯成交回报吞掉
  if (extractExecutionError(text)) return false;
  // 成交/订单/重试回报串由专用字段展示，不再原样刷到阶段说明
  if (/^(fill|order|attempt)=/i.test(text)) return true;
  if (/;\s*(fill|order|attempt)=/i.test(text)) return true;
  return false;
}

function retryHint(
  detail: string | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | undefined {
  if (isFillOrderDetail(detail)) return undefined;
  const friendly = formatExecutionDetailMessage(detail, t);
  if (friendly) return friendly;
  const text = detail || "";
  if (/retry|重试|attempt/i.test(text)) return text;
  const err = extractExecutionError(text);
  if (err) return err;
  return undefined;
}

/** 将 execution.detail 转为用户可读说明（优先中文 i18n） */
export function formatExecutionDetailMessage(
  detail: string | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  const raw = detail?.trim();
  if (!raw) return null;
  if (raw.startsWith("{") && raw.includes("expires_at")) return null;
  // 成交回报原始串由成交价/订单号字段展示，不再原样刷到页面
  if (isFillOrderDetail(raw)) return null;

  // attempt=1; err=... → 用 err 正文做友好匹配与展示
  const text = extractExecutionError(raw) || raw;
  const lower = text.toLowerCase();
  if (lower === "confirmation expired") return t("timeline.detailConfirmExpired");
  if (lower === "user rejected") return t("timeline.detailUserRejected");
  if (lower.includes("broker gateway offline")) return t("timeline.detailBrokerOffline");
  if (text === "entitlement:kill_switch") return t("timeline.skipKillSwitch");
  if (text.startsWith("entitlement:")) {
    return t("timeline.skipEntitlement", { reason: text.slice("entitlement:".length) });
  }
  if (text.startsWith("routing:")) {
    const code = text.slice("routing:".length).trim();
    const keyByCode: Record<string, string> = {
      broker_binding_mismatch: "timeline.detailRoutingBrokerMismatch",
      ambiguous_broker_account: "timeline.detailRoutingAmbiguousAccount",
      no_broker_binding: "timeline.detailRoutingNoBinding",
    };
    const key = keyByCode[code];
    if (key) return t(key);
    return t("timeline.detailRoutingBlocked", { reason: code });
  }
  if (/alpaca.*单腿|单腿.*alpaca|legs.*alpaca/i.test(text)) {
    return t("timeline.detailAlpacaSingleLeg");
  }
  // 仅长桥专属文案；勿用「不支持多腿组合」泛匹配，否则 futu/usmart 等会被误标成长桥
  if (/长桥.*多腿|多腿.*长桥|longbridge.*多腿|longbridge.*combo|长桥不支持多腿/i.test(text)) {
    return t("timeline.detailLongbridgeNoCombo");
  }
  if (/不支持多腿组合/i.test(text)) {
    return t("timeline.detailBrokerNoCombo");
  }
  // 须先于 OpenD 规则：模拟盘拒单文案也含 place_combo_order，勿误判成版本过低
  if (
    /模拟交易不支持组合|模拟盘.*不支持组合|不支持组合期权|simulate.*(does not|doesn't) support.*combo/i.test(
      text,
    )
  ) {
    return t("timeline.detailFutuSimulateNoCombo");
  }
  // 仅匹配真正的协议/版本问题；勿单独匹配 place_combo_order（模拟盘/权限类也会带这个词）
  if (
    /未知的协议|unknown protocol|opend.*版本过低|opend.*too old|组合下单需\s*≥|需\s*≥\s*10|server_ver.*9\./i.test(
      text,
    )
  ) {
    return t("timeline.detailFutuOpendTooOld");
  }
  if (/合约不正确|bad_request.*合约/i.test(text)) {
    return t("timeline.detailTigerBadContract");
  }
  if (
    /配置账户 .* 被老虎拒绝|拒绝配置账户|模拟账户本身不可用|bound account \(code=1200\)|账户侧拒绝|tiger_id\/账户/i.test(
      text,
    )
  ) {
    return t("timeline.detailTigerAccountForbidden");
  }
  if (
    /组合市价单仅美东盘中|盘外请用 LMT|收入型组合未用负数|盘前盘后不能用市价单|卖出开仓价差未使用负数限价|收入型垂直价差请用限价单|限价为负数/i.test(
      text,
    )
  ) {
    return t("timeline.detailTigerComboSession");
  }
  if (/模拟盘与实盘均使用正式环境|env=PROD|独立 sandbox 需另套/i.test(text)) {
    return t("timeline.detailTigerEnvMismatch");
  }
  if (/code=5\b|rate limit error|\b429\b|老虎\s*API\s*限流/i.test(text)) {
    return t("timeline.detailTigerRateLimit");
  }
  // 已按规范提交仍 1200/请稍后再试 → 账户侧，而非再提示「改成负数限价」
  if (/请稍后再试|try again later|code=1200/i.test(text)) {
    return t("timeline.detailTigerAccountForbidden");
  }
  if (/券商连接失败|老虎连接失败/i.test(text)) {
    return t("timeline.detailBrokerConnectFailed");
  }
  if (/us_index|index asset class|SPX\/SPXW|指数期权/i.test(text)) {
    return t("timeline.detailAlpacaIndexOptions");
  }
  if (lower.includes("kill_switch")) return t("timeline.skipKillSwitch");
  return text;
}

/** 成交价/权利金展示：美元符号 + 固定 2 位小数（避免浮点尾巴如 0.093333…）。 */
export function formatFillPrice(price: number | string): string {
  const n = typeof price === "number" ? price : Number(price);
  if (!Number.isFinite(n)) return String(price);
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

export function formatFillPriceLabel(
  price: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (price < 0) {
    return t("timeline.filledAtCredit", { price: formatFillPrice(Math.abs(price)) });
  }
  return t("timeline.filledAt", { price: formatFillPrice(price) });
}

function legCountFromSignal(signal?: Record<string, unknown>): number {
  const legs = signal?.legs;
  return Array.isArray(legs) ? legs.length : 0;
}

/** 结合 detail 与 signal/broker 推断用户可读说明 */
export function inferExecutionDetailMessage(
  execution: TimelineExecution,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  const friendly = formatExecutionDetailMessage(execution.detail, t);
  if (friendly) return friendly;
  const status = execution.status.toUpperCase();
  if (SUCCESS_STATUSES.has(status)) {
    const parsed = parseFillDetail(execution.detail);
    const price = execution.fill_price ?? parsed.fillPrice;
    if (price != null) {
      return price < 0
        ? t("timeline.detailFilledCredit", { price: formatFillPrice(Math.abs(price)) })
        : t("timeline.detailFilled", { price: formatFillPrice(price) });
    }
    return t("timeline.detailFilledGeneric");
  }
  const broker = (execution.broker || "").toLowerCase();
  const multiLeg = legCountFromSignal(execution.signal) > 1;
  if (
    broker === "alpaca" &&
    multiLeg &&
    FAIL_STATUSES.has(status) &&
    !isFillOrderDetail(execution.detail)
  ) {
    // 仅在仍像多腿限制类失败时提示；具体 err= 已由 format 处理
    const d = (execution.detail || "").toLowerCase();
    if (d.includes("单腿") || d.includes("mleg") || d.includes("legs")) {
      return t("timeline.detailAlpacaSingleLeg");
    }
  }
  // 长桥历史单：多腿曾被误下成单腿后 EXPIRED，无明确 err 时也给出原因
  if (broker === "longbridge" && multiLeg && FAIL_STATUSES.has(status)) {
    const d = (execution.detail || "").toLowerCase();
    if (
      !d ||
      d.includes("attempt=") ||
      d.includes("order=") ||
      d.includes("多腿") ||
      d.includes("组合")
    ) {
      return t("timeline.detailLongbridgeNoCombo");
    }
  }
  if (isExecutionSyncTimedOut(execution)) {
    return t("timeline.detailRoutingNoReport");
  }
  if (status === "EXPIRED") {
    return t("timeline.detailExpiredGeneric");
  }
  return null;
}

/** 根据当前 execution 状态构建执行流程图阶段 */
export function buildExecutionFlowStages(
  execution: TimelineExecution,
  t: (key: string, opts?: Record<string, unknown>) => string,
): ExecutionFlowStage[] {
  const status = execution.status.toUpperCase();
  const detail = execution.detail;
  const orderId = parseOrderIdFromDetail(detail, (execution as { order_id?: string }).order_id);
  const syncTimedOut = isExecutionSyncTimedOut(execution);
  const userRejected = status === "REJECTED" && isUserRejected(detail);
  const success = SUCCESS_STATUSES.has(status);
  const failed = (FAIL_STATUSES.has(status) && !userRejected) || syncTimedOut;
  const pastConfirm = !["PENDING_CONFIRM"].includes(status);
  const inDispatch = DISPATCH_STATUSES.has(status);
  const inSubmit = SUBMIT_STATUSES.has(status);
  const inWait = WAIT_STATUSES.has(status) || (status === "UNKNOWN" && Boolean(orderId));
  const inFlight = isInFlightExecutionStatus(status) || (status === "UNKNOWN" && Boolean(orderId));
  const errHint = retryHint(detail, t);

  const confirmState: FlowStageState = userRejected
    ? "failed"
    : status === "PENDING_CONFIRM"
      ? "active"
      : pastConfirm
        ? "done"
        : "pending";

  const dispatchState: FlowStageState = failed && inDispatch
    ? "failed"
    : inDispatch
      ? "active"
      : pastConfirm && (inSubmit || inWait || success || failed || inFlight)
        ? "done"
        : status === "PENDING_CONFIRM"
          ? "pending"
          : "pending";

  const submitState: FlowStageState = failed && inSubmit
    ? "failed"
    : inSubmit
      ? "active"
      : inWait || success || (failed && !inDispatch && !inSubmit)
        ? "done"
        : "pending";

  const waitState: FlowStageState = syncTimedOut
    ? "failed"
    : failed && (inWait || inSubmit)
      ? "failed"
      : inWait
        ? "active"
        : success
          ? "done"
          : failed && !inDispatch
            ? "failed"
            : "pending";

  const fillState: FlowStageState = success
    ? "done"
    : syncTimedOut || (failed && !userRejected)
      ? "failed"
      : userRejected
        ? "skipped"
        : "pending";

  const parsedFill = parseFillDetail(detail);
  const fillPrice = execution.fill_price ?? parsedFill.fillPrice;
  const fillLabel =
    fillPrice != null ? formatFillPriceLabel(fillPrice, t) : t("timeline.fill");

  return [
    stageAt("parse", t("timeline.parsed"), "done"),
    stageAt(
      "risk",
      t("timeline.risk"),
      status === "SKIPPED" ? "failed" : "done",
    ),
    stageAt(
      "confirm",
      t("timeline.awaitConfirm"),
      confirmState,
      status === "PENDING_CONFIRM" ? t("timeline.hintAwaitConfirm") : undefined,
    ),
    stageAt(
      "dispatch",
      t("timeline.dispatch"),
      dispatchState,
      inDispatch ? t("timeline.hintDispatch") : undefined,
    ),
    stageAt(
      "submit",
      t("timeline.submit"),
      submitState,
      inSubmit ? t("timeline.hintSubmit") : undefined,
    ),
    stageAt(
      "wait",
      t("timeline.waitFill"),
      waitState,
      syncTimedOut
        ? t("timeline.hintSyncTimeout")
        : inWait
          ? status === "UNKNOWN" && orderId
            ? t("timeline.hintSyncing")
            : t("timeline.hintWait")
          : success
            ? undefined
            : errHint,
    ),
    stageAt(
      "fill",
      fillLabel,
      fillState,
      syncTimedOut
        ? t("timeline.hintSyncTimeout")
        : failed && errHint
          ? errHint
          : success && fillPrice != null
            ? fillPrice < 0
              ? t("timeline.hintFilledCredit", {
                  price: formatFillPrice(Math.abs(fillPrice)),
                })
              : t("timeline.hintFilled", { price: formatFillPrice(fillPrice) })
            : undefined,
    ),
  ];
}

export function executionPhaseLabel(
  execution: TimelineExecution,
  t: (key: string) => string,
): string {
  if (isExecutionSyncTimedOut(execution)) return t("timeline.phaseSyncTimeout");
  const status = execution.status.toUpperCase();
  if (status === "PENDING_CONFIRM") return t("timeline.phaseAwaitConfirm");
  if (DISPATCH_STATUSES.has(status)) return t("timeline.phaseDispatch");
  if (SUBMIT_STATUSES.has(status)) return t("timeline.phaseSubmit");
  if (WAIT_STATUSES.has(status)) return t("timeline.phaseWait");
  if (status === "UNKNOWN") return t("timeline.phaseSyncing");
  if (SUCCESS_STATUSES.has(status)) return t("timeline.phaseSuccess");
  if (status === "REJECTED" && isUserRejected(execution.detail)) return t("timeline.phaseIgnored");
  if (FAIL_STATUSES.has(status)) return t("timeline.phaseFailed");
  return execution.status;
}
