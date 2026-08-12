import { useEffect, useId, useRef, useState } from "react";
import UiSelect from "./UiSelect";

type Props = {
  email: string;
  language: string;
  autostart: boolean;
  version: string;
  consoleUrl: string;
  labels: {
    language: string;
    autostart: string;
    openConsole: string;
    logout: string;
    quitApp: string;
    versionHint: string;
  };
  languageOptions: { value: string; label: string }[];
  busy: boolean;
  onLanguageChange: (value: string) => void;
  onAutostartChange: (enabled: boolean) => void;
  onLogout: () => void;
  onQuitApp: () => void;
};

function avatarInitial(email: string) {
  const local = (email.split("@")[0] || email).trim();
  if (!local) return "?";
  const ch = local.charAt(0);
  return /[a-zA-Z0-9]/.test(ch) ? ch.toUpperCase() : ch;
}

export default function UserMenu({
  email,
  language,
  autostart,
  version,
  consoleUrl,
  labels,
  languageOptions,
  busy,
  onLanguageChange,
  onAutostartChange,
  onLogout,
  onQuitApp,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const initial = avatarInitial(email);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="user-menu">
      <button
        type="button"
        className="user-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="user-avatar">{initial}</span>
        <span className="user-email">{email}</span>
        <svg viewBox="0 0 20 20" fill="currentColor" className={`user-menu-chevron${open ? " is-open" : ""}`} aria-hidden>
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open ? (
        <div id={menuId} role="menu" className="user-menu-panel">
          <div className="user-menu-header">{email}</div>
          <div className="user-menu-section">
            <label className="label">{labels.language}</label>
            <UiSelect
              value={language}
              onChange={onLanguageChange}
              options={languageOptions}
              aria-label={labels.language}
            />
          </div>
          <label className="user-menu-check">
            <input
              type="checkbox"
              className="ui-checkbox"
              checked={autostart}
              onChange={(e) => onAutostartChange(e.target.checked)}
            />
            {labels.autostart}
          </label>
          <a
            className="user-menu-item"
            href={consoleUrl}
            target="_blank"
            rel="noreferrer"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            {labels.openConsole}
          </a>
          <button
            type="button"
            className="user-menu-item"
            role="menuitem"
            disabled={busy}
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            {labels.logout}
          </button>
          <button
            type="button"
            className="user-menu-item user-menu-item-danger"
            role="menuitem"
            disabled={busy}
            onClick={() => {
              setOpen(false);
              onQuitApp();
            }}
          >
            {labels.quitApp}
          </button>
          <p className="user-menu-footer">
            v{version} · {labels.versionHint}
          </p>
        </div>
      ) : null}
    </div>
  );
}
