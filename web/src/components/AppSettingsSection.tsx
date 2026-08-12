import { useTranslation } from "react-i18next";
import api from "../lib/api";

type Props = {
  killSwitch: boolean;
  soundNotifications: boolean;
  onKillSwitchChanged: (next: boolean) => void;
  onSoundNotificationsChanged: (next: boolean) => void;
};

export default function AppSettingsSection({
  killSwitch,
  soundNotifications,
  onKillSwitchChanged,
  onSoundNotificationsChanged,
}: Props) {
  const { t } = useTranslation();

  const toggleKill = async () => {
    const next = !killSwitch;
    await api.post("/config/kill-switch", { enabled: next });
    onKillSwitchChanged(next);
  };

  const toggleSound = async () => {
    const next = !soundNotifications;
    await api.patch("/me", { sound_notifications: next });
    onSoundNotificationsChanged(next);
  };

  return (
    <div className="space-y-6">
      <div className="card overflow-hidden p-0">
        <div className="border-b border-slate-100 px-6 py-5">
          <p className="section-eyebrow">{t("console.nav.settings")}</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">{t("settings.soundTitle")}</h2>
          <p className="mt-1 text-sm text-slate-500">{t("settings.soundHint")}</p>
        </div>
        <SwitchRow
          title={t("settings.soundToggle")}
          hint={soundNotifications ? t("settings.soundOn") : t("settings.soundOff")}
          checked={soundNotifications}
          onChange={() => void toggleSound()}
        />
      </div>

      <div className={`overflow-hidden rounded-2xl border bg-white shadow-card ${killSwitch ? "border-loss/40" : "border-slate-200"}`}>
        <div className={`px-6 py-5 ${killSwitch ? "bg-loss-soft" : "bg-slate-50"}`}>
          <div className="flex items-start gap-3">
            <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${killSwitch ? "bg-loss text-white" : "bg-slate-200 text-slate-600"}`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
                <path d="M12 3l8 4v5c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V7zM9 12h6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <div>
              <p className={`section-eyebrow ${killSwitch ? "!text-loss" : ""}`}>{t("dashboard.killSwitch")}</p>
              <h2 className="mt-1 text-lg font-semibold text-slate-950">{t("settings.killSwitchTitle")}</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">{t("settings.killSwitchHint")}</p>
            </div>
          </div>
        </div>
        <SwitchRow
          title={`${t("dashboard.killSwitch")}: ${killSwitch ? "ON" : "OFF"}`}
          hint={killSwitch ? t("execPipeline.paused") : t("dashboard.online")}
          checked={killSwitch}
          danger
          onChange={() => void toggleKill()}
        />
      </div>
    </div>
  );
}

function SwitchRow({
  title,
  hint,
  checked,
  danger = false,
  onChange,
}: {
  title: string;
  hint: string;
  checked: boolean;
  danger?: boolean;
  onChange: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-6 py-4">
      <div>
        <p className="text-sm font-medium text-slate-900">{title}</p>
        <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={onChange}
        className={`toggle ${checked ? (danger ? "bg-loss" : "bg-brand-500") : "bg-slate-300"}`}
      >
        <span className={`toggle-thumb ${checked ? "translate-x-5" : "translate-x-0"}`} />
      </button>
    </div>
  );
}
