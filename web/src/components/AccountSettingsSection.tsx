import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { useAuth } from "../store/auth";

function SectionCard({
  icon,
  iconBg,
  title,
  children,
}: {
  icon: React.ReactNode;
  iconBg: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${iconBg}`}>{icon}</div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      </div>
      <div className="mt-5">{children}</div>
    </div>
  );
}

function PasswordField({
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  hint?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <div className="relative mt-1.5">
        <input
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-xl border border-slate-200 px-4 py-2.5 pr-10 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          aria-label={visible ? "Hide" : "Show"}
        >
          {visible ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
              <path d="M3 3l18 18M10.6 10.7a2 2 0 002.7 2.7M9.9 4.3A10.7 10.7 0 0112 4c5 0 8.5 4.3 9.5 6-.4.7-1.2 1.8-2.3 2.9M6.1 6.1C4.3 7.3 3.1 9 2.5 10c1 1.7 4.5 6 9.5 6 1 0 1.9-.2 2.8-.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
              <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="12" cy="12" r="2.5" />
            </svg>
          )}
        </button>
      </div>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export default function AccountSettingsSection() {
  const { t } = useTranslation();
  const { user, fetchMe } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileMsg, setProfileMsg] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState("");
  const [passwordErr, setPasswordErr] = useState("");

  useEffect(() => {
    setDisplayName(user?.display_name || "");
  }, [user?.display_name]);

  const saveProfile = async () => {
    setProfileBusy(true);
    setProfileMsg("");
    try {
      await api.patch("/me", { display_name: displayName.trim() || null });
      await fetchMe();
      setProfileMsg(t("account.profileSaved"));
    } catch {
      setProfileMsg(t("account.profileError"));
    } finally {
      setProfileBusy(false);
    }
  };

  const changePassword = async () => {
    setPasswordErr("");
    setPasswordMsg("");
    if (newPassword.length < 8) {
      setPasswordErr(t("account.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordErr(t("account.passwordMismatch"));
      return;
    }
    setPasswordBusy(true);
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMsg(t("account.passwordChanged"));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPasswordErr(detail === "incorrect password" ? t("account.passwordWrong") : t("account.passwordError"));
    } finally {
      setPasswordBusy(false);
    }
  };

  const isGoogle = user?.auth_provider === "google";

  return (
    <div className="space-y-6">
      <SectionCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
            <path d="M20 21a8 8 0 10-16 0M12 11a4 4 0 100-8 4 4 0 000 8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
        iconBg="bg-brand-50 text-brand-700"
        title={t("account.personalInfo")}
      >
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-slate-700">{t("account.email")}</label>
            <div className="relative mt-1.5">
              <input
                type="email"
                value={user?.email || ""}
                readOnly
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-600"
              />
              {user?.email_verified && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-emerald-500" title={t("account.emailVerified")}>
                  ✓
                </span>
              )}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">{t("account.nickname")}</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={t("account.nicknamePlaceholder")}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => void saveProfile()} disabled={profileBusy} className="btn-primary">
              {profileBusy ? t("common.loading") : t("account.save")}
            </button>
            {profileMsg && <span className="text-sm text-slate-500">{profileMsg}</span>}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden>
            <rect x="5" y="10" width="14" height="11" rx="2" />
            <path d="M8 10V7a4 4 0 018 0v3" strokeLinecap="round" />
          </svg>
        }
        iconBg="bg-amber-50 text-amber-700"
        title={t("account.changePassword")}
      >
        {isGoogle ? (
          <p className="text-sm text-slate-500">{t("account.googlePasswordHint")}</p>
        ) : (
          <div className="space-y-4">
            <PasswordField
              label={t("account.currentPassword")}
              value={currentPassword}
              onChange={setCurrentPassword}
              placeholder={t("account.currentPasswordPlaceholder")}
            />
            <PasswordField
              label={t("account.newPassword")}
              value={newPassword}
              onChange={setNewPassword}
              placeholder={t("account.newPasswordPlaceholder")}
              hint={t("account.passwordHint")}
            />
            <PasswordField
              label={t("account.confirmPassword")}
              value={confirmPassword}
              onChange={setConfirmPassword}
              placeholder={t("account.confirmPasswordPlaceholder")}
            />
            {passwordErr && <p className="text-sm text-red-600">{passwordErr}</p>}
            {passwordMsg && <p className="text-sm text-emerald-600">{passwordMsg}</p>}
            <button
              type="button"
              onClick={() => void changePassword()}
              disabled={passwordBusy || !currentPassword || !newPassword}
              className="btn-primary"
            >
              {passwordBusy ? t("common.loading") : t("account.changePassword")}
            </button>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
