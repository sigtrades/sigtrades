/** SigTrades Webhook 推送标准 st_webhook_v1（对齐内部 Signal 透传）。 */

export const ST_WEBHOOK_CONTRACT = "st_webhook_v1" as const;

export type StAssetClass = "STOCK" | "OPTIONS";
export type StSide = "BUY" | "SELL";
export type StOptionRight = "CALL" | "PUT";
export type StOrderType = "MKT" | "LMT";
export type StSignalSubtype = "OPEN" | "CLOSE";

export type StOptionLegInput = {
  expiry: string; // YYYY-MM-DD
  strike: number;
  optionType: StOptionRight;
  action: StSide;
  quantity: number;
};

export type StWebhookForm = {
  signalId?: string;
  symbol: string;
  quantity: number;
  assetClass: StAssetClass;
  action: StSide;
  orderType: StOrderType;
  limitPrice?: number | null;
  signalSubtype?: StSignalSubtype;
  legs?: StOptionLegInput[];
};

export type StWebhookLeg = {
  symbol: string;
  action: StSide;
  quantity: number;
  strike: number;
  option_type: StOptionRight;
};

export type StWebhookPayload = {
  contract_version: typeof ST_WEBHOOK_CONTRACT;
  signal_id: string;
  action: string;
  symbol: string;
  quantity: number;
  order_type: StOrderType;
  asset_class: StAssetClass;
  limit_price?: number;
  signal_subtype?: StSignalSubtype;
  legs?: StWebhookLeg[];
  metadata?: {
    underlying: string;
    expiry: string;
  };
};

/** 对齐后端 `format_broker_option_symbol`：`UNDERLYING YYMMDD{C|P}########`（行权价 ×1000）。 */
export function formatOccOptionSymbol(
  underlying: string,
  expiry: string,
  right: StOptionRight | "C" | "P",
  strike: number,
): string {
  const und = underlying.trim().toUpperCase();
  const digits = expiry.replace(/[-/]/g, "");
  if (!und) throw new Error("underlying required");
  if (digits.length !== 8 || !/^\d{8}$/.test(digits)) {
    throw new Error(`invalid expiry: ${expiry}`);
  }
  if (!Number.isFinite(strike) || strike <= 0) {
    throw new Error(`invalid strike: ${strike}`);
  }
  const yy = digits.slice(2);
  const rightChar = right === "PUT" || right === "P" ? "P" : "C";
  const strikeStr = String(Math.round(strike * 1000)).padStart(8, "0");
  return `${und} ${yy}${rightChar}${strikeStr}`;
}

export function newStSignalId(): string {
  const hex =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
      : Math.random().toString(16).slice(2, 14);
  return `st-${hex}`;
}

export function buildStWebhookPayload(form: StWebhookForm): StWebhookPayload {
  const symbol = form.symbol.trim().toUpperCase();
  if (!symbol) throw new Error("symbol required");
  const quantity = Math.max(1, Math.floor(Number(form.quantity) || 1));
  const signalId = (form.signalId || "").trim() || newStSignalId();
  const orderType = form.orderType || "MKT";

  const base: StWebhookPayload = {
    contract_version: ST_WEBHOOK_CONTRACT,
    signal_id: signalId,
    action: form.action,
    symbol,
    quantity,
    order_type: orderType,
    asset_class: form.assetClass,
  };

  if (orderType === "LMT" && form.limitPrice != null && Number.isFinite(Number(form.limitPrice))) {
    base.limit_price = Number(form.limitPrice);
  }

  if (form.assetClass === "STOCK") {
    return base;
  }

  const legsIn = (form.legs || []).slice(0, 4);
  if (legsIn.length === 0) {
    throw new Error("options require at least one leg");
  }

  const legs: StWebhookLeg[] = legsIn.map((leg) => {
    const strike = Number(leg.strike);
    const legQty = Math.max(1, Math.floor(Number(leg.quantity) || 1));
    return {
      symbol: formatOccOptionSymbol(symbol, leg.expiry, leg.optionType, strike),
      action: leg.action,
      quantity: legQty,
      strike,
      option_type: leg.optionType,
    };
  });

  const multi = legs.length > 1;
  return {
    ...base,
    action: multi ? "组合" : form.action,
    signal_subtype: form.signalSubtype || "OPEN",
    legs,
    metadata: {
      underlying: symbol,
      expiry: legsIn[0].expiry,
    },
  };
}

export function stringifyStWebhookPayload(payload: StWebhookPayload): string {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

/** 文档/UI 静态示例（股票）。 */
export const ST_WEBHOOK_STOCK_SAMPLE: StWebhookPayload = {
  contract_version: ST_WEBHOOK_CONTRACT,
  signal_id: "st-20260729-001",
  action: "BUY",
  symbol: "AAPL",
  quantity: 10,
  order_type: "MKT",
  asset_class: "STOCK",
};

/** 文档/UI 静态示例（单腿期权）。 */
export const ST_WEBHOOK_OPTION_SAMPLE: StWebhookPayload = {
  contract_version: ST_WEBHOOK_CONTRACT,
  signal_id: "st-20260729-002",
  action: "SELL",
  symbol: "SPX",
  quantity: 1,
  order_type: "MKT",
  asset_class: "OPTIONS",
  signal_subtype: "OPEN",
  legs: [
    {
      symbol: "SPX 240119P04500000",
      action: "SELL",
      quantity: 1,
      strike: 4500,
      option_type: "PUT",
    },
  ],
  metadata: {
    underlying: "SPX",
    expiry: "2024-01-19",
  },
};

export const TV_WEBHOOK_SAMPLE = {
  ticker: "AAPL",
  action: "buy",
  quantity: 10,
};
