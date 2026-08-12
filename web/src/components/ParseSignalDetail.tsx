import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { formatFillPrice } from "../lib/executionFlow";
import { legExpiryLabel, signalExpiryLabel } from "../lib/pipelineFlow";

type Leg = Record<string, unknown>;
type CashSide = "credit" | "debit";

function asLegs(signal: Record<string, unknown>): Leg[] {
  return Array.isArray(signal.legs) ? (signal.legs as Leg[]) : [];
}

function isStockSignal(signal: Record<string, unknown>, legs: Leg[]): boolean {
  const asset = String(signal.asset_class || "").toUpperCase();
  if (asset === "STOCK" || asset === "EQUITY") return true;
  if (legs.length > 0) return false;
  const optHint = String(signal.option_type || signal.right || signal.strike || "").trim();
  return !optHint;
}

function formatPriceValue(value: unknown): string | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  return formatFillPrice(n);
}

function normalizeAction(raw: unknown): string {
  return String(raw || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
}

/** SELL* → credit（收入）；BUY* → debit（支出） */
function actionCashSide(action: string): CashSide | null {
  if (!action) return null;
  if (action === "SELL" || action.startsWith("SELL_") || action === "STO" || action === "STC") {
    return "credit";
  }
  if (action === "BUY" || action.startsWith("BUY_") || action === "BTO" || action === "BTC") {
    return "debit";
  }
  return null;
}

function isSellAction(action: string): boolean {
  return actionCashSide(action) === "credit";
}

function isBuyAction(action: string): boolean {
  return actionCashSide(action) === "debit";
}

function legStrike(leg: Leg): number | null {
  const n = typeof leg.strike === "number" ? leg.strike : Number(leg.strike);
  return Number.isFinite(n) ? n : null;
}

/** 多腿净方向：卖多→收入；垂直价差按行权价判断信用/借方 */
function netCashSide(legs: Leg[], rootAction?: string, limitPrice?: unknown): CashSide | null {
  let sell = 0;
  let buy = 0;
  for (const leg of legs) {
    const side = actionCashSide(normalizeAction(leg.action));
    if (side === "credit") sell += 1;
    if (side === "debit") buy += 1;
  }
  if (sell > buy) return "credit";
  if (buy > sell) return "debit";

  if (legs.length >= 2 && sell > 0 && sell === buy) {
    const sellLegs = legs.filter((l) => actionCashSide(normalizeAction(l.action)) === "credit");
    const buyLegs = legs.filter((l) => actionCashSide(normalizeAction(l.action)) === "debit");
    const sellStrike = sellLegs.map(legStrike).find((x) => x != null);
    const buyStrike = buyLegs.map(legStrike).find((x) => x != null);
    const opt = String(sellLegs[0]?.option_type || sellLegs[0]?.right || buyLegs[0]?.option_type || "")
      .toUpperCase();
    if (sellStrike != null && buyStrike != null) {
      if (opt.includes("PUT") || opt === "P") {
        return sellStrike > buyStrike ? "credit" : "debit";
      }
      if (opt.includes("CALL") || opt === "C") {
        return sellStrike < buyStrike ? "credit" : "debit";
      }
    }
  }

  const n = typeof limitPrice === "number" ? limitPrice : Number(limitPrice);
  if (Number.isFinite(n) && n < 0) return "credit";
  return actionCashSide(normalizeAction(rootAction));
}

function Field({
  label,
  value,
  valueClassName,
  badge,
}: {
  label: string;
  value: string;
  valueClassName?: string;
  badge?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 flex flex-wrap items-center gap-1.5">
        <span className={`text-sm font-medium break-all ${valueClassName || "text-slate-900"}`}>{value}</span>
        {badge}
      </dd>
    </div>
  );
}

function SideBadge({ side, t }: { side: CashSide; t: (k: string) => string }) {
  if (side === "credit") {
    return (
      <span className="inline-flex items-center rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200/80">
        {t("pipeline.flow.parseTagCredit")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-md bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 ring-1 ring-inset ring-red-200/80">
      {t("pipeline.flow.parseTagDebit")}
    </span>
  );
}

function ActionChip({ action }: { action: string }) {
  if (isSellAction(action)) {
    return (
      <span className="inline-flex items-center rounded-md bg-red-50 px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-red-600 ring-1 ring-inset ring-red-200/80">
        {action}
      </span>
    );
  }
  if (isBuyAction(action)) {
    return (
      <span className="inline-flex items-center rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-emerald-700 ring-1 ring-inset ring-emerald-200/80">
        {action}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-slate-700">
      {action || "—"}
    </span>
  );
}

function LegRow({
  leg,
  index,
  t,
}: {
  leg: Leg;
  index: number;
  t: (k: string, opts?: Record<string, unknown>) => string;
}) {
  const action = normalizeAction(leg.action);
  const opt = String(leg.option_type || leg.right || "").toUpperCase();
  const strike = leg.strike != null ? String(leg.strike) : "";
  const qty = leg.quantity != null ? String(leg.quantity) : "";
  const symbol = String(leg.symbol || "").trim();
  const expiry = legExpiryLabel(leg);
  const legPx = formatPriceValue(leg.limit_price);
  const cash = actionCashSide(action);

  return (
    <li className="rounded-lg border border-slate-100 bg-white px-3 py-2.5 text-xs text-slate-800 shadow-sm shadow-slate-100/80">
      <div className="flex flex-wrap items-center gap-2">
        <span className="w-4 shrink-0 text-slate-400 tabular-nums">{index}.</span>
        <ActionChip action={action} />
        {cash ? <SideBadge side={cash} t={t} /> : null}
        {opt ? (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-700">{opt}</span>
        ) : null}
        {expiry ? (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-700">
            {expiry}
          </span>
        ) : null}
        {strike ? <span className="font-semibold tabular-nums text-slate-900">{strike}</span> : null}
        {qty ? <span className="text-slate-500">×{qty}</span> : null}
        {legPx ? (
          <span className="ml-auto tabular-nums text-slate-600">
            {t("pipeline.flow.parseFieldLimitPrice")} {legPx}
          </span>
        ) : null}
      </div>
      {symbol ? <p className="mt-1.5 truncate pl-6 font-mono text-[10px] text-slate-500">{symbol}</p> : null}
    </li>
  );
}

/** 解析详情：摘要（腿/股票/价格）+ 默认收起的 JSON */
export default function ParseSignalDetail({
  signalId,
  signal,
}: {
  signalId: string;
  signal: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const [jsonOpen, setJsonOpen] = useState(false);
  const legs = asLegs(signal);
  const stock = isStockSignal(signal, legs);
  const showLegs = legs.length > 0;
  const action = signal.action != null ? String(signal.action) : "";
  const actionNorm = normalizeAction(action);
  const symbol = signal.symbol != null ? String(signal.symbol) : "";
  const qty = signal.quantity != null ? String(signal.quantity) : "";
  const orderType = signal.order_type != null ? String(signal.order_type) : "";
  const limitPrice = formatPriceValue(signal.limit_price);
  const assetClass = signal.asset_class != null ? String(signal.asset_class) : "";
  const expiry = !stock ? signalExpiryLabel(signal) : "";
  const premiumSide = netCashSide(legs, action, signal.limit_price);
  const rootSide = actionCashSide(actionNorm);

  return (
    <div className="space-y-4">
      <p className="font-mono text-xs text-slate-500">{signalId}</p>

      <dl className="grid gap-2 sm:grid-cols-2">
        {action ? (
          <Field
            label={t("pipeline.flow.parseFieldAction")}
            value={action}
            valueClassName={
              isSellAction(actionNorm)
                ? "text-red-600"
                : isBuyAction(actionNorm)
                  ? "text-emerald-700"
                  : undefined
            }
            badge={rootSide ? <SideBadge side={rootSide} t={t} /> : null}
          />
        ) : null}
        {symbol ? (
          <Field
            label={stock ? t("pipeline.flow.parseFieldStock") : t("pipeline.flow.parseFieldSymbol")}
            value={symbol}
          />
        ) : null}
        {qty ? <Field label={t("pipeline.flow.parseFieldQty")} value={qty} /> : null}
        {expiry ? <Field label={t("pipeline.flow.parseFieldExpiry")} value={expiry} /> : null}
        {orderType ? <Field label={t("pipeline.flow.parseFieldOrderType")} value={orderType} /> : null}
        {limitPrice ? (
          <Field
            label={t("pipeline.flow.parseFieldLimitPrice")}
            value={limitPrice}
            valueClassName={
              premiumSide === "credit"
                ? "tabular-nums text-emerald-700"
                : premiumSide === "debit"
                  ? "tabular-nums text-red-600"
                  : "tabular-nums"
            }
            badge={premiumSide ? <SideBadge side={premiumSide} t={t} /> : null}
          />
        ) : null}
        {assetClass ? <Field label={t("pipeline.flow.parseFieldAsset")} value={assetClass} /> : null}
      </dl>

      {showLegs ? (
        <div>
          <p className="mb-2 text-xs font-semibold text-slate-700">{t("pipeline.flow.parseLegsTitle")}</p>
          <ul className="space-y-1.5">
            {legs.map((leg, i) => (
              <LegRow key={`${String(leg.symbol || "")}-${i}`} leg={leg} index={i + 1} t={t} />
            ))}
          </ul>
        </div>
      ) : null}

      <div className="border-t border-slate-100 pt-3">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-left transition hover:border-slate-300 hover:bg-slate-100"
          onClick={() => setJsonOpen((v) => !v)}
          aria-expanded={jsonOpen}
        >
          <span className="text-xs font-semibold text-slate-700">{t("pipeline.flow.parseJsonTitle")}</span>
          <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-white px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200">
            {jsonOpen ? t("pipeline.flow.parseJsonCollapse") : t("pipeline.flow.parseJsonExpand")}
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`h-3.5 w-3.5 text-slate-500 transition-transform ${jsonOpen ? "rotate-180" : ""}`}
              aria-hidden
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
                clipRule="evenodd"
              />
            </svg>
          </span>
        </button>
        {jsonOpen ? (
          <pre className="code-block mt-2 max-h-80 overflow-auto text-xs">
            {JSON.stringify(signal, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  );
}
