import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { formatApiError } from "../lib/apiError";
import RichText from "./RichText";
import {
  isSchwabAutoCallbackUri,
  schwabAutoCallbackUrl,
} from "../pages/SchwabCallback";
import {
  alpacaEnvLabel,
  brokerDisplayName,
  isTigerPaperAccount,
  longbridgeEnvLabel,
  normalizeUsmartRegion,
  tigerEnvLabel,
  USMART_APPLY_URLS,
  usmartDisplayName,
  usmartEnvLabel,
  usmartRegionLabel,
  type CredentialLastProbe,
  type SavedCredential,
  type UsmartRegion,
} from "../lib/brokerCredentials";
import { formatEtDateTimeCompact } from "../lib/datetime";
import {
  buildTigerCredentialPayload,
  mergeTigerParsedFiles,
  parseTigerCredentialFile,
  tigerLicenseRequiresToken,
  type TigerParsedFile,
} from "../lib/tigerCredentials";
import {
  IBKR_PRESETS,
  ibkrPresetById,
  ibkrPresetLabel,
  type IbkrPresetId,
} from "../lib/ibkrPresets";
import {
  FUTU_PRESETS,
  futuPresetById,
  futuPresetLabel,
  type FutuPresetId,
} from "../lib/futuPresets";
import ConfirmDialog from "./ConfirmDialog";
import { BrokerLogo, type BrokerKey } from "./BrokerLogos";
import Toast from "./Toast";
import UiSelect from "./UiSelect";

const AGENT_BROKERS = new Set(["ibkr", "futu"]);
const BROKER_KEYS = new Set<BrokerKey>([
  "tiger",
  "longbridge",
  "schwab",
  "alpaca",
  "usmart",
  "ibkr",
  "ibkr_web",
  "futu",
]);

/** 本地网关官方下载 / 教程（IBKR TWS & 富途 OpenD 经 Agent 执行） */
const AGENT_SETUP_LINKS = {
  ibkr: {
    tws: "https://www.interactivebrokers.com/en/trading/download-tws.php?p=offline-stable",
    guide: "https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/",
  },
  futu: {
    opend: "https://www.futunn.com/download/OpenAPI",
    guide: "https://openapi.futunn.com/futu-api-doc/opend/opend-intro.html",
  },
} as const;

function brokerKey(value: string): BrokerKey | null {
  const key = value.toLowerCase() as BrokerKey;
  return BROKER_KEYS.has(key) ? key : null;
}

type AgentVersionPayload = {
  download_url?: string;
  platforms?: {
    macos?: { download_url?: string };
    windows?: { download_url?: string };
  };
};

function preferAgentDownloadUrl(version: AgentVersionPayload | null): string {
  const mac = version?.platforms?.macos?.download_url?.trim() || "";
  const win = version?.platforms?.windows?.download_url?.trim() || "";
  const legacy = version?.download_url?.trim() || "";
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const isWin = /Windows/i.test(ua);
  if (isWin) return win || mac || legacy;
  return mac || win || legacy;
}

function IbkrTwsConfigDialog({
  open,
  onClose,
  twsDownloadHref,
}: {
  open: boolean;
  onClose: () => void;
  twsDownloadHref: string;
}) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  const steps = [
    {
      title: t("dashboard.ibkrTwsConfigStep1Title"),
      desc: t("dashboard.ibkrTwsConfigStep1Desc"),
      src: "/guides/ibkr-tws-api-settings.png",
      alt: t("dashboard.ibkrTwsConfigStep1Title"),
    },
    {
      title: t("dashboard.ibkrTwsConfigStep2Title"),
      desc: t("dashboard.ibkrTwsConfigStep2Desc"),
      src: "/guides/ibkr-tws-api-precautions.png",
      alt: t("dashboard.ibkrTwsConfigStep2Title"),
    },
  ] as const;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/40" aria-label={t("common.close")} onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="ibkr-tws-config-title"
        className="relative z-[1] flex max-h-[92vh] w-full max-w-2xl flex-col rounded-t-2xl border border-slate-200 bg-white shadow-xl sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
          <h3 id="ibkr-tws-config-title" className="text-sm font-semibold text-slate-900">
            {t("dashboard.ibkrImportantTipTitle")}
          </h3>
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            onClick={onClose}
          >
            {t("common.close")}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5">
          <p className="text-xs leading-relaxed text-amber-800">{t("dashboard.ibkrImportantTipIntro")}</p>
          <div className="mt-3 space-y-4">
            {steps.map((step) => (
              <section key={step.src} className="space-y-2">
                <h4 className="text-xs font-semibold text-slate-900">{step.title}</h4>
                <RichText
                  className="text-[11px] leading-relaxed text-slate-600"
                  strongClassName="font-semibold text-slate-800"
                  text={step.desc}
                />
                <a
                  href={step.src}
                  target="_blank"
                  rel="noreferrer"
                  className="block overflow-hidden rounded-xl border border-slate-200 bg-slate-50"
                >
                  <img src={step.src} alt={step.alt} className="w-full object-contain object-top" loading="lazy" />
                </a>
              </section>
            ))}
          </div>
          <RichText
            className="mt-4 text-[11px] leading-relaxed text-slate-500"
            strongClassName="font-semibold text-amber-800"
            text={t("dashboard.ibkrTwsConfigAfterClose")}
          />
        </div>
        <div className="flex flex-col gap-2 border-t border-slate-100 px-4 py-3 sm:flex-row sm:px-5">
          <a
            href={twsDownloadHref}
            target="_blank"
            rel="noreferrer"
            className="btn-primary inline-flex w-full items-center justify-center text-sm sm:flex-1"
          >
            {t("dashboard.ibkrTwsConfigDownload")} ↗
          </a>
          <button type="button" className="btn-secondary w-full text-sm sm:flex-1" onClick={onClose}>
            {t("dashboard.ibkrImportantTipGotIt")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function AgentLocalSetupLinks({
  broker,
  compact = false,
}: {
  broker: string;
  /** 卡片内一行展示；弹窗内可带简短说明 */
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const key = broker.toLowerCase();
  const [agentVersion, setAgentVersion] = useState<AgentVersionPayload | null>(null);
  const [tipOpen, setTipOpen] = useState(false);

  useEffect(() => {
    api.get("/public/agent-version").then((r) => setAgentVersion(r.data)).catch(() => {});
  }, []);

  const linkClass =
    "font-medium text-brand-700 underline underline-offset-2 hover:text-brand-800";
  const mutedLinkClass =
    "font-medium text-slate-600 underline underline-offset-2 hover:text-slate-800";
  const tipBtnClass =
    "font-semibold text-amber-700 underline underline-offset-2 hover:text-amber-800";
  const agentUrl = preferAgentDownloadUrl(agentVersion);

  let gatewayHref = "";
  let gatewayLabel = "";
  let guideHref = "";
  let guideLabel = "";
  let hint = "";
  if (key === "ibkr") {
    hint = t("dashboard.ibkrLocalSetupHint");
    gatewayHref = AGENT_SETUP_LINKS.ibkr.tws;
    gatewayLabel = t("dashboard.downloadIbTws");
    guideHref = AGENT_SETUP_LINKS.ibkr.guide;
    guideLabel = t("dashboard.ibkrApiGuide");
  } else if (key === "futu") {
    hint = t("dashboard.futuLocalSetupHint");
    gatewayHref = AGENT_SETUP_LINKS.futu.opend;
    gatewayLabel = t("dashboard.downloadFutuOpend");
    guideHref = AGENT_SETUP_LINKS.futu.guide;
    guideLabel = t("dashboard.futuOpendGuide");
  } else {
    return null;
  }

  const tipControl =
    key === "ibkr" ? (
      <button type="button" className={tipBtnClass} onClick={() => setTipOpen(true)}>
        {t("dashboard.ibkrImportantTip")}
      </button>
    ) : null;

  const tipDialog =
    key === "ibkr" ? (
      <IbkrTwsConfigDialog open={tipOpen} onClose={() => setTipOpen(false)} twsDownloadHref={gatewayHref} />
    ) : null;

  const step1 = agentUrl ? (
    <a href={agentUrl} target="_blank" rel="noreferrer" className={linkClass}>
      {t("dashboard.agentLocalSetupStep1")} ↗
    </a>
  ) : (
    <span className="text-slate-400" title={t("dashboard.agentDownloadUnavailable")}>
      {t("dashboard.agentLocalSetupStep1")}
    </span>
  );
  const step2 =
    key === "ibkr" ? (
      <button type="button" className={linkClass} onClick={() => setTipOpen(true)}>
        {t("dashboard.agentLocalSetupStep2Ibkr")}
      </button>
    ) : (
      <a href={gatewayHref} target="_blank" rel="noreferrer" className={linkClass}>
        {t("dashboard.agentLocalSetupStep2Futu")} ↗
      </a>
    );
  const guide = (
    <a href={guideHref} target="_blank" rel="noreferrer" className={mutedLinkClass}>
      {guideLabel} ↗
    </a>
  );

  if (compact) {
    const chip =
      "inline-flex items-center rounded-md bg-white/80 px-2 py-1 text-[11px] font-medium text-brand-700 ring-1 ring-slate-200/80 hover:bg-brand-50";
    const mutedChip =
      "inline-flex items-center rounded-md bg-white/80 px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200/80 hover:bg-slate-50";
    const tipChip =
      "inline-flex items-center rounded-md bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200/90 hover:bg-amber-100";
    return (
      <>
        {/* 手机：小标签 */}
        <div className="flex flex-wrap gap-1.5 pt-0.5 md:hidden">
          {agentUrl ? (
            <a href={agentUrl} target="_blank" rel="noreferrer" className={chip}>
              {t("dashboard.agentLocalSetupStep1")}
            </a>
          ) : (
            <span className={`${mutedChip} opacity-50`} title={t("dashboard.agentDownloadUnavailable")}>
              {t("dashboard.agentLocalSetupStep1")}
            </span>
          )}
          {key === "ibkr" ? (
            <button type="button" className={chip} onClick={() => setTipOpen(true)}>
              {t("dashboard.agentLocalSetupStep2Ibkr")}
            </button>
          ) : (
            <a href={gatewayHref} target="_blank" rel="noreferrer" className={chip}>
              {t("dashboard.agentLocalSetupStep2Futu")}
            </a>
          )}
          <a href={guideHref} target="_blank" rel="noreferrer" className={mutedChip}>
            {guideLabel}
          </a>
          {key === "ibkr" ? (
            <button type="button" className={tipChip} onClick={() => setTipOpen(true)}>
              {t("dashboard.ibkrImportantTip")}
            </button>
          ) : null}
        </div>
        {/* PC：原先一行链接 */}
        <div className="hidden flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-slate-500 md:flex">
          <span className="font-medium text-slate-600">{t("dashboard.agentLocalSetupTitle")}</span>
          <span className="text-slate-300" aria-hidden>
            ·
          </span>
          {step1}
          <span className="text-slate-300" aria-hidden>
            →
          </span>
          {step2}
          <span className="text-slate-300" aria-hidden>
            ·
          </span>
          {guide}
          {tipControl ? (
            <>
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
              {tipControl}
            </>
          ) : null}
        </div>
        {tipDialog}
      </>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/90 px-3 py-2.5 text-xs leading-relaxed text-slate-700">
      <p className="font-medium text-slate-800">{t("dashboard.agentLocalSetupTitle")}</p>
      <p className="mt-1 text-slate-600">{hint}</p>
      <ol className="mt-2 list-decimal space-y-1 pl-4 text-slate-700">
        <li>{step1}</li>
        <li>
          {step2}
          <span className="mx-1.5 text-slate-300" aria-hidden>
            ·
          </span>
          {guide}
          {tipControl ? (
            <>
              <span className="mx-1.5 text-slate-300" aria-hidden>
                ·
              </span>
              {tipControl}
            </>
          ) : null}
        </li>
      </ol>
      {tipDialog}
    </div>
  );
}

type Binding = {
  id: string;
  broker: string;
  label: string;
  account_id: string;
  device_id?: string;
  enabled: boolean;
  /** 上次「测试账户」持久化结果 */
  last_probe?: CredentialLastProbe | null;
};

type AddBrokerKind =
  | "tiger"
  | "longbridge"
  | "schwab"
  | "alpaca"
  | "usmart"
  | "ibkr"
  | "ibkr_web"
  | "futu";

function isProductionEnv(env: string): boolean {
  const key = (env || "").toLowerCase();
  return ["production", "prod", "live", "online"].includes(key);
}

function ModeTagBadge({ paper }: { paper: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${
        paper
          ? "bg-amber-50 text-amber-800 ring-amber-200"
          : "bg-emerald-50 text-emerald-700 ring-emerald-200"
      }`}
    >
      {paper ? t("dashboard.envSimTag") : t("dashboard.envLiveTag")}
    </span>
  );
}

function EnvBadge({
  env,
  broker,
  accountId,
}: {
  env: string;
  broker: string;
  accountId?: string;
}) {
  const { t } = useTranslation();
  const brokerKey = broker.toLowerCase();

  if (brokerKey === "ibkr") {
    const preset = ibkrPresetById(accountId);
    return <ModeTagBadge paper={preset?.paper ?? true} />;
  }
  if (brokerKey === "futu") {
    const preset = futuPresetById(accountId);
    return <ModeTagBadge paper={preset?.paper ?? true} />;
  }

  const label =
    brokerKey === "alpaca" || brokerKey === "ibkr_web"
      ? alpacaEnvLabel(env, t)
      : brokerKey === "longbridge"
      ? longbridgeEnvLabel(env, t)
      : brokerKey === "usmart"
        ? usmartEnvLabel(env, t)
      : brokerKey === "schwab"
        ? t("dashboard.envLive")
      : tigerEnvLabel(env, t, accountId);
  const prod =
    brokerKey === "tiger"
      ? accountId
        ? !isTigerPaperAccount(accountId)
        : isProductionEnv(env)
      : brokerKey === "usmart"
        ? (env || "live").toLowerCase() !== "uat"
      : isProductionEnv(env);

  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${
        prod
          ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
          : "bg-amber-50 text-amber-800 ring-amber-200"
      }`}
    >
      {label}
    </span>
  );
}

function CredentialEncryptionNotice({ className = "" }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <div className={`rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 ${className}`}>
      <p className="font-semibold">{t("dashboard.credentialEncryptionTitle")}</p>
      <RichText
        text={t("dashboard.credentialEncryptionBody")}
        className="mt-1 text-xs leading-relaxed text-emerald-800"
        strongClassName="font-semibold text-emerald-950"
      />
    </div>
  );
}

function BrokerAddModal({
  open,
  title,
  closeLabel,
  busy,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  closeLabel: string;
  busy: boolean;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={closeLabel}
        disabled={busy}
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-xl sm:rounded-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button
            type="button"
            className="text-sm text-slate-500 hover:text-slate-700 disabled:opacity-50"
            disabled={busy}
            onClick={onClose}
          >
            {closeLabel}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-slate-50/80 px-5 py-3">
          {footer}
        </div>
      </div>
    </div>
  );
}

type AccountTestState = {
  status: "idle" | "testing" | "ok" | "fail";
  summary?: {
    account_id?: string | null;
    net_liquidation?: number | null;
    available_cash?: number | null;
    currency?: string | null;
  } | null;
  error?: string | null;
  tested_at?: string | null;
};

function formatMoney(n?: number | null, currency?: string | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const cur = (currency || "USD").toUpperCase();
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: cur,
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `${n.toFixed(2)} ${cur}`;
  }
}

/** 兼容历史探测文案（曾含 IB Gateway）；IBKR 仅提示 TWS。 */
function formatBrokerProbeError(broker: string, error?: string | null): string {
  if (!error) return "";
  const key = broker.toLowerCase();
  let text = error
    .replace(/IB Gateway\s*\/\s*TWS\s*\/\s*OpenD/gi, key === "futu" ? "OpenD" : "TWS")
    .replace(/IB Gateway\s*\/\s*TWS/gi, "TWS")
    .replace(/IB Gateway/gi, "TWS")
    .replace(/请启动 TWS\s*\/\s*OpenD/g, key === "futu" ? "请启动 OpenD" : "请启动 TWS")
    .replace(/请启动 OpenD\s*\/\s*TWS/g, key === "futu" ? "请启动 OpenD" : "请启动 TWS");
  return text;
}

function AccountCard({
  broker,
  title,
  envBadge,
  statusBadge,
  details,
  region,
  testState,
  onTest,
  onAuthorize,
  authorizeLabel,
  onEdit,
  onDelete,
  canDelete,
  busy,
}: {
  broker: string;
  title: string;
  envBadge?: React.ReactNode;
  statusBadge?: React.ReactNode;
  details: { label: string; value: string }[];
  region?: string;
  testState?: AccountTestState;
  onTest?: () => void;
  onAuthorize?: () => void;
  authorizeLabel?: string;
  onEdit?: () => void;
  onDelete?: () => void;
  canDelete?: boolean;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const logoKey = brokerKey(broker);
  const tone =
    testState?.status === "ok"
      ? "border-emerald-300 bg-emerald-50/70 hover:border-emerald-400"
      : testState?.status === "fail"
        ? "border-rose-300 bg-rose-50/70 hover:border-rose-400"
        : testState?.status === "testing"
          ? "border-amber-300 bg-amber-50/50 hover:border-amber-400"
          : "border-slate-200 bg-white hover:border-brand-200 hover:bg-brand-50/20";

  const mobileActionBtn =
    "inline-flex min-h-0 items-center justify-center rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";

  const statusOk =
    testState?.status === "ok" ? (
      <span className="inline-flex shrink-0 items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 ring-1 ring-emerald-200">
        {t("dashboard.accountTestOk")}
      </span>
    ) : null;
  const statusFail =
    testState?.status === "fail" ? (
      <span className="inline-flex shrink-0 items-center rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-800 ring-1 ring-rose-200">
        {t("dashboard.accountTestFail")}
      </span>
    ) : null;

  const regionBadges = (
    <>
      {logoKey === "usmart" ? (
        <span className="inline-flex items-center rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 ring-1 ring-rose-200">
          {usmartRegionLabel(region, t)}
        </span>
      ) : null}
      {logoKey === "futu" ? (
        <span className="inline-flex items-center rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 ring-1 ring-rose-200">
          {t("dashboard.regionHongKong")}
        </span>
      ) : null}
    </>
  );

  const actionsDesktop = (
    <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
      {onAuthorize ? (
        <button
          type="button"
          className="btn-primary min-h-0 px-3 py-1.5 text-xs font-medium"
          disabled={busy}
          onClick={onAuthorize}
        >
          {authorizeLabel || t("dashboard.schwabAuthorize")}
        </button>
      ) : null}
      {onTest ? (
        <button
          type="button"
          className="btn-secondary min-h-0 px-3 py-1.5 text-xs font-medium"
          disabled={busy || testState?.status === "testing"}
          onClick={onTest}
        >
          {testState?.status === "testing" ? t("dashboard.accountTesting") : t("dashboard.testAccount")}
        </button>
      ) : null}
      {onEdit ? (
        <button
          type="button"
          className="btn-secondary min-h-0 px-3 py-1.5 text-xs font-medium"
          disabled={busy}
          onClick={onEdit}
        >
          {t("dashboard.editCredential")}
        </button>
      ) : null}
      {canDelete && onDelete ? (
        <button
          type="button"
          className="inline-flex min-h-0 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 transition-colors hover:border-rose-300 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={busy}
          onClick={onDelete}
        >
          {t("dashboard.deleteCredential")}
        </button>
      ) : null}
    </div>
  );

  const actionsMobile = (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {onAuthorize ? (
        <button
          type="button"
          className={`${mobileActionBtn} bg-brand-500 text-white hover:bg-brand-600`}
          disabled={busy}
          onClick={onAuthorize}
        >
          {authorizeLabel || t("dashboard.schwabAuthorize")}
        </button>
      ) : null}
      {onTest ? (
        <button
          type="button"
          className={`${mobileActionBtn} border border-slate-300 bg-white text-slate-700 hover:border-brand-300 hover:bg-brand-50`}
          disabled={busy || testState?.status === "testing"}
          onClick={onTest}
        >
          {testState?.status === "testing" ? t("dashboard.accountTesting") : t("dashboard.testAccount")}
        </button>
      ) : null}
      {onEdit ? (
        <button
          type="button"
          className={`${mobileActionBtn} border border-slate-300 bg-white text-slate-700 hover:border-brand-300 hover:bg-brand-50`}
          disabled={busy}
          onClick={onEdit}
        >
          {t("dashboard.editCredential")}
        </button>
      ) : null}
      {canDelete && onDelete ? (
        <button
          type="button"
          className={`${mobileActionBtn} border border-rose-200 bg-rose-50 text-rose-700 hover:border-rose-300 hover:bg-rose-100`}
          disabled={busy}
          onClick={onDelete}
        >
          {t("dashboard.deleteCredential")}
        </button>
      ) : null}
    </div>
  );

  return (
    <li className={`rounded-2xl border px-3 py-3 transition-colors md:px-4 md:py-4 ${tone}`}>
      {/* —— 手机紧凑布局 —— */}
      <div className="md:hidden">
        <div className="flex items-start gap-2.5">
          {logoKey ? (
            <BrokerLogo
              broker={logoKey}
              framed
              className={logoKey === "longbridge" ? "mt-0.5 h-6 w-6 object-contain" : "mt-0.5 h-5 max-w-[4.5rem] object-contain"}
            />
          ) : null}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-sm font-semibold text-slate-900">{title}</span>
              {envBadge}
              {statusBadge}
              {statusOk}
              {statusFail}
            </div>
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
              <span>
                {logoKey === "usmart" ? usmartDisplayName(region, t) : brokerDisplayName(broker, t)}
              </span>
              {regionBadges}
              {details.map((row) => (
                <span key={row.label} className="text-slate-400">
                  · {row.label}{" "}
                  <span className="font-mono text-slate-600">{row.value}</span>
                </span>
              ))}
            </p>
          </div>
        </div>
        {actionsMobile}
        {testState?.status === "ok" && testState.summary ? (
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            <div className="rounded-lg border border-emerald-200 bg-emerald-100/80 px-2 py-1.5">
              <p className="text-[10px] font-medium text-emerald-600">{t("dashboard.accountTestEquity")}</p>
              <p className="mt-0.5 truncate font-mono text-xs font-semibold tabular-nums text-emerald-900">
                {formatMoney(testState.summary.net_liquidation, testState.summary.currency)}
              </p>
            </div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-100/80 px-2 py-1.5">
              <p className="text-[10px] font-medium text-emerald-600">{t("dashboard.accountTestCash")}</p>
              <p className="mt-0.5 truncate font-mono text-xs font-semibold tabular-nums text-emerald-900">
                {formatMoney(testState.summary.available_cash, testState.summary.currency)}
              </p>
            </div>
          </div>
        ) : null}
        {testState?.status === "fail" && testState.error ? (
          <p className="mt-2 text-xs leading-snug text-rose-700">{formatBrokerProbeError(broker, testState.error)}</p>
        ) : null}
        {testState?.tested_at && (testState.status === "ok" || testState.status === "fail") ? (
          <p className="mt-1.5 text-[11px] text-slate-500">
            {t("dashboard.accountTestLastAt", { time: formatEtDateTimeCompact(testState.tested_at) })}
          </p>
        ) : null}
        {AGENT_BROKERS.has(broker.toLowerCase()) ? (
          <div className="mt-2 border-t border-black/5 pt-2">
            <AgentLocalSetupLinks broker={broker} compact />
          </div>
        ) : null}
      </div>

      {/* —— PC：原先左右布局 —— */}
      <div className="hidden flex-wrap items-start justify-between gap-3 md:flex">
        <div className="flex min-w-0 flex-1 gap-3">
          {logoKey ? (
            <BrokerLogo
              broker={logoKey}
              framed
              className={logoKey === "longbridge" ? "h-6 w-6 object-contain" : "h-5 max-w-[5.5rem] object-contain"}
            />
          ) : null}
          <div className="min-w-0 flex-1 space-y-2">
            <p className="flex flex-wrap items-center gap-1.5 text-xs font-medium text-slate-500">
              <span>
                {logoKey === "usmart" ? usmartDisplayName(region, t) : brokerDisplayName(broker, t)}
              </span>
              {regionBadges}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-900">{title}</span>
              {envBadge}
              {statusBadge}
              {statusOk}
              {statusFail}
            </div>
            {details.length > 0 ? (
              <div className="grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
                {details.map((row) => (
                  <span key={row.label}>
                    {row.label}: <span className="font-mono text-slate-800">{row.value}</span>
                  </span>
                ))}
              </div>
            ) : null}
            {testState?.status === "ok" && testState.summary ? (
              <div className="flex flex-wrap gap-2 pt-0.5">
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-100/90 px-2.5 py-1 text-xs font-semibold text-emerald-900 shadow-sm">
                  <span className="text-[10px] font-medium uppercase tracking-wide text-emerald-600">
                    {t("dashboard.accountTestEquity")}
                  </span>
                  <span className="font-mono tabular-nums">
                    {formatMoney(testState.summary.net_liquidation, testState.summary.currency)}
                  </span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-100/90 px-2.5 py-1 text-xs font-semibold text-emerald-900 shadow-sm">
                  <span className="text-[10px] font-medium uppercase tracking-wide text-emerald-600">
                    {t("dashboard.accountTestCash")}
                  </span>
                  <span className="font-mono tabular-nums">
                    {formatMoney(testState.summary.available_cash, testState.summary.currency)}
                  </span>
                </span>
              </div>
            ) : null}
            {testState?.status === "fail" && testState.error ? (
              <p className="text-xs text-rose-700">{formatBrokerProbeError(broker, testState.error)}</p>
            ) : null}
            {testState?.tested_at && (testState.status === "ok" || testState.status === "fail") ? (
              <p className="text-[11px] text-slate-500">
                {t("dashboard.accountTestLastAt", { time: formatEtDateTimeCompact(testState.tested_at) })}
              </p>
            ) : null}
            {AGENT_BROKERS.has(broker.toLowerCase()) ? (
              <AgentLocalSetupLinks broker={broker} compact />
            ) : null}
          </div>
        </div>
        {actionsDesktop}
      </div>
    </li>
  );
}

export default function BrokerConfigSection({ onSaved }: { onSaved?: () => void }) {
  const { t, i18n } = useTranslation();
  const tigerFileRef = useRef<HTMLInputElement>(null);
  const [addKind, setAddKind] = useState<AddBrokerKind>("tiger");
  const [accountLabel, setAccountLabel] = useState("");
  const [accountId, setAccountId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [ibkrMode, setIbkrMode] = useState<IbkrPresetId>("tws-paper");
  /** IBKR 接入方式：TWS Agent vs Web API（下拉只显示一个 IBKR） */
  const [ibkrAccessMode, setIbkrAccessMode] = useState<"tws" | "web">("tws");
  const [futuMode, setFutuMode] = useState<FutuPresetId>("futu-simulate");
  const [tigerId, setTigerId] = useState("");
  const [tigerAccount, setTigerAccount] = useState("");
  const [tigerEnv, setTigerEnv] = useState<"paper" | "live">("paper");
  const [tigerFile, setTigerFile] = useState<TigerParsedFile | null>(null);
  const [tigerLicense, setTigerLicense] = useState("TBNZ");
  const [tigerToken, setTigerToken] = useState("");
  const [lbAccount, setLbAccount] = useState("");
  const [lbEnv, setLbEnv] = useState<"sandbox" | "live">("sandbox");
  const [lbAppKey, setLbAppKey] = useState("");
  const [lbAppSecret, setLbAppSecret] = useState("");
  const [lbAccessToken, setLbAccessToken] = useState("");
  const [schwabClientId, setSchwabClientId] = useState("");
  const [schwabClientSecret, setSchwabClientSecret] = useState("");
  const [schwabRedirectUri, setSchwabRedirectUri] = useState("");
  const [schwabAuthCredId, setSchwabAuthCredId] = useState<string | null>(null);
  const [schwabAuthUrl, setSchwabAuthUrl] = useState("");
  const [schwabRedirectedUrl, setSchwabRedirectedUrl] = useState("");
  const schwabAutoSubmitRef = useRef("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [alpacaAccount, setAlpacaAccount] = useState("");
  const [alpacaEnv, setAlpacaEnv] = useState<"paper" | "live">("paper");
  const [alpacaApiKey, setAlpacaApiKey] = useState("");
  const [alpacaApiSecret, setAlpacaApiSecret] = useState("");
  const [ibkrWebAccount, setIbkrWebAccount] = useState("");
  const [ibkrWebEnv, setIbkrWebEnv] = useState<"paper" | "live">("paper");
  const [ibkrWebConsumerKey, setIbkrWebConsumerKey] = useState("");
  const [ibkrWebAccessToken, setIbkrWebAccessToken] = useState("");
  const [ibkrWebAccessTokenSecret, setIbkrWebAccessTokenSecret] = useState("");
  const [ibkrWebSignatureKey, setIbkrWebSignatureKey] = useState("");
  const [ibkrWebEncryptionKey, setIbkrWebEncryptionKey] = useState("");
  const [ibkrWebDhPrime, setIbkrWebDhPrime] = useState("");
  const [ibkrWebGenBusy, setIbkrWebGenBusy] = useState(false);
  const [usmartEnv, setUsmartEnv] = useState<"live" | "uat">("live");
  const [usmartRegion, setUsmartRegion] = useState<UsmartRegion>("hk");
  const [usmartChannel, setUsmartChannel] = useState("");
  const [usmartPublicKey, setUsmartPublicKey] = useState("");
  const [usmartPrivateKey, setUsmartPrivateKey] = useState("");
  const [toast, setToast] = useState<{ message: string; variant: "success" | "error" } | null>(
    null,
  );
  const showToast = (message: string, variant: "success" | "error" = "success") => {
    setToast({ message, variant });
  };
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [credentials, setCredentials] = useState<SavedCredential[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingCredId, setEditingCredId] = useState<string | null>(null);
  const [editingBindingId, setEditingBindingId] = useState<string | null>(null);
  const [testStates, setTestStates] = useState<Record<string, AccountTestState>>({});
  const [deleteTarget, setDeleteTarget] = useState<{
    kind: "credential" | "binding";
    id: string;
    label: string;
  } | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const loadBindings = () => {
    api
      .get("/broker-bindings")
      .then((r) => {
        const rows = (r.data || []) as Binding[];
        setBindings(rows);
        setTestStates((prev) => {
          const next = { ...prev };
          for (const binding of rows) {
            const key = `bind-${binding.id}`;
            if (prev[key]?.status === "testing") continue;
            const probe = binding.last_probe;
            if (!probe) continue;
            next[key] = {
              status: probe.ok ? "ok" : "fail",
              summary: probe.account_summary ?? null,
              error: probe.error ?? null,
              tested_at: probe.tested_at ?? null,
            };
          }
          return next;
        });
      })
      .catch(() => {});
  };

  const loadCredentials = () => {
    api
      .get("/broker-credentials")
      .then((r) => {
        const rows = (r.data || []) as SavedCredential[];
        setCredentials(rows);
        setTestStates((prev) => {
          const next = { ...prev };
          for (const cred of rows) {
            if (prev[cred.id]?.status === "testing") continue;
            const probe = cred.last_probe;
            if (!probe) continue;
            next[cred.id] = {
              status: probe.ok ? "ok" : "fail",
              summary: probe.account_summary ?? null,
              error: probe.error ?? null,
              tested_at: probe.tested_at ?? null,
            };
          }
          return next;
        });
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadBindings();
    loadCredentials();
  }, []);

  useEffect(() => {
    if (!showAddForm || addKind !== "schwab") return;
    api
      .get("/schwab/oauth/redirect-uri")
      .then((r) => setSchwabRedirectUri(String(r.data?.redirect_uri || "")))
      .catch(() => setSchwabRedirectUri(""));
  }, [showAddForm, addKind]);

  // 从 /schwab/callback 带回的 paste 兜底，或授权成功提示
  useEffect(() => {
    const flag = searchParams.get("schwab");
    if (!flag) return;
    const next = new URLSearchParams(searchParams);
    next.delete("schwab");
    next.delete("reason");
    next.delete("hint");
    const redirected = searchParams.get("redirected");
    if (redirected) next.delete("redirected");
    setSearchParams(next, { replace: true });

    if (flag === "ok") {
      showToast(t("dashboard.schwabConnected"));
      loadCredentials();
      onSaved?.();
      return;
    }
    if (flag === "error") {
      setError(
        t("dashboard.schwabConnectFailed", {
          reason: searchParams.get("reason") || "",
        }),
      );
      return;
    }
    if (flag === "paste" && redirected) {
      const credId = sessionStorage.getItem("schwab_oauth_cred_id");
      setSchwabRedirectedUrl(redirected);
      if (credId) setSchwabAuthCredId(credId);
    }
  }, [searchParams, setSearchParams, t, onSaved]);

  const brokerKindOptions = useMemo(
    () => [
      { value: "tiger", label: t("dashboard.brokerTiger") },
      { value: "longbridge", label: t("dashboard.brokerLongbridge") },
      { value: "schwab", label: t("dashboard.brokerSchwab") },
      { value: "alpaca", label: "Alpaca" },
      { value: "usmart", label: t("dashboard.brokerUsmart") },
      { value: "ibkr", label: t("dashboard.brokerIbkr") },
      { value: "futu", label: t("dashboard.brokerFutu") },
    ],
    [t],
  );

  const ibkrFamilySelected = addKind === "ibkr" || addKind === "ibkr_web";

  const setBrokerKind = (value: string) => {
    if (value === "ibkr") {
      setAddKind(ibkrAccessMode === "web" ? "ibkr_web" : "ibkr");
      return;
    }
    setAddKind(value as AddBrokerKind);
  };

  const setIbkrAccess = (mode: "tws" | "web") => {
    setIbkrAccessMode(mode);
    setAddKind(mode === "web" ? "ibkr_web" : "ibkr");
  };

  const ibkrModeOptions = useMemo(
    () =>
      IBKR_PRESETS.map((p) => ({
        value: p.id,
        label: i18n.language?.toLowerCase().startsWith("en") ? p.labelEn : p.labelZh,
        tag: p.paper ? t("dashboard.envSimTag") : t("dashboard.envLiveTag"),
        tagTone: (p.paper ? "paper" : "live") as "paper" | "live",
      })),
    [i18n.language, t],
  );

  const futuModeOptions = useMemo(
    () =>
      FUTU_PRESETS.map((p) => ({
        value: p.id,
        label: i18n.language?.toLowerCase().startsWith("en") ? p.labelEn : p.labelZh,
        tag: p.paper ? t("dashboard.envSimTag") : t("dashboard.envLiveTag"),
        tagTone: (p.paper ? "paper" : "live") as "paper" | "live",
      })),
    [i18n.language, t],
  );

  const resetForms = () => {
    setAddKind("tiger");
    setAccountLabel("");
    setAccountId("");
    setDeviceId("");
    setIbkrMode("tws-paper");
    setIbkrAccessMode("tws");
    setFutuMode("futu-simulate");
    setTigerId("");
    setTigerAccount("");
    setTigerEnv("paper");
    setTigerFile(null);
    setTigerLicense("TBNZ");
    setTigerToken("");
    if (tigerFileRef.current) tigerFileRef.current.value = "";
    setLbAccount("");
    setLbEnv("sandbox");
    setLbAppKey("");
    setLbAppSecret("");
    setLbAccessToken("");
    setSchwabClientId("");
    setSchwabClientSecret("");
    setAlpacaAccount("");
    setAlpacaEnv("paper");
    setAlpacaApiKey("");
    setAlpacaApiSecret("");
    setIbkrWebAccount("");
    setIbkrWebEnv("paper");
    setIbkrWebConsumerKey("");
    setIbkrWebAccessToken("");
    setIbkrWebAccessTokenSecret("");
    setIbkrWebSignatureKey("");
    setIbkrWebEncryptionKey("");
    setIbkrWebDhPrime("");
    setUsmartEnv("live");
    setUsmartRegion("hk");
    setUsmartChannel("");
    setUsmartPublicKey("");
    setUsmartPrivateKey("");
    setEditingCredId(null);
    setEditingBindingId(null);
  };

  const runCredentialTest = async (credId: string): Promise<AccountTestState> => {
    setTestStates((prev) => ({ ...prev, [credId]: { status: "testing" } }));
    try {
      const { data } = await api.post(`/broker-credentials/${credId}/test`);
      const next: AccountTestState = data?.ok
        ? {
            status: "ok",
            summary: data.account_summary,
            error: null,
            tested_at: data.tested_at ?? null,
          }
        : {
            status: "fail",
            summary: data?.account_summary,
            error: data?.error || t("dashboard.accountTestFail"),
            tested_at: data?.tested_at ?? null,
          };
      setTestStates((prev) => ({ ...prev, [credId]: next }));
      return next;
    } catch (e) {
      const next: AccountTestState = { status: "fail", error: formatApiError(e, t) };
      setTestStates((prev) => ({ ...prev, [credId]: next }));
      return next;
    }
  };

  const runBindingTest = async (bindingId: string): Promise<AccountTestState> => {
    const key = `bind-${bindingId}`;
    setTestStates((prev) => ({ ...prev, [key]: { status: "testing" } }));
    setToast(null);
    try {
      const { data } = await api.post(`/broker-bindings/${bindingId}/test`);
      const next: AccountTestState = data?.ok
        ? {
            status: "ok",
            summary: data.account_summary,
            error: null,
            tested_at: data.tested_at ?? null,
          }
        : {
            status: "fail",
            summary: data?.account_summary,
            error: data?.error || t("dashboard.accountTestFail"),
            tested_at: data?.tested_at ?? null,
          };
      setTestStates((prev) => ({ ...prev, [key]: next }));
      showToast(
        data?.ok ? t("dashboard.accountTestOk") : next.error || t("dashboard.accountTestFail"),
        data?.ok ? "success" : "error",
      );
      return next;
    } catch (e) {
      const next: AccountTestState = { status: "fail", error: formatApiError(e, t) };
      setTestStates((prev) => ({ ...prev, [key]: next }));
      showToast(next.error || t("dashboard.accountTestFail"), "error");
      return next;
    }
  };

  const tigerEnvOptions = useMemo(
    () => [
      { value: "paper", label: t("dashboard.envTest") },
      { value: "live", label: t("dashboard.envProduction") },
    ],
    [t],
  );

  const lbEnvOptions = useMemo(
    () => [
      { value: "sandbox", label: t("dashboard.envSandbox") },
      { value: "live", label: t("dashboard.envLive") },
    ],
    [t],
  );

  const alpacaEnvOptions = useMemo(
    () => [
      { value: "paper", label: t("dashboard.envPaper") },
      { value: "live", label: t("dashboard.envLive") },
    ],
    [t],
  );

  const usmartEnvOptions = useMemo(
    () => [
      { value: "live", label: t("dashboard.envLive") },
      { value: "uat", label: t("dashboard.envUat") },
    ],
    [t],
  );

  const usmartRegionOptions = useMemo(
    () => [
      { value: "hk", label: t("dashboard.usmartRegionHk") },
      { value: "sg", label: t("dashboard.usmartRegionSg") },
    ],
    [t],
  );

  type AccountEntry =
    | { kind: "credential"; key: string; cred: SavedCredential }
    | { kind: "binding"; key: string; binding: Binding };

  const accountList = useMemo(() => {
    const entries: AccountEntry[] = [
      ...credentials.map((cred) => ({ kind: "credential" as const, key: `cred-${cred.id}`, cred })),
      ...bindings
        .filter((b) => AGENT_BROKERS.has(b.broker.toLowerCase()))
        .map((b) => ({
          kind: "binding" as const,
          key: `bind-${b.id}`,
          binding: b,
        })),
    ];
    return entries.sort((a, b) => {
      const brokerA = a.kind === "credential" ? a.cred.broker : a.binding.broker;
      const brokerB = b.kind === "credential" ? b.cred.broker : b.binding.broker;
      const titleA = a.kind === "credential" ? a.cred.label : a.binding.label;
      const titleB = b.kind === "credential" ? b.cred.label : b.binding.label;
      const ba = brokerDisplayName(brokerA, t);
      const bb = brokerDisplayName(brokerB, t);
      if (ba !== bb) return ba.localeCompare(bb);
      return titleA.localeCompare(titleB);
    });
  }, [bindings, credentials, t]);

  const credentialDetails = (cred: SavedCredential) => {
    const broker = cred.broker.toLowerCase();
    const details: { label: string; value: string }[] = [];
    if (broker === "tiger") {
      details.push(
        { label: "Tiger ID", value: cred.tiger_id || "—" },
        { label: t("dashboard.tigerAccountPlaceholder"), value: cred.account_id || "—" },
      );
      if (cred.license) details.push({ label: "License", value: cred.license });
      details.push({ label: t("dashboard.privateKeyMasked"), value: cred.key_hint });
      if (tigerLicenseRequiresToken(cred.license) || cred.token_hint) {
        details.push({
          label: t("dashboard.tigerTokenMasked"),
          value: cred.token_hint || t("dashboard.tigerTokenMissing"),
        });
      }
    } else if (broker === "longbridge") {
      details.push(
        { label: t("dashboard.lbAccountPlaceholder"), value: cred.account_id || "—" },
        { label: "App Key", value: cred.app_key_hint || "—" },
        { label: "App Secret", value: cred.app_secret_hint || "—" },
        { label: "Access Token", value: cred.access_token_hint || "—" },
      );
    } else if (broker === "schwab") {
      details.push(
        { label: t("dashboard.schwabAccount"), value: cred.account_id || "—" },
        { label: t("dashboard.schwabClientId"), value: cred.client_id_hint || "—" },
        {
          label: t("dashboard.schwabOAuthStatus"),
          value:
            cred.oauth_status === "authorized" || cred.refresh_token_hint
              ? t("dashboard.schwabOAuthAuthorized")
              : t("dashboard.schwabOAuthPending"),
        },
      );
    } else if (broker === "alpaca") {
      details.push(
        { label: t("dashboard.alpacaAccount"), value: cred.account_id || "—" },
        { label: "API Key", value: cred.api_key_hint || "—" },
        { label: "API Secret", value: cred.api_secret_hint || "—" },
      );
    } else if (broker === "ibkr_web") {
      details.push(
        { label: t("dashboard.ibkrWebAccount"), value: cred.account_id || "—" },
        { label: "Consumer Key", value: cred.consumer_key_hint || "—" },
        { label: "Access Token", value: cred.access_token_hint || "—" },
      );
    } else if (broker === "usmart") {
      details.push(
        { label: t("dashboard.usmartRegion"), value: usmartRegionLabel(cred.region, t) },
        { label: t("dashboard.usmartChannel"), value: cred.channel || "—" },
        { label: t("dashboard.usmartPublicKey"), value: cred.public_key_hint || "—" },
        { label: t("dashboard.usmartPrivateKey"), value: cred.private_key_hint || "—" },
      );
    }
    return details;
  };

  const validateLabel = () => {
    const label = accountLabel.trim();
    if (!label) {
      setError(t("dashboard.accountLabelRequired"));
      return null;
    }
    return label;
  };

  const closeAddModal = () => {
    if (busy) return;
    setShowAddForm(false);
    setError("");
    resetForms();
  };

  const openAddModal = () => {
    resetForms();
    setError("");
    setShowAddForm(true);
  };

  const openEditCredential = (cred: SavedCredential) => {
    resetForms();
    setError("");
    setEditingCredId(cred.id);
    setAddKind(cred.broker.toLowerCase() as AddBrokerKind);
    setAccountLabel(cred.label || "");
    const broker = cred.broker.toLowerCase();
    if (broker === "tiger") {
      setTigerId(cred.tiger_id || "");
      setTigerAccount(cred.account_id || "");
      setTigerLicense((cred.license || "TBNZ").toUpperCase());
      setTigerToken("");
      setTigerEnv(
        isTigerPaperAccount(cred.account_id) || !isProductionEnv(cred.env || "live")
          ? "paper"
          : "live",
      );
    } else if (broker === "longbridge") {
      setLbAccount(cred.account_id || "");
      setLbEnv(isProductionEnv(cred.env) ? "live" : "sandbox");
    } else if (broker === "schwab") {
      setSchwabRedirectUri(cred.oauth_redirect_uri || "https://127.0.0.1");
    } else if (broker === "alpaca") {
      setAlpacaAccount(cred.account_id || "");
      setAlpacaEnv(isProductionEnv(cred.env) ? "live" : "paper");
    } else if (broker === "ibkr_web") {
      setIbkrAccessMode("web");
      setIbkrWebAccount(cred.account_id || "");
      setIbkrWebEnv(isProductionEnv(cred.env) ? "live" : "paper");
    } else if (broker === "usmart") {
      const region = normalizeUsmartRegion(cred.region);
      setUsmartRegion(region);
      setUsmartChannel(cred.channel || "");
      setUsmartEnv((cred.env || "live").toLowerCase() === "uat" ? "uat" : "live");
    }
    setShowAddForm(true);
  };

  const openEditBinding = (binding: Binding) => {
    resetForms();
    setError("");
    setEditingBindingId(binding.id);
    setAddKind(binding.broker.toLowerCase() as AddBrokerKind);
    setAccountLabel(binding.label || "");
    setAccountId(binding.account_id || "");
    if (binding.broker.toLowerCase() === "ibkr") {
      setIbkrAccessMode("tws");
      const preset = ibkrPresetById(binding.account_id);
      setIbkrMode(preset?.id || "tws-paper");
    }
    if (binding.broker.toLowerCase() === "futu") {
      const preset = futuPresetById(binding.account_id);
      setFutuMode(preset?.id || "futu-simulate");
    }
    setShowAddForm(true);
  };

  const saveAccountEdit = async () => {
    const label = validateLabel();
    if (!label) return;
    // 老虎编辑时可重新上传配置 / 补 TBHK token（走 upsert，非仅改名）
    if (editingCredId && addKind === "tiger" && (tigerFile || tigerToken.trim())) {
      await saveTiger();
      return;
    }
    // closeAddModal 会清空 id，先留住以便保存后重跑账户探测
    const credId = editingCredId;
    const bindingId = editingBindingId;
    setBusy(true);
    setError("");
    setToast(null);
    try {
      if (credId) {
        // 老虎模拟/实盘由资金账号决定，编辑只改名称；长桥/Alpaca 可改 env 标识
        const body: { label: string; env?: string } = { label };
        if (addKind === "longbridge") body.env = lbEnv;
        else if (addKind === "alpaca") body.env = alpacaEnv;
        else if (addKind === "ibkr_web") body.env = ibkrWebEnv;
        else if (addKind === "usmart") body.env = usmartEnv;
        else if (addKind === "schwab") body.env = "live";
        await api.patch(`/broker-credentials/${credId}`, body);
      } else if (bindingId) {
        const bindingAccountId =
          addKind === "ibkr" ? ibkrMode : addKind === "futu" ? futuMode : accountId.trim();
        await api.patch(`/broker-bindings/${bindingId}`, {
          label,
          account_id: bindingAccountId,
        });
      }
      closeAddModal();
      loadCredentials();
      loadBindings();
      onSaved?.();
      // 保存后自动再测一次账户信息（净值/可用等）
      if (credId) {
        const result = await runCredentialTest(credId);
        showToast(
          result.status === "ok"
            ? t("dashboard.accountTestSavedOk")
            : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
          result.status === "ok" ? "success" : "error",
        );
      } else if (bindingId) {
        await runBindingTest(bindingId);
      } else {
        showToast(t("dashboard.accountUpdated"));
      }
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveBinding = async (e?: FormEvent) => {
    e?.preventDefault();
    const label = validateLabel();
    if (!label) return;
    if (addKind === "ibkr" && !ibkrMode) return;
    if (addKind === "futu" && !futuMode) return;
    if (addKind !== "ibkr" && addKind !== "futu" && !accountId.trim()) return;
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const bindingAccountId =
        addKind === "ibkr" ? ibkrMode : addKind === "futu" ? futuMode : accountId.trim();
      const { data } = await api.post("/broker-bindings", {
        broker: addKind,
        label,
        account_id: bindingAccountId,
        device_id: undefined,
      });
      const bindingId = data?.binding?.id as string | undefined;
      closeAddModal();
      loadBindings();
      onSaved?.();
      if (bindingId) {
        await runBindingTest(bindingId);
      } else {
        showToast(t("dashboard.brokerSaved"));
      }
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const handleTigerFile = async (file: File | null) => {
    if (!file) return;
    setError("");
    setToast(null);
    try {
      const content = await file.text();
      const parsed = parseTigerCredentialFile(file.name, content);
      let merged: TigerParsedFile = parsed;
      setTigerFile((prev) => {
        merged = mergeTigerParsedFiles(prev, parsed);
        return merged;
      });
      if (merged.tiger_id) setTigerId(merged.tiger_id);
      if (merged.account) setTigerAccount(merged.account);
      if (merged.license) setTigerLicense(merged.license.toUpperCase());
      if (merged.token) setTigerToken(merged.token);
      if (merged.account && isTigerPaperAccount(merged.account)) {
        setTigerEnv("paper");
      } else if (merged.env) {
        const prod = ["PROD", "PRODUCTION", "LIVE"].includes(merged.env.toUpperCase());
        setTigerEnv(prod ? "live" : "paper");
      }
    } catch (e) {
      if (!tigerFile) setTigerFile(null);
      setError(e instanceof Error ? e.message : t("dashboard.tigerFileInvalid"));
    }
  };

  const saveTiger = async () => {
    const label = validateLabel();
    if (!label) return;
    if (!tigerFile && !editingCredId) {
      setError(t("dashboard.tigerFileRequired"));
      return;
    }
    if (!tigerId.trim() || !tigerAccount.trim()) {
      setError(t("dashboard.tigerFileInvalid"));
      return;
    }
    const license = (tigerLicense || tigerFile?.license || "TBNZ").toUpperCase();
    const token = tigerToken.trim() || tigerFile?.token?.trim() || "";
    if (tigerLicenseRequiresToken(license) && !token && !editingCredId) {
      setError(t("dashboard.tigerTokenRequired"));
      return;
    }
    // 编辑补 token：无新私钥时也允许只提交 secrets
    if (editingCredId && !tigerFile?.private_key && !token && tigerLicenseRequiresToken(license)) {
      if (!editingCredential?.token_hint) {
        setError(t("dashboard.tigerTokenRequired"));
        return;
      }
    }
    setBusy(true);
    setError("");
    setToast(null);
    try {
      let body: Record<string, unknown>;
      if (tigerFile?.private_key) {
        const payload = buildTigerCredentialPayload(tigerFile, {
          tiger_id: tigerId,
          account_id: tigerAccount,
          env: tigerEnv,
          token,
          license,
        });
        body = {
          broker: "tiger",
          label,
          account_id: payload.account_id,
          env: tigerEnv,
          config: payload.config,
          private_key: payload.private_key,
          ...(payload.secrets ? { secrets: payload.secrets } : {}),
        };
      } else {
        const mode = isTigerPaperAccount(tigerAccount) ? "paper" : tigerEnv;
        body = {
          broker: "tiger",
          label,
          account_id: tigerAccount.trim(),
          env: mode,
          config: {
            env: mode,
            sandbox: false,
            license,
            tiger_id: tigerId.trim(),
            account: tigerAccount.trim(),
            production: { tiger_id: tigerId.trim(), account: tigerAccount.trim() },
          },
          ...(token ? { secrets: { token } } : {}),
        };
      }
      const { data } = await api.post("/broker-credentials", body);
      const credId = data?.credential?.id || editingCredId;
      closeAddModal();
      loadBindings();
      onSaved?.();
      if (credId) {
        const result = await runCredentialTest(credId);
        showToast(
          result.status === "ok"
            ? t("dashboard.accountTestSavedOk")
            : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
          result.status === "ok" ? "success" : "error",
        );
      } else {
        showToast(t("dashboard.tigerSaved"));
      }
      loadCredentials();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveLongbridge = async () => {
    const label = validateLabel();
    if (!label) return;
    const hasSecrets = Boolean(lbAppKey.trim() && lbAppSecret.trim() && lbAccessToken.trim());
    if (!hasSecrets && !editingCredId) {
      setError(t("dashboard.lbSecretsRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const account_id = lbAccount.trim() || `lb-${Date.now().toString(36)}`;
      const { data } = await api.post("/broker-credentials", {
        broker: "longbridge",
        label,
        account_id,
        env: lbEnv,
        ...(hasSecrets
          ? {
              secrets: {
                app_key: lbAppKey.trim(),
                app_secret: lbAppSecret.trim(),
                access_token: lbAccessToken.trim(),
              },
            }
          : {}),
      });
      const credId = data?.credential?.id || editingCredId;
      closeAddModal();
      loadBindings();
      onSaved?.();
      if (credId) {
        const result = await runCredentialTest(credId);
        showToast(
          result.status === "ok"
            ? t("dashboard.accountTestSavedOk")
            : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
          result.status === "ok" ? "success" : "error",
        );
      } else {
        showToast(t("dashboard.lbSaved"));
      }
      loadCredentials();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveSchwab = async () => {
    const label = validateLabel();
    if (!label) return;
    const hasSecrets = Boolean(schwabClientId.trim() && schwabClientSecret.trim());
    if (!hasSecrets && !editingCredId) {
      setError(t("dashboard.schwabSecretsRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const existingAccountId = editingCredId
        ? credentials.find((c) => c.id === editingCredId)?.account_id
        : undefined;
      const callback = (schwabRedirectUri || schwabAutoCallbackUrl()).trim().replace(/\/$/, "");
      const { data } = await api.post("/broker-credentials", {
        broker: "schwab",
        label,
        account_id: existingAccountId || `schwab-${Date.now().toString(36)}`,
        env: "live",
        config: { oauth_redirect_uri: callback },
        ...(hasSecrets
          ? {
              secrets: {
                client_id: schwabClientId.trim(),
                client_secret: schwabClientSecret.trim(),
              },
            }
          : {}),
      });
      setSchwabRedirectUri(callback);
      const credId = data?.credential?.id || editingCredId;
      closeAddModal();
      loadBindings();
      onSaved?.();
      // 先保存成功；测试失败不影响已保存结果
      if (credId) {
        const result = await runCredentialTest(credId);
        showToast(
          result.status === "ok"
            ? t("dashboard.accountTestSavedOk")
            : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
          result.status === "ok" ? "success" : "error",
        );
      } else {
        showToast(t("dashboard.schwabSaved"));
      }
      loadCredentials();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const startSchwabAuthorize = async (credId: string) => {
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const savedRedirect = credentials.find((c) => c.id === credId)?.oauth_redirect_uri;
      const redirect =
        (schwabRedirectUri || savedRedirect || schwabAutoCallbackUrl() || "https://127.0.0.1")
          .trim()
          .replace(/\/$/, "");
      const { data } = await api.post("/schwab/oauth/start", {
        cred_id: credId,
        redirect_uri: redirect,
      });
      const authorizeUrl = String(data?.authorize_url || "");
      const redirectUri = String(data?.redirect_uri || redirect || "");
      if (!authorizeUrl) {
        throw new Error(t("dashboard.schwabSecretsRequired"));
      }
      if (redirectUri) setSchwabRedirectUri(redirectUri);
      sessionStorage.setItem("schwab_oauth_cred_id", credId);
      schwabAutoSubmitRef.current = "";
      // 本站回调：同窗口跳转，授权后直接回到 /schwab/callback 自动换票
      if (isSchwabAutoCallbackUri(redirectUri)) {
        window.location.assign(authorizeUrl);
        return;
      }
      // https://127.0.0.1 等无法回到本站：弹窗 + 粘贴兜底
      setSchwabAuthCredId(credId);
      setSchwabAuthUrl(authorizeUrl);
      setSchwabRedirectedUrl("");
      window.open(authorizeUrl, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const completeSchwabAuthorize = async () => {
    if (!schwabAuthCredId || !schwabRedirectedUrl.trim()) return;
    const credId = schwabAuthCredId;
    const redirected = schwabRedirectedUrl.trim();
    setBusy(true);
    setError("");
    try {
      await api.post("/schwab/oauth/complete", {
        cred_id: credId,
        redirected_url: redirected,
      });
      sessionStorage.removeItem("schwab_oauth_cred_id");
      setSchwabAuthCredId(null);
      setSchwabAuthUrl("");
      setSchwabRedirectedUrl("");
      loadCredentials();
      onSaved?.();
      const result = await runCredentialTest(credId);
      showToast(
        result.status === "ok"
          ? t("dashboard.schwabConnected")
          : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
        result.status === "ok" ? "success" : "error",
      );
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  // 粘贴含 code= 的 URL 后自动提交（授权码很快过期）
  useEffect(() => {
    if (!schwabAuthCredId || busy) return;
    const url = schwabRedirectedUrl.trim();
    if (!/[?&]code=/.test(url)) return;
    if (schwabAutoSubmitRef.current === url) return;
    schwabAutoSubmitRef.current = url;
    void completeSchwabAuthorize();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when pasted URL changes
  }, [schwabRedirectedUrl, schwabAuthCredId, busy]);

  const saveAlpaca = async () => {
    const label = validateLabel();
    if (!label) return;
    const hasSecrets = Boolean(alpacaApiKey.trim() && alpacaApiSecret.trim());
    if (!hasSecrets && !editingCredId) {
      setError(t("dashboard.alpacaSecretsRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const { data } = await api.post("/broker-credentials", {
        broker: "alpaca",
        label,
        account_id: alpacaAccount.trim() || `alpaca-${Date.now().toString(36)}`,
        env: alpacaEnv,
        ...(hasSecrets
          ? {
              secrets: {
                api_key: alpacaApiKey.trim(),
                api_secret: alpacaApiSecret.trim(),
              },
            }
          : {}),
      });
      const credId = data?.credential?.id || editingCredId;
      closeAddModal();
      loadBindings();
      onSaved?.();
      if (credId) {
        const result = await runCredentialTest(credId);
        showToast(
          result.status === "ok"
            ? t("dashboard.accountTestSavedOk")
            : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
          result.status === "ok" ? "success" : "error",
        );
      } else {
        showToast(t("dashboard.alpacaSaved"));
      }
      loadCredentials();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const downloadTextFile = (filename: string, content: string) => {
    const blob = new Blob([content], { type: "application/x-pem-file;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const generateIbkrWebKeys = async () => {
    setIbkrWebGenBusy(true);
    setError("");
    setToast(null);
    try {
      const { data } = await api.post("/broker-credentials/ibkr-web/generate-keys");
      const sigPriv = String(data?.signature_key_pem || "");
      const encPriv = String(data?.encryption_key_pem || "");
      const dh = String(data?.dhparam_pem || "");
      const pubSig = String(data?.public_signature_pem || "");
      const pubEnc = String(data?.public_encryption_pem || "");
      if (!sigPriv || !encPriv || !dh || !pubSig || !pubEnc) {
        throw new Error("incomplete key material");
      }
      setIbkrWebSignatureKey(sigPriv);
      setIbkrWebEncryptionKey(encPriv);
      setIbkrWebDhPrime(dh);
      // 依次下载 IBKR 需上传的 3 个公钥/参数文件
      downloadTextFile("public_signature.pem", pubSig);
      await new Promise((r) => setTimeout(r, 250));
      downloadTextFile("public_encryption.pem", pubEnc);
      await new Promise((r) => setTimeout(r, 250));
      downloadTextFile("dhparam.pem", dh);
      showToast(t("dashboard.ibkrWebGenerateOk"), "success");
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setIbkrWebGenBusy(false);
    }
  };

  const saveIbkrWeb = async () => {
    const label = validateLabel();
    if (!label) return;
    const account = ibkrWebAccount.trim();
    if (!account) {
      setError(t("dashboard.ibkrWebAccountRequired"));
      return;
    }
    const hasSecrets = Boolean(
      ibkrWebConsumerKey.trim() &&
        ibkrWebAccessToken.trim() &&
        ibkrWebAccessTokenSecret.trim() &&
        ibkrWebSignatureKey.trim() &&
        ibkrWebEncryptionKey.trim() &&
        ibkrWebDhPrime.trim(),
    );
    if (!hasSecrets && !editingCredId) {
      setError(t("dashboard.ibkrWebSecretsRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const { data } = await api.post("/broker-credentials", {
        broker: "ibkr_web",
        label,
        account_id: account,
        env: ibkrWebEnv,
        config: { realm: "limited_poa" },
        ...(hasSecrets
          ? {
              secrets: {
                consumer_key: ibkrWebConsumerKey.trim(),
                access_token: ibkrWebAccessToken.trim(),
                access_token_secret: ibkrWebAccessTokenSecret.trim(),
                signature_key_pem: ibkrWebSignatureKey.trim(),
                encryption_key_pem: ibkrWebEncryptionKey.trim(),
                dh_prime: ibkrWebDhPrime.trim(),
              },
            }
          : {}),
      });
      const credId = data?.credential?.id || editingCredId;
      closeAddModal();
      loadBindings();
      onSaved?.();
      if (credId) {
        const result = await runCredentialTest(credId);
        showToast(
          result.status === "ok"
            ? t("dashboard.accountTestSavedOk")
            : t("dashboard.accountTestSavedFail", { error: result.error || "" }),
          result.status === "ok" ? "success" : "error",
        );
      } else {
        showToast(t("dashboard.ibkrWebSaved"));
      }
      loadCredentials();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveUsmart = async () => {
    const label = validateLabel();
    if (!label) return;
    const hasApiSecrets = Boolean(
      usmartChannel.trim() && usmartPublicKey.trim() && usmartPrivateKey.trim(),
    );
    if (!hasApiSecrets && !editingCredId) {
      setError(t("dashboard.usmartSecretsRequired"));
      return;
    }
    if (!usmartChannel.trim()) {
      setError(t("dashboard.usmartSecretsRequired"));
      return;
    }
    setBusy(true);
    setError("");
    setToast(null);
    try {
      const secrets: Record<string, string> = {};
      if (usmartPublicKey.trim()) secrets.public_key = usmartPublicKey.trim();
      if (usmartPrivateKey.trim()) secrets.private_key = usmartPrivateKey.trim();
      await api.post("/broker-credentials", {
        broker: "usmart",
        label,
        account_id: usmartChannel.trim() || `usmart-${Date.now().toString(36)}`,
        env: usmartEnv,
        config: {
          region: usmartRegion,
          channel: usmartChannel.trim(),
        },
        ...(Object.keys(secrets).length ? { secrets } : {}),
      });
      closeAddModal();
      loadBindings();
      onSaved?.();
      showToast(t("dashboard.usmartSaved"));
      loadCredentials();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  const confirmDeleteAccount = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setError("");
    try {
      if (deleteTarget.kind === "credential") {
        await api.delete(`/broker-credentials/${deleteTarget.id}`);
        loadCredentials();
        loadBindings();
      } else {
        await api.delete(`/broker-bindings/${deleteTarget.id}`);
        loadBindings();
      }
      showToast(t("dashboard.credentialDeleted"));
      setDeleteTarget(null);
      onSaved?.();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setDeleteBusy(false);
    }
  };

  const isAgent = addKind === "ibkr" || addKind === "futu";
  const isEditing = Boolean(editingCredId || editingBindingId);
  const editingCredential = editingCredId
    ? credentials.find((c) => c.id === editingCredId) || null
    : null;

  const canSaveModal =
    Boolean(accountLabel.trim()) &&
    !busy &&
    (isEditing
      ? addKind === "ibkr"
        ? Boolean(ibkrMode)
        : addKind === "futu"
          ? Boolean(futuMode)
          : true
      : addKind === "tiger"
        ? Boolean(tigerFile?.private_key) &&
          Boolean(tigerId.trim() && tigerAccount.trim()) &&
          (!tigerLicenseRequiresToken(tigerLicense || tigerFile?.license) ||
            Boolean(tigerToken.trim() || tigerFile?.token))
        : addKind === "longbridge"
          ? Boolean(lbAppKey.trim() && lbAppSecret.trim() && lbAccessToken.trim())
          : addKind === "schwab"
            ? Boolean(schwabClientId.trim() && schwabClientSecret.trim())
            : addKind === "alpaca"
              ? Boolean(alpacaApiKey.trim() && alpacaApiSecret.trim())
              : addKind === "ibkr_web"
                ? Boolean(
                    ibkrWebAccount.trim() &&
                      ibkrWebConsumerKey.trim() &&
                      ibkrWebAccessToken.trim() &&
                      ibkrWebAccessTokenSecret.trim() &&
                      ibkrWebSignatureKey.trim() &&
                      ibkrWebEncryptionKey.trim() &&
                      ibkrWebDhPrime.trim(),
                  )
              : addKind === "usmart"
                ? Boolean(
                    usmartChannel.trim() && usmartPublicKey.trim() && usmartPrivateKey.trim(),
                  )
              : addKind === "ibkr"
                ? Boolean(ibkrMode)
                : addKind === "futu"
                  ? Boolean(futuMode)
                  : Boolean(accountId.trim()));

  const handleModalSave = () => {
    if (isEditing) {
      void saveAccountEdit();
      return;
    }
    if (addKind === "tiger") void saveTiger();
    else if (addKind === "longbridge") void saveLongbridge();
    else if (addKind === "schwab") void saveSchwab();
    else if (addKind === "alpaca") void saveAlpaca();
    else if (addKind === "ibkr_web") void saveIbkrWeb();
    else if (addKind === "usmart") void saveUsmart();
    else void saveBinding();
  };

  return (
      <section className="card space-y-3 md:space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-2 md:gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold text-slate-900">{t("dashboard.brokers")}</h2>
            <p className="mt-0.5 text-xs text-slate-500 md:mt-1">{t("dashboard.brokersSubtitle")}</p>
            <CredentialEncryptionNotice className="mt-2 md:mt-3" />
          </div>
          <button type="button" className="btn-primary min-h-0 px-3 py-1.5 text-xs md:min-h-0 md:px-4 md:py-2 md:text-sm" onClick={openAddModal}>
            {t("dashboard.addAccount")}
          </button>
        </div>

        {accountList.length > 0 ? (
          <ul className="space-y-2">
            {accountList.map((item) =>
              item.kind === "credential" ? (
                <AccountCard
                  key={item.key}
                  broker={item.cred.broker}
                  title={item.cred.label}
                  region={item.cred.region}
                  envBadge={
                    <EnvBadge
                      env={item.cred.env}
                      broker={item.cred.broker.toLowerCase()}
                      accountId={item.cred.account_id}
                    />
                  }
                  details={credentialDetails(item.cred)}
                  testState={testStates[item.cred.id]}
                  canDelete
                  busy={busy}
                  onAuthorize={
                    item.cred.broker.toLowerCase() === "schwab"
                      ? () => void startSchwabAuthorize(item.cred.id)
                      : undefined
                  }
                  authorizeLabel={
                    item.cred.oauth_status === "authorized" || item.cred.refresh_token_hint
                      ? t("dashboard.schwabReauthorize")
                      : t("dashboard.schwabAuthorize")
                  }
                  onTest={() => {
                    void runCredentialTest(item.cred.id).then((result) => {
                      showToast(
                        result.status === "ok"
                          ? t("dashboard.accountTestOk")
                          : result.error || t("dashboard.accountTestFail"),
                        result.status === "ok" ? "success" : "error",
                      );
                    });
                  }}
                  onEdit={() => openEditCredential(item.cred)}
                  onDelete={() =>
                    setDeleteTarget({
                      kind: "credential",
                      id: item.cred.id,
                      label: item.cred.label || item.cred.broker,
                    })
                  }
                />
              ) : (
                <AccountCard
                  key={item.key}
                  broker={item.binding.broker}
                  title={item.binding.label}
                  envBadge={
                    <EnvBadge
                      env=""
                      broker={item.binding.broker}
                      accountId={item.binding.account_id}
                    />
                  }
                  statusBadge={
                    <span
                      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${
                        item.binding.enabled !== false
                          ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                          : "bg-slate-100 text-slate-500 ring-slate-200"
                      }`}
                    >
                      {item.binding.enabled !== false
                        ? t("dashboard.bindingEnabled")
                        : t("dashboard.bindingDisabled")}
                    </span>
                  }
                  details={[
                    {
                      label: t("dashboard.relayAgent"),
                      value:
                        item.binding.broker.toLowerCase() === "ibkr"
                          ? ibkrPresetLabel(item.binding.account_id, i18n.language)
                          : item.binding.broker.toLowerCase() === "futu"
                            ? futuPresetLabel(item.binding.account_id, i18n.language)
                            : t("dashboard.agentBindingViaAgent"),
                    },
                  ]}
                  testState={
                    testStates[`bind-${item.binding.id}`] || {
                      status: "idle",
                      error: undefined,
                    }
                  }
                  canDelete
                  busy={busy}
                  onTest={() => void runBindingTest(item.binding.id)}
                  onEdit={() => openEditBinding(item.binding)}
                  onDelete={() =>
                    setDeleteTarget({
                      kind: "binding",
                      id: item.binding.id,
                      label: item.binding.label || item.binding.broker,
                    })
                  }
                />
              ),
            )}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-xs text-slate-500">
            {t("dashboard.noAccountsYet")}
          </p>
        )}

        {!showAddForm && !schwabAuthCredId && error ? <p className="text-sm text-loss">{error}</p> : null}

        {toast ? (
          <Toast
            message={toast.message}
            variant={toast.variant}
            durationMs={toast.variant === "error" ? 4800 : 3200}
            onClose={() => setToast(null)}
          />
        ) : null}

        <BrokerAddModal
          open={Boolean(schwabAuthCredId)}
          title={t("dashboard.schwabAuthorizeTitle")}
          closeLabel={t("dashboard.cancelAdd")}
          busy={busy}
          onClose={() => {
            if (busy) return;
            setSchwabAuthCredId(null);
            setSchwabAuthUrl("");
            setSchwabRedirectedUrl("");
            setError("");
          }}
          footer={
            <>
              <button
                type="button"
                className="btn-secondary text-sm"
                disabled={busy || !schwabAuthUrl}
                onClick={() => schwabAuthUrl && window.open(schwabAuthUrl, "_blank", "noopener,noreferrer")}
              >
                {t("dashboard.schwabAuthorizeOpenAgain")}
              </button>
              <button
                type="button"
                className="btn-primary text-sm"
                disabled={busy || !schwabRedirectedUrl.trim()}
                onClick={() => void completeSchwabAuthorize()}
              >
                {busy ? t("execPipeline.saving") : t("dashboard.schwabAuthorizeSubmit")}
              </button>
            </>
          }
        >
          <div className="space-y-3 text-sm">
            <p className="text-slate-600">{t("dashboard.schwabAuthorizeStep1")}</p>
            <p className="text-slate-600">{t("dashboard.schwabAuthorizeStep2")}</p>
            <p className="text-xs text-amber-800 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
              {t("dashboard.schwabAuthorizeCodeTtl")}
            </p>
            {schwabRedirectUri ? (
              <p className="break-all rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 font-mono text-[11px] text-sky-950">
                <span className="mb-1 block font-sans text-[10px] font-semibold uppercase tracking-wide text-sky-700">
                  {t("dashboard.schwabCallbackUrl")}
                </span>
                {schwabRedirectUri}
              </p>
            ) : null}
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">{t("dashboard.schwabAuthorizePaste")}</span>
              <textarea
                className="textarea min-h-24 w-full"
                value={schwabRedirectedUrl}
                onChange={(e) => setSchwabRedirectedUrl(e.target.value)}
                placeholder="https://127.0.0.1/?code=...&session=..."
              />
            </label>
            {error ? <p className="text-sm text-loss break-all">{error}</p> : null}
          </div>
        </BrokerAddModal>

        <BrokerAddModal
          open={showAddForm}
          title={
            editingCredId || editingBindingId
              ? t("dashboard.editAccount")
              : t("dashboard.addAccount")
          }
          closeLabel={t("dashboard.cancelAdd")}
          busy={busy}
          onClose={closeAddModal}
          footer={
            <>
              <button type="button" className="btn-secondary text-sm" disabled={busy} onClick={closeAddModal}>
                {t("dashboard.cancelAdd")}
              </button>
              <button
                type="button"
                className="btn-primary text-sm"
                disabled={!canSaveModal}
                onClick={handleModalSave}
              >
                {busy ? t("execPipeline.saving") : t("dashboard.saveAccount")}
              </button>
            </>
          }
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-600">{t("dashboard.accountLabel")}</label>
              <input
                className="input"
                placeholder={t("dashboard.accountLabelPlaceholder")}
                value={accountLabel}
                onChange={(e) => setAccountLabel(e.target.value)}
                required
              />
              <p className="text-xs text-slate-500">
                {isEditing ? t("dashboard.editMetaHint") : t("dashboard.accountLabelHint")}
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-600">{t("dashboard.pickBrokerType")}</label>
              <UiSelect
                value={ibkrFamilySelected ? "ibkr" : addKind}
                onChange={setBrokerKind}
                options={brokerKindOptions}
                disabled={isEditing}
              />
              {ibkrFamilySelected ? (
                <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                  <p className="text-xs font-medium text-slate-600">{t("dashboard.ibkrAccessMode")}</p>
                  <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-4">
                    <label
                      className={`flex cursor-pointer items-start gap-2 text-xs text-slate-800 ${
                        isEditing ? "cursor-not-allowed opacity-70" : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name="ibkr-access-mode"
                        className="mt-0.5"
                        checked={addKind === "ibkr"}
                        disabled={isEditing}
                        onChange={() => setIbkrAccess("tws")}
                      />
                      <span>
                        <span className="font-medium">{t("dashboard.ibkrAccessTws")}</span>
                        <span className="mt-0.5 block text-slate-500">{t("dashboard.ibkrAccessTwsHint")}</span>
                      </span>
                    </label>
                    <label
                      className={`flex cursor-pointer items-start gap-2 text-xs text-slate-800 ${
                        isEditing ? "cursor-not-allowed opacity-70" : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name="ibkr-access-mode"
                        className="mt-0.5"
                        checked={addKind === "ibkr_web"}
                        disabled={isEditing}
                        onChange={() => setIbkrAccess("web")}
                      />
                      <span>
                        <span className="font-medium">{t("dashboard.ibkrAccessWeb")}</span>
                        <span className="mt-0.5 block text-slate-500">{t("dashboard.ibkrAccessWebHint")}</span>
                      </span>
                    </label>
                  </div>
                </div>
              ) : null}
              {isEditing ? (
                <p className="text-xs text-slate-500">{t("dashboard.brokerTypeLockedHint")}</p>
              ) : (
                <p className="text-xs text-slate-500">
                  {addKind === "tiger" && t("dashboard.tigerUploadHint")}
                  {addKind === "longbridge" && t("dashboard.lbUploadHint")}
                  {addKind === "schwab" && t("dashboard.schwabUploadHint")}
                  {addKind === "alpaca" && t("dashboard.alpacaUploadHint")}
                  {addKind === "ibkr_web" && t("dashboard.ibkrWebUploadHint")}
                  {addKind === "usmart" && t("dashboard.usmartUploadHint")}
                  {isAgent && t("dashboard.agentBindingHint")}
                </p>
              )}
            </div>

            {isEditing && editingCredential ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-700">
                <p className="font-semibold text-slate-800">{t("dashboard.secretsReadonly")}</p>
                <div className="mt-2 grid gap-1 sm:grid-cols-2">
                  {credentialDetails(editingCredential).map((row) => (
                    <span key={row.label}>
                      {row.label}: <span className="font-mono text-slate-900">{row.value}</span>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {addKind === "tiger" ? (
              <div className="space-y-3">
                {isEditing ? (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">
                      {t("dashboard.tigerTradingMode")}
                    </label>
                    <div className="flex items-center gap-2">
                      <EnvBadge
                        env={tigerEnv}
                        broker="tiger"
                        accountId={editingCredential?.account_id}
                      />
                      {tigerLicense ? (
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                          {tigerLicense}
                        </span>
                      ) : null}
                    </div>
                    <p className="text-xs text-slate-500">{t("dashboard.tigerEnvLockedHint")}</p>
                    {(tigerLicenseRequiresToken(tigerLicense) ||
                      tigerLicenseRequiresToken(editingCredential?.license)) && (
                      <p className="text-xs text-amber-800">{t("dashboard.tigerTokenTbhkHint")}</p>
                    )}
                  </div>
                ) : (
                  <>
                    <CredentialEncryptionNotice />
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-950">
                      <p className="font-semibold">{t("dashboard.tigerApiTitle")}</p>
                      <p className="mt-1">{t("dashboard.tigerApiHint")}</p>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                        <a
                          href="https://developer.itigerup.com/profile"
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-amber-800 underline underline-offset-2"
                        >
                          {t("dashboard.tigerDeveloperPortal")} ↗
                        </a>
                        <a
                          href="https://docs.itigerup.com/docs/"
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-amber-800 underline underline-offset-2"
                        >
                          {t("dashboard.tigerApiDocs")} ↗
                        </a>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <div className="grid gap-2 text-sm md:grid-cols-3">
                        <UiSelect
                          value={tigerEnv}
                          onChange={(v) => setTigerEnv(v as "paper" | "live")}
                          options={tigerEnvOptions}
                        />
                        <input
                          className="input"
                          placeholder={t("dashboard.tigerIdPlaceholder")}
                          value={tigerId}
                          onChange={(e) => setTigerId(e.target.value)}
                        />
                        <input
                          className="input"
                          placeholder={t("dashboard.tigerAccountPlaceholder")}
                          value={tigerAccount}
                          onChange={(e) => setTigerAccount(e.target.value)}
                        />
                      </div>
                      <p className="text-xs text-slate-500">{t("dashboard.tigerEnvHint")}</p>
                    </div>
                  </>
                )}
                {/* 新增与编辑均可上传；TBHK 还需 token 文件或粘贴 */}
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-3">
                    <input
                      ref={tigerFileRef}
                      type="file"
                      accept=".properties,.pem,.key,.pk8,.pk1,.txt"
                      className="hidden"
                      onChange={(e) => void handleTigerFile(e.target.files?.[0] ?? null)}
                    />
                    <button
                      type="button"
                      className="btn-secondary text-sm"
                      onClick={() => tigerFileRef.current?.click()}
                    >
                      {t("dashboard.tigerUploadFile")}
                    </button>
                    {tigerFile ? (
                      <span className="text-xs text-profit">
                        {t("dashboard.tigerFileSelected", { name: tigerFile.filename })}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">
                        {isEditing ? t("dashboard.tigerReuploadOptional") : t("dashboard.tigerFileEmpty")}
                      </span>
                    )}
                    {tigerLicense ? (
                      <span className="text-xs text-slate-500">
                        License: <span className="font-mono text-slate-800">{tigerLicense}</span>
                      </span>
                    ) : null}
                  </div>
                  {(tigerLicenseRequiresToken(tigerLicense) ||
                    Boolean(tigerToken) ||
                    tigerLicenseRequiresToken(editingCredential?.license)) && (
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-600">
                        {t("dashboard.tigerTokenLabel")}
                      </label>
                      <textarea
                        className="input min-h-[4.5rem] font-mono text-xs"
                        placeholder={t("dashboard.tigerTokenPlaceholder")}
                        value={tigerToken}
                        onChange={(e) => setTigerToken(e.target.value)}
                      />
                      <p className="text-xs text-slate-500">{t("dashboard.tigerTokenHint")}</p>
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {addKind === "longbridge" ? (
              <div className="space-y-3">
                {isEditing ? (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">{t("dashboard.envSandbox")}</label>
                    <UiSelect
                      value={lbEnv}
                      onChange={(v) => setLbEnv(v as "sandbox" | "live")}
                      options={lbEnvOptions}
                    />
                  </div>
                ) : (
                  <>
                    <CredentialEncryptionNotice />
                    <div className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-xs leading-relaxed text-cyan-950">
                      <p className="font-semibold">{t("dashboard.longbridgeApiTitle")}</p>
                      <p className="mt-1">{t("dashboard.longbridgeApiHint")}</p>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                        <a
                          href="https://open.longbridge.com/"
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-cyan-800 underline underline-offset-2"
                        >
                          {t("dashboard.longbridgeDeveloperPortal")} ↗
                        </a>
                        <a
                          href="https://open.longbridge.com/docs/getting-started"
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-cyan-800 underline underline-offset-2"
                        >
                          {t("dashboard.longbridgeApiDocs")} ↗
                        </a>
                      </div>
                    </div>
                    <div className="grid gap-2 text-sm md:grid-cols-2">
                      <UiSelect
                        value={lbEnv}
                        onChange={(v) => setLbEnv(v as "sandbox" | "live")}
                        options={lbEnvOptions}
                      />
                      <input
                        className="input"
                        placeholder={t("dashboard.lbAccountPlaceholder")}
                        value={lbAccount}
                        onChange={(e) => setLbAccount(e.target.value)}
                      />
                      <input
                        className="input"
                        placeholder="App Key"
                        value={lbAppKey}
                        onChange={(e) => setLbAppKey(e.target.value)}
                      />
                      <input
                        className="input"
                        placeholder="App Secret"
                        type="password"
                        value={lbAppSecret}
                        onChange={(e) => setLbAppSecret(e.target.value)}
                      />
                      <input
                        className="input md:col-span-2"
                        placeholder="Access Token"
                        type="password"
                        value={lbAccessToken}
                        onChange={(e) => setLbAccessToken(e.target.value)}
                      />
                    </div>
                  </>
                )}
              </div>
            ) : null}

            {addKind === "schwab" && !isEditing ? (
              <div className="space-y-3">
                <CredentialEncryptionNotice />
                <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs leading-relaxed text-sky-900">
                  <p className="font-semibold">{t("dashboard.schwabOAuthTitle")}</p>
                  <p className="mt-1">{t("dashboard.schwabOAuthHint")}</p>
                  <a
                    href="https://developer.schwab.com/user-guides/get-started/authenticate-with-oauth"
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex font-medium text-sky-700 underline underline-offset-2"
                  >
                    {t("dashboard.schwabDocs")} ↗
                  </a>
                </div>
                <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                  <label className="flex min-w-0 flex-col gap-1.5 sm:col-span-2">
                    <span className="text-xs font-medium text-slate-700">{t("dashboard.schwabCallbackUrl")}</span>
                    <input
                      className="input font-mono text-xs"
                      value={schwabRedirectUri || schwabAutoCallbackUrl()}
                      onChange={(e) => setSchwabRedirectUri(e.target.value)}
                      autoComplete="off"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="btn-secondary px-2 py-1 text-[11px]"
                        onClick={() => setSchwabRedirectUri(schwabAutoCallbackUrl())}
                      >
                        {t("dashboard.schwabUseAutoCallback")}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary px-2 py-1 text-[11px]"
                        onClick={() => setSchwabRedirectUri("https://127.0.0.1")}
                      >
                        {t("dashboard.schwabUsePasteCallback")}
                      </button>
                    </div>
                    <span className="text-[11px] text-slate-500">{t("dashboard.schwabCallbackUrlHint")}</span>
                    <span className="text-[11px] text-slate-500">{t("dashboard.schwabAutoCallbackHint")}</span>
                  </label>
                  <label className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-xs font-medium text-slate-700">{t("dashboard.schwabClientId")}</span>
                    <input
                      className="input"
                      value={schwabClientId}
                      onChange={(e) => setSchwabClientId(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <label className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-xs font-medium text-slate-700">{t("dashboard.schwabClientSecret")}</span>
                    <input
                      className="input"
                      type="password"
                      value={schwabClientSecret}
                      onChange={(e) => setSchwabClientSecret(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {addKind === "alpaca" ? (
              <div className="space-y-3">
                {isEditing ? (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">{t("dashboard.envPaper")}</label>
                    <UiSelect
                      value={alpacaEnv}
                      onChange={(v) => setAlpacaEnv(v as "paper" | "live")}
                      options={alpacaEnvOptions}
                    />
                  </div>
                ) : (
                  <>
                    <CredentialEncryptionNotice />
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-950">
                      <p className="font-semibold">{t("dashboard.alpacaApiTitle")}</p>
                      <p className="mt-1">{t("dashboard.alpacaApiHint")}</p>
                      <a
                        href="https://docs.alpaca.markets/us/docs/authentication"
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex font-medium text-amber-800 underline underline-offset-2"
                      >
                        {t("dashboard.alpacaDocs")} ↗
                      </a>
                    </div>
                    <div className="grid gap-2 text-sm md:grid-cols-2">
                      <UiSelect
                        value={alpacaEnv}
                        onChange={(v) => setAlpacaEnv(v as "paper" | "live")}
                        options={alpacaEnvOptions}
                      />
                      <input
                        className="input"
                        placeholder={t("dashboard.alpacaAccount")}
                        value={alpacaAccount}
                        onChange={(e) => setAlpacaAccount(e.target.value)}
                      />
                      <input
                        className="input"
                        placeholder="API Key ID"
                        value={alpacaApiKey}
                        onChange={(e) => setAlpacaApiKey(e.target.value)}
                      />
                      <input
                        className="input"
                        placeholder="API Secret Key"
                        type="password"
                        value={alpacaApiSecret}
                        onChange={(e) => setAlpacaApiSecret(e.target.value)}
                      />
                    </div>
                  </>
                )}
              </div>
            ) : null}

            {addKind === "ibkr_web" ? (
              <div className="space-y-3">
                {isEditing ? (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">{t("dashboard.envPaper")}</label>
                    <UiSelect
                      value={ibkrWebEnv}
                      onChange={(v) => setIbkrWebEnv(v as "paper" | "live")}
                      options={alpacaEnvOptions}
                    />
                  </div>
                ) : (
                  <>
                    <CredentialEncryptionNotice />
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-950">
                      <p className="font-semibold">{t("dashboard.ibkrWebApiTitle")}</p>
                      <p className="mt-1">{t("dashboard.ibkrWebApiHint")}</p>
                      <p className="mt-2 rounded-lg border border-amber-300/80 bg-amber-100/80 px-2.5 py-2 font-medium text-amber-950">
                        {t("dashboard.ibkrWebActivationNotice")}
                      </p>
                      <p className="mt-1 text-amber-900/80">{t("dashboard.ibkrWebGenerateHint")}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          className="btn-secondary min-h-0 px-3 py-1.5 text-xs"
                          disabled={busy || ibkrWebGenBusy}
                          onClick={() => void generateIbkrWebKeys()}
                        >
                          {ibkrWebGenBusy
                            ? t("dashboard.ibkrWebGenerating")
                            : t("dashboard.ibkrWebGenerate")}
                        </button>
                        <a
                          href="https://ndcdyn.interactivebrokers.com/sso/Login?action=OAUTH&RL=1&ip2loc=US"
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex font-medium text-amber-800 underline underline-offset-2"
                        >
                          {t("dashboard.ibkrWebPortal")} ↗
                        </a>
                      </div>
                    </div>
                    <div className="grid gap-2 text-sm md:grid-cols-2">
                      <UiSelect
                        value={ibkrWebEnv}
                        onChange={(v) => setIbkrWebEnv(v as "paper" | "live")}
                        options={alpacaEnvOptions}
                      />
                      <input
                        className="input"
                        placeholder={t("dashboard.ibkrWebAccount")}
                        value={ibkrWebAccount}
                        onChange={(e) => setIbkrWebAccount(e.target.value)}
                      />
                      <input
                        className="input md:col-span-2"
                        placeholder="Consumer Key"
                        value={ibkrWebConsumerKey}
                        onChange={(e) => setIbkrWebConsumerKey(e.target.value)}
                        autoComplete="off"
                      />
                      <input
                        className="input md:col-span-2"
                        placeholder="Access Token"
                        value={ibkrWebAccessToken}
                        onChange={(e) => setIbkrWebAccessToken(e.target.value)}
                        autoComplete="off"
                      />
                      <textarea
                        className="input min-h-[4.5rem] font-mono text-xs md:col-span-2"
                        placeholder="Access Token Secret"
                        value={ibkrWebAccessTokenSecret}
                        onChange={(e) => setIbkrWebAccessTokenSecret(e.target.value)}
                        autoComplete="off"
                      />
                      <textarea
                        className="input min-h-[5.5rem] font-mono text-xs md:col-span-2"
                        placeholder={t("dashboard.ibkrWebSignatureKey")}
                        value={ibkrWebSignatureKey}
                        onChange={(e) => setIbkrWebSignatureKey(e.target.value)}
                        autoComplete="off"
                      />
                      <textarea
                        className="input min-h-[5.5rem] font-mono text-xs md:col-span-2"
                        placeholder={t("dashboard.ibkrWebEncryptionKey")}
                        value={ibkrWebEncryptionKey}
                        onChange={(e) => setIbkrWebEncryptionKey(e.target.value)}
                        autoComplete="off"
                      />
                      <textarea
                        className="input min-h-[4.5rem] font-mono text-xs md:col-span-2"
                        placeholder={t("dashboard.ibkrWebDhPrime")}
                        value={ibkrWebDhPrime}
                        onChange={(e) => setIbkrWebDhPrime(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                  </>
                )}
              </div>
            ) : null}

            {addKind === "usmart" ? (
              <div className="space-y-3">
                {isEditing ? (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">{t("dashboard.envLive")}</label>
                    <UiSelect
                      value={usmartEnv}
                      onChange={(v) => setUsmartEnv(v as "live" | "uat")}
                      options={usmartEnvOptions}
                    />
                    <p className="text-xs text-slate-500">
                      {t("dashboard.usmartRegion")}: {usmartRegionLabel(usmartRegion, t)}
                    </p>
                  </div>
                ) : (
                  <>
                    <CredentialEncryptionNotice />
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-950">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold">{t("dashboard.usmartApiTitle")}</p>
                        <span className="inline-flex items-center rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 ring-1 ring-rose-200">
                          {usmartRegionLabel(usmartRegion, t)}
                        </span>
                      </div>
                      <p className="mt-1">{t("dashboard.usmartApiHint")}</p>
                      <p className="mt-1 text-amber-900/80">{t("dashboard.usmartRegionHint")}</p>
                      <p className="mt-1 text-amber-900/80">
                        {usmartRegion === "hk"
                          ? t("dashboard.usmartRegionNoteHk")
                          : t("dashboard.usmartRegionNoteSg")}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                        <a
                          href="https://api-doc.usmart.sg/zh-cn/trade.html"
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-amber-800 underline underline-offset-2"
                        >
                          {t("dashboard.usmartDocs")} ↗
                        </a>
                        <a
                          href={USMART_APPLY_URLS[usmartRegion]}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-amber-800 underline underline-offset-2"
                        >
                          {t("dashboard.usmartApply")} ↗
                        </a>
                      </div>
                    </div>
                    <div className="grid gap-2 text-sm md:grid-cols-2">
                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-600">{t("dashboard.usmartRegion")}</label>
                        <UiSelect
                          value={usmartRegion}
                          onChange={(v) => setUsmartRegion(v as UsmartRegion)}
                          options={usmartRegionOptions}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-600">{t("dashboard.envLive")}</label>
                        <UiSelect
                          value={usmartEnv}
                          onChange={(v) => setUsmartEnv(v as "live" | "uat")}
                          options={usmartEnvOptions}
                        />
                      </div>
                      <input
                        className="input md:col-span-2"
                        placeholder={t("dashboard.usmartChannel")}
                        value={usmartChannel}
                        onChange={(e) => setUsmartChannel(e.target.value)}
                      />
                      <textarea
                        className="input md:col-span-2 min-h-[88px] font-mono text-xs"
                        placeholder={t("dashboard.usmartPublicKey")}
                        value={usmartPublicKey}
                        onChange={(e) => setUsmartPublicKey(e.target.value)}
                      />
                      <textarea
                        className="input md:col-span-2 min-h-[88px] font-mono text-xs"
                        placeholder={t("dashboard.usmartPrivateKey")}
                        value={usmartPrivateKey}
                        onChange={(e) => setUsmartPrivateKey(e.target.value)}
                      />
                    </div>
                  </>
                )}
              </div>
            ) : null}

            {addKind === "ibkr" ? (
              <div className="space-y-3">
                <AgentLocalSetupLinks broker="ibkr" />
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-600">
                    {t("dashboard.ibkrConnectionMode")}
                  </label>
                  <UiSelect
                    value={ibkrMode}
                    onChange={(v) => setIbkrMode(v as IbkrPresetId)}
                    options={ibkrModeOptions}
                  />
                  <p className="text-xs text-slate-500">{t("dashboard.ibkrConnectionModeHint")}</p>
                </div>
                <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs leading-relaxed text-sky-950">
                  <p className="font-semibold">{t("dashboard.relayAgent")}</p>
                  <p className="mt-1">{t("dashboard.agentSingleDeviceHint")}</p>
                </div>
              </div>
            ) : null}

            {addKind === "futu" ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                  <span className="inline-flex items-center rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 ring-1 ring-rose-200">
                    {t("dashboard.regionHongKong")}
                  </span>
                  <span>{t("dashboard.futuRegionNote")}</span>
                </div>
                <AgentLocalSetupLinks broker="futu" />
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-600">
                    {t("dashboard.futuConnectionMode")}
                  </label>
                  <UiSelect
                    value={futuMode}
                    onChange={(v) => setFutuMode(v as FutuPresetId)}
                    options={futuModeOptions}
                  />
                  <p className="text-xs text-slate-500">{t("dashboard.futuConnectionModeHint")}</p>
                </div>
                <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs leading-relaxed text-sky-950">
                  <p className="font-semibold">{t("dashboard.relayAgent")}</p>
                  <p className="mt-1">{t("dashboard.agentSingleDeviceHint")}</p>
                </div>
              </div>
            ) : null}

            {error ? <p className="text-sm text-loss">{error}</p> : null}
          </div>
        </BrokerAddModal>

        <ConfirmDialog
          open={deleteTarget != null}
          title={t("dashboard.deleteCredentialTitle")}
          message={t("dashboard.deleteCredentialConfirm", {
            name: deleteTarget?.label ?? "",
          })}
          confirmLabel={t("dashboard.deleteCredential")}
          cancelLabel={t("common.cancel")}
          variant="danger"
          busy={deleteBusy}
          onClose={() => !deleteBusy && setDeleteTarget(null)}
          onConfirm={() => void confirmDeleteAccount()}
        />
      </section>
  );
}
