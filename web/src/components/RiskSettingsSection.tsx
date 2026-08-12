import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";

export default function RiskSettingsSection() {
  const { t } = useTranslation();
  // 资金类限制暂不展示；保存时原样回写，避免被清空
  const [maxPos, setMaxPos] = useState<number | null>(null);
  const [stopLoss, setStopLoss] = useState<number | null>(null);
  const [takeProfit, setTakeProfit] = useState<number | null>(null);
  const [maxDailyLoss, setMaxDailyLoss] = useState<number | null>(null);
  const [start, setStart] = useState("09:30");
  const [end, setEnd] = useState("16:00");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get("/config/risk").then((r) => {
      const d = r.data;
      setMaxPos(d.max_position_usd ?? null);
      setStopLoss(d.stop_loss_pct ?? null);
      setTakeProfit(d.take_profit_pct ?? null);
      setMaxDailyLoss(d.max_daily_loss_usd ?? null);
      const h = d.trading_hours || {};
      if (h.start) setStart(h.start);
      if (h.end) setEnd(h.end);
    });
  }, []);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    try {
      await api.put("/config/risk", {
        max_position_usd: maxPos,
        stop_loss_pct: stopLoss,
        take_profit_pct: takeProfit,
        max_daily_loss_usd: maxDailyLoss,
        trading_hours: { tz: "America/New_York", start, end, days: [0, 1, 2, 3, 4] },
        enabled: true,
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-5">
      <section className="card overflow-hidden p-0">
        <div className="border-b border-slate-100 bg-gradient-to-r from-slate-950 to-slate-900 px-6 py-5 text-white">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-300">{t("riskSettings.eyebrow")}</p>
          <h2 className="mt-1 text-xl font-bold">{t("riskSettings.title")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-300">{t("riskSettings.subtitle")}</p>
        </div>

        <div className="p-6">
          <div className="mx-auto max-w-xl rounded-2xl border border-brand-100 bg-brand-50/60 p-5">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
                  <path d="M12 7v5l3 2M4.9 4.9a10 10 0 1014.2 0" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <div>
                <p className="font-semibold text-slate-900">{t("riskSettings.hoursTitle")}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">{t("common.timezoneEt")}</p>
              </div>
            </div>
            <div className="mt-5 grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
              <TimeField label={t("riskSettings.start")} value={start} onChange={setStart} />
              <span className="hidden pb-2 text-center text-slate-400 sm:block">→</span>
              <TimeField label={t("riskSettings.end")} value={end} onChange={setEnd} />
            </div>
            <p className="mt-4 rounded-xl bg-white/80 px-3 py-2 text-xs text-slate-600 ring-1 ring-brand-100">
              {t("riskSettings.weekdays")}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50/70 px-6 py-4">
          {saved && <span className="text-sm font-medium text-profit">{t("riskSettings.saved")}</span>}
          <button className="btn-primary" disabled={saving}>
            {saving ? t("common.loading") : t("dashboard.save")}
          </button>
        </div>
      </section>
    </form>
  );
}

function TimeField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-600">{label}</span>
      <input type="time" className="input w-full" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
