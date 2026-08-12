import { GoogleOAuthProvider } from "@react-oauth/google";

const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

/** 仅包裹 Google 登录按钮，避免全站依赖 accounts.google.com（国内可达性差会导致白屏）。 */
export default function GoogleAuthGate({ children }: { children: React.ReactNode }) {
  if (!clientId) return null;
  return <GoogleOAuthProvider clientId={clientId}>{children}</GoogleOAuthProvider>;
}
