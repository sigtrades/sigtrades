import axios from "axios";
import type { TFunction } from "i18next";

type ApiErrorDetail = {
  error?: string;
  feature?: string;
  limit?: number;
  message?: string;
};

export function formatApiError(e: unknown, t: TFunction): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail as ApiErrorDetail | string | undefined;
    if (detail && typeof detail === "object") {
      if (detail.error === "plan_limit_exceeded" && detail.feature === "max_signal_sources") {
        return t("dashboard.planLimitSources", { limit: detail.limit ?? 1 });
      }
      if (detail.error === "plan_limit_exceeded" && detail.feature === "max_brokers") {
        return t("dashboard.planLimitBrokers", { limit: detail.limit ?? 1 });
      }
      if (detail.error === "plan_feature_required") {
        const featureKey = detail.feature ?? "";
        const labeled = featureKey ? t(`dashboard.planFeature.${featureKey}`, { defaultValue: featureKey }) : "";
        return t("dashboard.planFeatureRequired", { feature: labeled || featureKey });
      }
      if (detail.error === "ai_not_configured") {
        return t("dashboard.parseAiNotConfigured");
      }
      if (detail.message) return String(detail.message);
      if (detail.error) return String(detail.error);
    }
    if (typeof detail === "string") {
      if (detail === "email_not_verified") {
        return t("dashboard.emailNotVerifiedAction");
      }
      if (detail) return detail;
    }
  }
  return e instanceof Error ? e.message : String(e);
}
