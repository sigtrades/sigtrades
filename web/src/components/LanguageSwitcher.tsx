import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { useAuth } from "../store/auth";
import UiSelect from "./UiSelect";

type Props = {
  className?: string;
  compact?: boolean;
};

export default function LanguageSwitcher({ className = "w-[7.5rem]", compact }: Props) {
  const { i18n, t } = useTranslation();
  const accessToken = useAuth((s) => s.accessToken);

  const current = i18n.language?.startsWith("zh") ? "zh" : "en";

  const switchLang = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem("lang", lng);
    if (accessToken) api.patch("/me", { language: lng }).catch(() => {});
  };

  return (
    <UiSelect
      value={current}
      onChange={switchLang}
      options={[
        { value: "zh", label: compact ? "中文" : t("common.langZh") },
        { value: "en", label: compact ? "English" : t("common.langEn") },
      ]}
      className={className}
      aria-label={t("common.language")}
    />
  );
}
