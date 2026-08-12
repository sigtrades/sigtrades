import { ReactNode, useEffect, useState } from "react";
import api from "../lib/api";

type Props = {
  feature: string;
  children: ReactNode;
  fallback?: ReactNode;
};

export default function FeatureGate({ feature, children, fallback = null }: Props) {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    api.get("/config/entitlements").then((r) => {
      const feats = r.data.features || {};
      const val = feats[feature];
      setOk(typeof val === "boolean" ? val : Number(val) > 0);
    }).catch(() => setOk(false));
  }, [feature]);

  if (ok === null) return null;
  if (!ok) return <>{fallback}</>;
  return <>{children}</>;
}
