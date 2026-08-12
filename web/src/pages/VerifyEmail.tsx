import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import Layout from "../components/Layout";
import { useAuth } from "../store/auth";

export default function VerifyEmail() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  const fetchMe = useAuth((s) => s.fetchMe);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const token = useMemo(() => (params.get("token") || "").trim(), [params]);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        await api.get("/auth/verify-email", { params: { token }, signal: controller.signal });
        if (cancelled) return;
        setStatus("ok");
        if (useAuth.getState().isAuthenticated) {
          try {
            await fetchMe();
          } catch {
            // ignore
          }
        }
      } catch (e: unknown) {
        if (cancelled || controller.signal.aborted) return;
        const code = (e as { code?: string })?.code;
        if (code === "ERR_CANCELED") return;
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [token, fetchMe]);

  return (
    <Layout>
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card text-center">
          {status === "loading" && <p className="text-slate-600">{t("auth.verifying")}</p>}
          {status === "ok" && (
            <>
              <h1 className="text-2xl font-bold text-emerald-700">{t("auth.verifySuccess")}</h1>
              <p className="mt-3 text-sm text-slate-600">{t("auth.verifySuccessHint")}</p>
              <button
                type="button"
                className="btn-primary mt-6 px-5 py-2.5"
                onClick={() => navigate(isAuthenticated ? "/app" : "/login", { replace: true })}
              >
                {isAuthenticated ? t("nav.dashboard") : t("nav.login")}
              </button>
            </>
          )}
          {status === "error" && (
            <>
              <h1 className="text-2xl font-bold text-loss">{t("auth.verifyFailed")}</h1>
              <p className="mt-3 text-sm text-slate-600">{t("auth.verifyFailedHint")}</p>
              <Link to="/verify-pending" className="btn-primary mt-6 inline-block px-5 py-2.5">
                {t("auth.resendVerify")}
              </Link>
              <p className="mt-4 text-sm">
                <Link to="/login" className="text-brand-600 hover:underline">
                  {t("nav.login")}
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </Layout>
  );
}
