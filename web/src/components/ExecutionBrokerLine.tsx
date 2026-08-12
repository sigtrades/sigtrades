import { useTranslation } from "react-i18next";
import { BrokerLogo } from "./BrokerLogos";
import { brokerDisplayName, normalizeBrokerKey, type BrokerKey } from "../lib/brokerCredentials";
import { executionStatusLabel, formatFillPrice } from "../lib/executionFlow";

type Props = {
  broker: string;
  status: string;
  fillPrice?: number | null;
  detail?: string | null;
  orderId?: string | null;
  compact?: boolean;
  /** 状态徽章；流水线内联摘要已展示时可关 */
  showStatus?: boolean;
  showFill?: boolean;
};

function ExecStatusBadge({
  status,
  detail,
  orderId,
}: {
  status: string;
  detail?: string | null;
  orderId?: string | null;
}) {
  const { t } = useTranslation();
  const label = executionStatusLabel(status, t, detail, orderId);
  const s = status.toUpperCase();
  const cls =
    ["FILLED", "PARTIALLY_FILLED", "CLOUD_EXECUTED"].includes(s)
      ? "badge-success"
      : ["FAILED", "REJECTED", "DISCARDED_AGENT_OFFLINE", "PROTECTIVE_FAILED"].includes(s)
        ? "badge-danger"
        : s === "PENDING_CONFIRM"
          ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
          : ["ROUTING", "DISPATCHED", "SUBMITTED", "NEW"].includes(s)
            ? "badge-neutral"
            : "badge-neutral";
  return <span className={`badge text-[10px] ${cls}`}>{label}</span>;
}

function brokerLogoClass(key: BrokerKey, compact?: boolean): string {
  if (compact) {
    return key === "longbridge" ? "h-3.5 w-3.5 object-contain" : "h-3.5 w-3.5 rounded object-contain";
  }
  return key === "longbridge" ? "h-4 w-4 object-contain" : "h-4 w-4 rounded object-contain";
}

export default function ExecutionBrokerLine({
  broker,
  status,
  fillPrice,
  detail,
  orderId,
  compact,
  showStatus = true,
  showFill = true,
}: Props) {
  const { t } = useTranslation();
  const key = normalizeBrokerKey(broker);
  const name = brokerDisplayName(broker, t);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {key ? (
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-200 bg-white">
          <BrokerLogo broker={key} className={brokerLogoClass(key, compact)} />
        </span>
      ) : null}
      <span className={`font-medium text-slate-800 ${compact ? "text-[11px]" : "text-xs"}`}>{name}</span>
      {showStatus ? <ExecStatusBadge status={status} detail={detail} orderId={orderId} /> : null}
      {showFill && fillPrice != null ? (
        <span className="text-[10px] font-medium tabular-nums text-emerald-600">
          {fillPrice < 0
            ? `@${formatFillPrice(Math.abs(fillPrice))} · ${t("timeline.metaFillCreditSide")}`
            : `@${formatFillPrice(fillPrice)}`}
        </span>
      ) : null}
    </div>
  );
}
