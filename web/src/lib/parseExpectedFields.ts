/** 样例规则「期望输出」表单 ↔ 后端 expected_output JSON */

export type ParseExpectedForm = {
  assetClass: "OPTIONS" | "STOCK";
  action: "BUY" | "SELL";
  signalSubtype: "OPEN" | "CLOSE";
  underlying: string;
  strike: string;
  right: "C" | "P" | "";
  expiry: string;
  dte: string;
  quantity: string;
  orderType: "MKT" | "LMT";
  limitPrice: string;
};

/** 默认 0DTE 样例：一行标准开仓格式（SPY ~735） */
export const DEFAULT_FLOW_SAMPLE = "BUY SPY 735C @2.45";

export const DEFAULT_PARSE_EXPECTED_FORM: ParseExpectedForm = {
  assetClass: "OPTIONS",
  action: "BUY",
  signalSubtype: "OPEN",
  underlying: "SPY",
  strike: "735",
  right: "C",
  expiry: "",
  dte: "0",
  quantity: "1",
  orderType: "LMT",
  limitPrice: "2.45",
};

/** SPY 正股样例 */
export const SPY_STOCK_SAMPLE = "BUY SPY 100 @735.50";

export const SPY_STOCK_EXPECTED_FORM: ParseExpectedForm = {
  assetClass: "STOCK",
  action: "BUY",
  signalSubtype: "OPEN",
  underlying: "SPY",
  strike: "",
  right: "",
  expiry: "",
  dte: "",
  quantity: "100",
  orderType: "LMT",
  limitPrice: "735.50",
};

/** 两行期权 flow 样例（SPY） */
export const SPY_OPTION_FLOW_SAMPLE = `SPY 735 C 2026-07-30
$245K AVG$2.45 0DTE`;

export const SPY_OPTION_FLOW_EXPECTED_FORM: ParseExpectedForm = {
  assetClass: "OPTIONS",
  action: "BUY",
  signalSubtype: "OPEN",
  underlying: "SPY",
  strike: "735",
  right: "C",
  expiry: "2026-07-30",
  dte: "0",
  quantity: "1",
  orderType: "LMT",
  limitPrice: "2.45",
};

/** 从监听消息/样例文本推断期望输出字段（两行 flow 或单行 BUY） */
export function inferExpectedFormFromSample(text: string): Partial<ParseExpectedForm> | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const flowHead = trimmed.match(/^([A-Z][A-Z0-9.]*)\s+([\d.]+)\s+([CP])\s+(\d{4}-\d{2}-\d{2})/im);
  const flowMeta = trimmed.match(/\$[\d.]+[KMB]\s+AVG\$([\d.]+)\s+(\d+)DTE/i);
  if (flowHead) {
    const right = flowHead[3].toUpperCase();
    return {
      assetClass: "OPTIONS",
      action: "BUY",
      signalSubtype: "OPEN",
      underlying: flowHead[1].toUpperCase(),
      strike: flowHead[2],
      right: right === "P" ? "P" : "C",
      expiry: flowHead[4],
      dte: flowMeta?.[2] ?? "",
      orderType: "LMT",
      limitPrice: flowMeta?.[1] ?? "",
      quantity: "1",
    };
  }

  const buyOpt = trimmed.match(/^BUY\s+([A-Z][A-Z0-9.]*)\s+(\d+(?:\.\d+)?)([CP])\s*@([\d.]+)/i);
  if (buyOpt) {
    const right = buyOpt[3].toUpperCase();
    return {
      assetClass: "OPTIONS",
      action: "BUY",
      signalSubtype: "OPEN",
      underlying: buyOpt[1].toUpperCase(),
      strike: buyOpt[2],
      right: right === "P" ? "P" : "C",
      expiry: "",
      dte: "0",
      orderType: "LMT",
      limitPrice: buyOpt[4],
      quantity: "1",
    };
  }

  const buyStock = trimmed.match(/^BUY\s+([A-Z][A-Z0-9.]*)\s+(\d+(?:\.\d+)?)\s*@([\d.]+)/i);
  if (buyStock) {
    return {
      assetClass: "STOCK",
      action: "BUY",
      signalSubtype: "OPEN",
      underlying: buyStock[1].toUpperCase(),
      strike: "",
      right: "",
      expiry: "",
      dte: "",
      orderType: "LMT",
      limitPrice: buyStock[3],
      quantity: buyStock[2],
    };
  }

  return null;
}

/** 样例与期望字段不一致时，优先用样例推断的标的/行权价等 */
export function resolveExpectedFormForGenerate(sample: string, form: ParseExpectedForm): ParseExpectedForm {
  const inferred = inferExpectedFormFromSample(sample);
  if (!inferred?.underlying) return form;
  const sampleTicker = inferred.underlying.toUpperCase();
  const formTicker = form.underlying.trim().toUpperCase();
  if (!formTicker || formTicker !== sampleTicker) {
    return { ...form, ...inferred };
  }
  return form;
}

export function buildExpectedOutput(form: ParseExpectedForm): Record<string, unknown> {
  const qty = Number.parseInt(form.quantity, 10);
  const out: Record<string, unknown> = {
    action: form.action,
    quantity: Number.isFinite(qty) && qty > 0 ? qty : 1,
    order_type: form.orderType,
    signal_subtype: form.signalSubtype,
    asset_class: form.assetClass,
  };

  const underlying = form.underlying.trim().toUpperCase();
  if (form.assetClass === "OPTIONS") {
    const strike = form.strike.trim();
    const right = form.right;
    out.symbol = strike && right ? `${underlying} ${strike}${right}` : underlying;
    const meta: Record<string, unknown> = { underlying };
    if (strike) {
      const strikeNum = Number.parseFloat(strike);
      if (Number.isFinite(strikeNum)) meta.strike = strikeNum;
    }
    if (right) meta.right = right;
    if (form.expiry.trim()) meta.expiry = form.expiry.trim();
    const dte = Number.parseInt(form.dte, 10);
    if (Number.isFinite(dte) && dte >= 0) meta.dte = dte;
    out.metadata = meta;
  } else {
    out.symbol = underlying;
  }

  if (form.orderType === "LMT") {
    const px = Number.parseFloat(form.limitPrice);
    if (Number.isFinite(px)) out.limit_price = px;
  }
  return out;
}

function parseSymbolParts(symbol: string): { underlying: string; strike: string; right: "C" | "P" | "" } {
  const text = symbol.trim();
  const m = text.match(/^([A-Z][A-Z0-9]*)\s+(\d+(?:\.\d+)?)([CP])$/i);
  if (m) {
    return {
      underlying: m[1].toUpperCase(),
      strike: m[2],
      right: m[3].toUpperCase() as "C" | "P",
    };
  }
  const compact = text.match(/^([A-Z][A-Z0-9]*)(\d+(?:\.\d+)?)([CP])$/i);
  if (compact) {
    return {
      underlying: compact[1].toUpperCase(),
      strike: compact[2],
      right: compact[3].toUpperCase() as "C" | "P",
    };
  }
  return { underlying: text.split(/\s+/)[0]?.toUpperCase() || "", strike: "", right: "" };
}

export function formFromExpectedOutput(raw: Record<string, unknown>): ParseExpectedForm {
  const meta = (raw.metadata as Record<string, unknown> | undefined) || {};
  const assetClass = String(raw.asset_class || "OPTIONS").toUpperCase() === "STOCK" ? "STOCK" : "OPTIONS";
  const symbol = String(raw.symbol || meta.underlying || "");
  const parts = parseSymbolParts(symbol);

  const underlying = String(meta.underlying || parts.underlying || "");
  const strikeRaw = meta.strike ?? parts.strike;
  const rightRaw = meta.right ?? parts.right;

  return {
    assetClass,
    action: String(raw.action || "BUY").toUpperCase() === "SELL" ? "SELL" : "BUY",
    signalSubtype: String(raw.signal_subtype || "OPEN").toUpperCase() === "CLOSE" ? "CLOSE" : "OPEN",
    underlying,
    strike: strikeRaw != null ? String(strikeRaw) : "",
    right: String(rightRaw || "").toUpperCase() === "P" ? "P" : String(rightRaw || "").toUpperCase() === "C" ? "C" : "",
    expiry: String(meta.expiry || meta.expiry_date || ""),
    dte: meta.dte != null ? String(meta.dte) : "",
    quantity: raw.quantity != null ? String(raw.quantity) : "1",
    orderType: String(raw.order_type || "MKT").toUpperCase() === "LMT" ? "LMT" : "MKT",
    limitPrice: raw.limit_price != null ? String(raw.limit_price) : "",
  };
}
