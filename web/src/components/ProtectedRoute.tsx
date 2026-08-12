import { useCallback, useEffect } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../store/auth";
import FullPageLoader from "./FullPageLoader";
import RiskDisclosureGate from "./RiskDisclosureGate";

const REQUIRE_VERIFY = import.meta.env.VITE_REQUIRE_EMAIL_VERIFICATION === "true";

export default function ProtectedRoute() {
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  const isHydrating = useAuth((s) => s.isHydrating);
  const user = useAuth((s) => s.user);
  const fetchMe = useAuth((s) => s.fetchMe);

  useEffect(() => {
    if (isAuthenticated && !user) {
      void fetchMe();
    }
  }, [isAuthenticated, user, fetchMe]);

  const onRiskAccepted = useCallback(async () => {
    await fetchMe();
  }, [fetchMe]);

  if (isHydrating) return <FullPageLoader />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!user) return <FullPageLoader />;
  if (REQUIRE_VERIFY && !user.email_verified) {
    return <Navigate to="/verify-pending" replace />;
  }
  if (!user.risk_disclosure_accepted) {
    return <RiskDisclosureGate onAccepted={onRiskAccepted} />;
  }
  return <Outlet />;
}
