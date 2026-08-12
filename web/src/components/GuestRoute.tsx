import { useEffect } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../store/auth";
import { DEFAULT_APP_PATH } from "../lib/appRoutes";
import FullPageLoader from "./FullPageLoader";

export default function GuestRoute() {
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  const isHydrating = useAuth((s) => s.isHydrating);
  const user = useAuth((s) => s.user);
  const fetchMe = useAuth((s) => s.fetchMe);

  useEffect(() => {
    if (isAuthenticated && !user) {
      void fetchMe();
    }
  }, [isAuthenticated, user, fetchMe]);

  if (isHydrating) return <FullPageLoader />;
  if (isAuthenticated) {
    if (!user) return <FullPageLoader />;
    return <Navigate to={DEFAULT_APP_PATH} replace />;
  }
  return <Outlet />;
}
