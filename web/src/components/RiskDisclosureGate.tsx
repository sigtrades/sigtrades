import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { formatApiError } from "../lib/apiError";
import { useAuth } from "../store/auth";
import SimpleMarkdown from "./SimpleMarkdown";

const DEFAULT_READ_SECONDS = 10;

type DisclosurePayload = {
  version: string;
  accepted: boolean;
  markdown: string;
  read_seconds?: number;
};

type Props = {
  onAccepted: () => void | Promise<void>;
};

export default function RiskDisclosureGate({ onAccepted }: Props) {
  const { t } = useTranslation();
  const language = useAuth((s) => s.user?.language);
  const [payload, setPayload] = useState<DisclosurePayload | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(DEFAULT_READ_SECONDS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get<DisclosurePayload>("/risk-disclosure");
        if (cancelled) return;
        if (data.accepted) {
          await onAccepted();
          return;
        }
        setPayload(data);
        setSecondsLeft(Math.max(1, Number(data.read_seconds) || DEFAULT_READ_SECONDS));
      } catch (e) {
        if (!cancelled) setLoadError(formatApiError(e, t));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onAccepted, t, language]);

  useEffect(() => {
    if (!payload || secondsLeft <= 0) return;
    const timer = window.setTimeout(() => {
      setSecondsLeft((s) => Math.max(0, s - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [payload, secondsLeft]);

  const confirm = async () => {
    if (!payload || secondsLeft > 0 || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/risk-disclosure/agree", { version: payload.version });
      await onAccepted();
    } catch (e) {
      setError(formatApiError(e, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/55 p-3 backdrop-blur-[2px] sm:p-6">
      <div
        className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="risk-disclosure-title"
      >
        <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
            {t("riskDisclosure.eyebrow")}
          </p>
          <h2 id="risk-disclosure-title" className="mt-1 text-lg font-semibold text-slate-900">
            {t("riskDisclosure.title")}
          </h2>
          <p className="mt-1 text-xs text-slate-500">{t("riskDisclosure.subtitle")}</p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-6">
          {loadError ? (
            <p className="text-sm text-loss">{loadError}</p>
          ) : !payload ? (
            <p className="text-sm text-slate-500">{t("riskDisclosure.loading")}</p>
          ) : (
            <SimpleMarkdown source={payload.markdown} />
          )}
        </div>

        <div className="space-y-3 border-t border-slate-100 bg-slate-50 px-5 py-4 sm:px-6">
          <p className="text-xs text-slate-600">{t("riskDisclosure.confirmHint")}</p>
          {error ? <p className="text-sm text-loss">{error}</p> : null}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              {payload ? t("riskDisclosure.version", { version: payload.version }) : null}
            </p>
            <button
              type="button"
              className="btn-primary min-w-[10rem] text-sm disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!payload || secondsLeft > 0 || busy}
              onClick={() => void confirm()}
            >
              {busy
                ? t("riskDisclosure.saving")
                : secondsLeft > 0
                  ? t("riskDisclosure.waitConfirm", { seconds: secondsLeft })
                  : t("riskDisclosure.confirm")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
