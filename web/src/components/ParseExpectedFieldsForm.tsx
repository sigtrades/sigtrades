import { useTranslation } from "react-i18next";
import type { ParseExpectedForm } from "../lib/parseExpectedFields";
import UiSelect from "./UiSelect";

type Props = {
  value: ParseExpectedForm;
  onChange: (next: ParseExpectedForm) => void;
  disabled?: boolean;
};

export default function ParseExpectedFieldsForm({ value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const isOption = value.assetClass === "OPTIONS";

  const set = (patch: Partial<ParseExpectedForm>) => onChange({ ...value, ...patch });

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <p className="text-xs text-slate-500">{t("dashboard.parseExpectedFormHint")}</p>

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.parseFieldAssetClass")}
          </span>
          <UiSelect
            value={value.assetClass}
            disabled={disabled}
            onChange={(v) => set({ assetClass: v as ParseExpectedForm["assetClass"] })}
            options={[
              { value: "OPTIONS", label: t("dashboard.parseAssetOptions") },
              { value: "STOCK", label: t("dashboard.parseAssetStock") },
            ]}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.parseFieldAction")}
          </span>
          <UiSelect
            value={value.action}
            disabled={disabled}
            onChange={(v) => set({ action: v as ParseExpectedForm["action"] })}
            options={[
              { value: "BUY", label: "BUY" },
              { value: "SELL", label: "SELL" },
            ]}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.parseFieldSubtype")}
          </span>
          <UiSelect
            value={value.signalSubtype}
            disabled={disabled}
            onChange={(v) => set({ signalSubtype: v as ParseExpectedForm["signalSubtype"] })}
            options={[
              { value: "OPEN", label: "OPEN" },
              { value: "CLOSE", label: "CLOSE" },
            ]}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.parseFieldUnderlying")}
          </span>
          <input
            className="input w-full text-sm"
            disabled={disabled}
            value={value.underlying}
            placeholder="SPY"
            onChange={(e) => set({ underlying: e.target.value.toUpperCase() })}
          />
        </label>
        {isOption ? (
          <>
            <label className="space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {t("dashboard.parseFieldStrike")}
              </span>
              <input
                className="input w-full text-sm"
                disabled={disabled}
                value={value.strike}
                placeholder="10"
                onChange={(e) => set({ strike: e.target.value })}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {t("dashboard.parseFieldRight")}
              </span>
              <UiSelect
                value={value.right || "C"}
                disabled={disabled}
                onChange={(v) => set({ right: v as "C" | "P" })}
                options={[
                  { value: "C", label: t("dashboard.parseRightCall") },
                  { value: "P", label: t("dashboard.parseRightPut") },
                ]}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {t("dashboard.parseFieldExpiry")}
              </span>
              <input
                className="input w-full text-sm"
                disabled={disabled}
                value={value.expiry}
                placeholder="2026-06-18"
                onChange={(e) => set({ expiry: e.target.value })}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {t("dashboard.parseFieldDte")}
              </span>
              <input
                className="input w-full text-sm"
                type="number"
                min={0}
                disabled={disabled}
                value={value.dte}
                placeholder="0"
                onChange={(e) => set({ dte: e.target.value })}
              />
              <p className="text-[11px] text-slate-400">{t("dashboard.parseFieldDteHint")}</p>
            </label>
          </>
        ) : null}
        <label className="space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.parseFieldQuantity")}
          </span>
          <input
            className="input w-full text-sm"
            type="number"
            min={1}
            disabled={disabled}
            value={value.quantity}
            onChange={(e) => set({ quantity: e.target.value })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {t("dashboard.parseFieldOrderType")}
          </span>
          <UiSelect
            value={value.orderType}
            disabled={disabled}
            onChange={(v) => set({ orderType: v as ParseExpectedForm["orderType"] })}
            options={[
              { value: "LMT", label: t("dashboard.parseOrderTypeLmt") },
              { value: "MKT", label: t("dashboard.parseOrderTypeMkt") },
            ]}
          />
        </label>
        {value.orderType === "LMT" ? (
          <label className="space-y-1 sm:col-span-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
              {t("dashboard.parseFieldLimitPrice")}
            </span>
            <input
              className="input w-full text-sm"
              disabled={disabled}
              value={value.limitPrice}
              placeholder="0.39"
              onChange={(e) => set({ limitPrice: e.target.value })}
            />
          </label>
        ) : null}
      </div>
    </div>
  );
}
