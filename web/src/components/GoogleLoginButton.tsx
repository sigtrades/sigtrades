import { GoogleLogin, CredentialResponse } from "@react-oauth/google";
import { useTranslation } from "react-i18next";
import { useAuth } from "../store/auth";
import GoogleAuthGate from "./GoogleAuthGate";

type Props = {
  mode?: "login" | "register";
  onSuccess: () => void;
  onError?: (msg: string) => void;
  /** 返回 false 时不提交凭证（例如注册页未勾选条款） */
  canProceed?: () => boolean;
  blockedMessage?: string;
};

export default function GoogleLoginButton({
  mode = "login",
  onSuccess,
  onError,
  canProceed,
  blockedMessage,
}: Props) {
  const { t, i18n } = useTranslation();
  const googleLogin = useAuth((s) => s.googleLogin);

  const handle = async (res: CredentialResponse) => {
    if (!res.credential) {
      onError?.(t("auth.googleLoginFailed"));
      return;
    }
    if (canProceed && !canProceed()) {
      onError?.(blockedMessage || t("auth.agreeTermsRequired"));
      return;
    }
    try {
      await googleLogin(res.credential);
      onSuccess();
    } catch {
      onError?.(t("auth.googleLoginFailed"));
    }
  };

  const locale = i18n.language?.startsWith("en")
    ? "en"
    : i18n.language?.startsWith("zh-HK")
      ? "zh-HK"
      : "zh-CN";

  return (
    <GoogleAuthGate>
      <div className="flex justify-center">
        <GoogleLogin
          key={i18n.language}
          onSuccess={handle}
          onError={() => onError?.(t("auth.googleLoginFailed"))}
          theme="outline"
          size="large"
          width="100%"
          text={mode === "register" ? "signup_with" : "signin_with"}
          shape="rectangular"
          locale={locale}
        />
      </div>
    </GoogleAuthGate>
  );
}
