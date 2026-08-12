import { Fragment, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  type StAssetClass,
  type StOptionLegInput,
  type StOptionRight,
  type StOrderType,
  type StSide,
  type StSignalSubtype,
  buildStWebhookPayload,
  newStSignalId,
  stringifyStWebhookPayload,
} from "../lib/stWebhookV1";
import ModalShell from "./ModalShell";

type Props = {
  open: boolean;
  onClose: () => void;
};

/** Lightweight JSON syntax highlight for the light preview panel. */
function highlightJson(text: string): ReactNode[] {
  const re =
    /("(?:\\.|[^"\\])*")\s*:|("(?:\\.|[^"\\])*")|(\btrue\b|\bfalse\b|\bnull\b)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|([{}\[\],:])|(\s+)/g;
  const nodes: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(
        <span key={`t-${i++}`} className="text-slate-500">
          {text.slice(last, m.index)}
        </span>,
      );
    }
    if (m[1] != null) {
      nodes.push(
        <Fragment key={`k-${i++}`}>
          <span className="font-semibold text-sky-700">{m[1]}</span>
          <span className="text-slate-400">:</span>
        </Fragment>,
      );
    } else if (m[2] != null) {
      nodes.push(
        <span key={`s-${i++}`} className="text-emerald-700">
          {m[2]}
        </span>,
      );
    } else if (m[3] != null) {
      nodes.push(
        <span key={`b-${i++}`} className="font-medium text-violet-700">
          {m[3]}
        </span>,
      );
    } else if (m[4] != null) {
      nodes.push(
        <span key={`n-${i++}`} className="font-medium text-amber-700">
          {m[4]}
        </span>,
      );
    } else if (m[5] != null) {
      nodes.push(
        <span key={`p-${i++}`} className="text-slate-400">
          {m[5]}
        </span>,
      );
    } else if (m[6] != null) {
      nodes.push(<span key={`w-${i++}`}>{m[6]}</span>);
    }
    last = re.lastIndex;
  }
  if (last < text.length) {
    nodes.push(
      <span key={`t-${i++}`} className="text-slate-500">
        {text.slice(last)}
      </span>,
    );
  }
  return nodes;
}

function todayYmd(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultLeg(): StOptionLegInput {
  return {
    expiry: todayYmd(),
    strike: 100,
    optionType: "PUT",
    action: "SELL",
    quantity: 1,
  };
}

export default function WebhookSignalJsonModal({ open, onClose }: Props) {
  const { t } = useTranslation();
  const [signalId, setSignalId] = useState(() => newStSignalId());
  const [symbol, setSymbol] = useState("AAPL");
  const [quantity, setQuantity] = useState(10);
  const [assetClass, setAssetClass] = useState<StAssetClass>("STOCK");
  const [action, setAction] = useState<StSide>("BUY");
  const [orderType, setOrderType] = useState<StOrderType>("MKT");
  const [limitPrice, setLimitPrice] = useState("");
  const [signalSubtype, setSignalSubtype] = useState<StSignalSubtype>("OPEN");
  const [legs, setLegs] = useState<StOptionLegInput[]>([defaultLeg()]);
  const [copied, setCopied] = useState(false);

  const built = useMemo(() => {
    try {
      const payload = buildStWebhookPayload({
        signalId,
        symbol,
        quantity,
        assetClass,
        action,
        orderType,
        limitPrice: limitPrice === "" ? null : Number(limitPrice),
        signalSubtype,
        legs: assetClass === "OPTIONS" ? legs : undefined,
      });
      return { ok: true as const, text: stringifyStWebhookPayload(payload), error: "" };
    } catch (e) {
      return { ok: false as const, text: "", error: e instanceof Error ? e.message : String(e) };
    }
  }, [signalId, symbol, quantity, assetClass, action, orderType, limitPrice, signalSubtype, legs]);

  const copyJson = async () => {
    if (!built.ok) return;
    try {
      await navigator.clipboard.writeText(built.text.trim());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      window.prompt(t("webhookJson.copyPrompt"), built.text.trim());
    }
  };

  const updateLeg = (index: number, patch: Partial<StOptionLegInput>) => {
    setLegs((prev) => prev.map((leg, i) => (i === index ? { ...leg, ...patch } : leg)));
  };

  return (
    <ModalShell
      open={open}
      title={t("webhookJson.modalTitle")}
      onClose={onClose}
      panelClassName="max-w-3xl"
    >
      <p className="text-sm text-slate-600">{t("webhookJson.modalHint")}</p>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-600">{t("webhookJson.signalId")}</label>
            <div className="mt-1 flex gap-2">
              <input className="input min-w-0 flex-1 font-mono text-xs" value={signalId} onChange={(e) => setSignalId(e.target.value)} />
              <button type="button" className="btn-secondary shrink-0 text-xs" onClick={() => setSignalId(newStSignalId())}>
                {t("webhookJson.regenerateId")}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600">{t("webhookJson.symbol")}</label>
              <input
                className="input mt-1 w-full uppercase"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600">{t("webhookJson.quantity")}</label>
              <input
                className="input mt-1 w-full"
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600">{t("webhookJson.assetClass")}</label>
            <div className="mt-1 flex gap-2">
              {(["STOCK", "OPTIONS"] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={
                    assetClass === key
                      ? "rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white"
                      : "rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  }
                  onClick={() => {
                    setAssetClass(key);
                    if (key === "OPTIONS") {
                      setQuantity(1);
                      setLegs((prev) => (prev.length ? prev : [defaultLeg()]));
                    } else {
                      setQuantity(10);
                    }
                  }}
                >
                  {t(`webhookJson.asset.${key}`)}
                </button>
              ))}
            </div>
          </div>

          {assetClass === "STOCK" ? (
            <div>
              <label className="text-xs font-medium text-slate-600">{t("webhookJson.action")}</label>
              <div className="mt-1 flex gap-2">
                {(["BUY", "SELL"] as const).map((side) => (
                  <button
                    key={side}
                    type="button"
                    className={
                      action === side
                        ? "rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
                        : "rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
                    }
                    onClick={() => setAction(side)}
                  >
                    {side}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <label className="text-xs font-medium text-slate-600">{t("webhookJson.signalSubtype")}</label>
              <div className="mt-1 flex gap-2">
                {(["OPEN", "CLOSE"] as const).map((sub) => (
                  <button
                    key={sub}
                    type="button"
                    className={
                      signalSubtype === sub
                        ? "rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
                        : "rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
                    }
                    onClick={() => setSignalSubtype(sub)}
                  >
                    {t(`webhookJson.subtype.${sub}`)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600">{t("webhookJson.orderType")}</label>
              <select
                className="input mt-1 w-full"
                value={orderType}
                onChange={(e) => setOrderType(e.target.value as StOrderType)}
              >
                <option value="MKT">{t("webhookJson.orderMkt")}</option>
                <option value="LMT">{t("webhookJson.orderLmt")}</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600">{t("webhookJson.limitPrice")}</label>
              <input
                className="input mt-1 w-full"
                type="number"
                step="any"
                disabled={orderType !== "LMT"}
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                placeholder={orderType === "LMT" ? "0.00" : "—"}
              />
            </div>
          </div>

          {assetClass === "OPTIONS" ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-slate-600">{t("webhookJson.legs")}</label>
                <button
                  type="button"
                  className="text-xs font-medium text-brand-700 hover:underline disabled:opacity-40"
                  disabled={legs.length >= 4}
                  onClick={() => setLegs((prev) => (prev.length >= 4 ? prev : [...prev, defaultLeg()]))}
                >
                  {t("webhookJson.addLeg")}
                </button>
              </div>
              {legs.map((leg, index) => (
                <div key={index} className="rounded-xl border border-slate-200 bg-slate-50/80 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-slate-700">{t("webhookJson.legN", { n: index + 1 })}</p>
                    {legs.length > 1 ? (
                      <button
                        type="button"
                        className="text-xs text-loss hover:underline"
                        onClick={() => setLegs((prev) => prev.filter((_, i) => i !== index))}
                      >
                        {t("webhookJson.removeLeg")}
                      </button>
                    ) : null}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[11px] text-slate-500">{t("webhookJson.expiry")}</label>
                      <input
                        className="input mt-0.5 w-full text-xs"
                        type="date"
                        value={leg.expiry}
                        onChange={(e) => updateLeg(index, { expiry: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="text-[11px] text-slate-500">{t("webhookJson.strike")}</label>
                      <input
                        className="input mt-0.5 w-full text-xs"
                        type="number"
                        step="any"
                        value={leg.strike}
                        onChange={(e) => updateLeg(index, { strike: Number(e.target.value) || 0 })}
                      />
                    </div>
                    <div>
                      <label className="text-[11px] text-slate-500">{t("webhookJson.optionType")}</label>
                      <select
                        className="input mt-0.5 w-full text-xs"
                        value={leg.optionType}
                        onChange={(e) => updateLeg(index, { optionType: e.target.value as StOptionRight })}
                      >
                        <option value="PUT">PUT</option>
                        <option value="CALL">CALL</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-[11px] text-slate-500">{t("webhookJson.legAction")}</label>
                      <select
                        className="input mt-0.5 w-full text-xs"
                        value={leg.action}
                        onChange={(e) => updateLeg(index, { action: e.target.value as StSide })}
                      >
                        <option value="BUY">BUY</option>
                        <option value="SELL">SELL</option>
                      </select>
                    </div>
                    <div className="col-span-2">
                      <label className="text-[11px] text-slate-500">{t("webhookJson.legQty")}</label>
                      <input
                        className="input mt-0.5 w-full text-xs"
                        type="number"
                        min={1}
                        value={leg.quantity}
                        onChange={(e) =>
                          updateLeg(index, { quantity: Math.max(1, Number(e.target.value) || 1) })
                        }
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex min-h-[16rem] flex-col">
          <label className="text-xs font-medium text-slate-600">{t("webhookJson.preview")}</label>
          {built.ok ? (
            <pre className="mt-1 flex-1 overflow-auto rounded-xl border border-slate-200 bg-white p-3 font-mono text-[11px] leading-relaxed shadow-sm ring-1 ring-slate-100">
              {highlightJson(built.text)}
            </pre>
          ) : (
            <p className="mt-1 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              {built.error}
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
        <button type="button" className="btn-secondary" onClick={onClose}>
          {t("common.close")}
        </button>
        <button type="button" className="btn-primary" disabled={!built.ok} onClick={() => void copyJson()}>
          {copied ? t("dashboard.copied") : t("webhookJson.copyJson")}
        </button>
      </div>
    </ModalShell>
  );
}
