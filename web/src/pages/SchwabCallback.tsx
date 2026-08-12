import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { formatApiError } from "../lib/apiError";
import { navPath } from "../lib/appRoutes";

const CRED_KEY = "schwab_oauth_cred_id";

export function schwabAutoCallbackUrl(): string {
  return `${window.location.origin}/schwab/callback`;
}

export function isSchwabAutoCallbackUri(uri: string): boolean {
  try {
    const u = new URL(uri.trim());
    return u.pathname.replace(/\/$/, "") === "/schwab/callback";
  } catch {
    return false;
  }
}

export default function SchwabCallback() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = params.get("code");
    const oauthError = params.get("error");
    const credId = sessionStorage.getItem(CRED_KEY) || "";
    const brokers = `${navPath("brokers")}`;

    if (oauthError) {
      navigate(`${brokers}?schwab=error&reason=${encodeURIComponent(oauthError)}`, { replace: true });
      return;
    }
    if (!code) {
      navigate(`${brokers}?schwab=error&reason=missing_code`, { replace: true });
      return;
    }
    if (!credId) {
      // 无 session：回到券商页并带上完整 URL，供粘贴兜底
      navigate(
        `${brokers}?schwab=paste&redirected=${encodeURIComponent(window.location.href)}`,
        { replace: true },
      );
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        await api.post("/schwab/oauth/complete", {
          cred_id: credId,
          redirected_url: window.location.href,
        });
        sessionStorage.removeItem(CRED_KEY);
        if (!cancelled) {
          navigate(`${brokers}?schwab=ok`, { replace: true });
        }
      } catch (e) {
        if (!cancelled) {
          setError(formatApiError(e, t));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate, params, t]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-base font-semibold text-slate-900">{t("dashboard.schwabCallbackTitle")}</h1>
        {error ? (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-loss break-all">{error}</p>
            <button
              type="button"
              className="btn-secondary text-sm"
              onClick={() =>
                navigate(
                  `${navPath("brokers")}?schwab=paste&redirected=${encodeURIComponent(window.location.href)}`,
                  { replace: true },
                )
              }
            >
              {t("dashboard.schwabCallbackFallback")}
            </button>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-600">{t("dashboard.schwabCallbackWorking")}</p>
        )}
      </div>
    </div>
  );
}
