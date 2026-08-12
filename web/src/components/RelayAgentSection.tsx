import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";

type PlatformRelease = {
  latest_version?: string;
  download_url?: string;
  filename?: string;
  release_notes?: string;
};

type AgentVersion = {
  latest_version?: string;
  download_url?: string;
  filename?: string;
  platforms?: {
    macos?: PlatformRelease;
    windows?: PlatformRelease;
  };
};

type Props = {
  agentOnline: boolean;
};

function packageName(url?: string, filename?: string): string {
  const fromField = (filename || "").trim();
  if (fromField) return fromField;
  const u = (url || "").trim();
  if (!u) return "";
  try {
    const path = new URL(u, window.location.origin).pathname;
    const name = path.split("/").filter(Boolean).pop() || "";
    return decodeURIComponent(name);
  } catch {
    return u.split("/").filter(Boolean).pop() || "";
  }
}

export default function RelayAgentSection({ agentOnline }: Props) {
  const { t } = useTranslation();
  const [version, setVersion] = useState<AgentVersion | null>(null);

  useEffect(() => {
    api.get("/public/agent-version").then((r) => setVersion(r.data)).catch(() => {});
  }, []);

  const macos = version?.platforms?.macos;
  const windows = version?.platforms?.windows;
  const macUrl = macos?.download_url?.trim() || "";
  const winUrl = windows?.download_url?.trim() || "";
  const legacyUrl = version?.download_url?.trim() || "";
  const hasAnyDownload = Boolean(macUrl || winUrl || legacyUrl);

  return (
    <div className="card">
      <h2 className="font-semibold">{t("dashboard.relayAgent")}</h2>
      <p className="mt-2 text-sm text-slate-600">{t("onboarding.agentHint")}</p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {macUrl ? (
          <DownloadButton
            href={macUrl}
            label={t("dashboard.agentDownloadMac")}
            version={macos?.latest_version}
            filename={packageName(macUrl, macos?.filename)}
          />
        ) : null}
        {winUrl ? (
          <DownloadButton
            href={winUrl}
            label={t("dashboard.agentDownloadWindows")}
            version={windows?.latest_version}
            filename={packageName(winUrl, windows?.filename)}
          />
        ) : null}
        {!macUrl && !winUrl && legacyUrl ? (
          <DownloadButton
            href={legacyUrl}
            label={t("dashboard.agentDownload")}
            version={version?.latest_version}
            filename={packageName(legacyUrl, version?.filename)}
          />
        ) : null}
        {!hasAnyDownload ? (
          <p className="text-sm text-slate-500">{t("dashboard.agentDownloadUnavailable")}</p>
        ) : null}
      </div>

      <div className="mt-5 border-t border-slate-100 pt-5">
        <p className="text-sm font-medium text-slate-700">{t("dashboard.agentLoginStep")}</p>
        <p className="mt-2 text-sm text-slate-600">{t("dashboard.agentLoginHint")}</p>
        <p className="mt-3 text-sm text-slate-600">
          {t("dashboard.agent")}:{" "}
          <span className={agentOnline ? "font-medium text-profit" : "text-slate-400"}>
            {agentOnline ? t("dashboard.online") : t("dashboard.offline")}
          </span>
        </p>
        <p className="mt-3 text-sm">
          <Link to="/agent/releases" className="text-brand-600 hover:underline">
            {t("dashboard.agentReleaseHistory")}
          </Link>
        </p>
      </div>
    </div>
  );
}

function DownloadButton({
  href,
  label,
  version,
  filename,
}: {
  href: string;
  label: string;
  version?: string;
  filename?: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      download={filename || undefined}
      className="btn-primary inline-flex items-center gap-2 py-2.5"
      title={filename || undefined}
    >
      <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 shrink-0" aria-hidden>
        <path d="M10 2.5a.75.75 0 01.75.75v7.69l2.22-2.22a.75.75 0 111.06 1.06l-3.5 3.5a.75.75 0 01-1.06 0l-3.5-3.5a.75.75 0 111.06-1.06l2.22 2.22V3.25A.75.75 0 0110 2.5z" />
        <path d="M3.5 13.25a.75.75 0 01.75.75v1.5A1.5 1.5 0 005.75 17h8.5a1.5 1.5 0 001.5-1.5v-1.5a.75.75 0 011.5 0v1.5a3 3 0 01-3 3h-8.5a3 3 0 01-3-3v-1.5a.75.75 0 01.75-.75z" />
      </svg>
      {label}
      {version ? <span className="text-xs font-normal opacity-80">v{version}</span> : null}
    </a>
  );
}
