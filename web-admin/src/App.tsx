import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { canAccessAdminPath } from "@/lib/adminPermissions";
import MainLayout from "@/components/Layout/MainLayout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Users from "@/pages/Users";
import UsersAnalytics from "@/pages/UsersAnalytics";
import UserDetail from "@/pages/UserDetail";
import Payments from "@/pages/Payments";
import MembershipPlans from "@/pages/MembershipPlans";
import Promotions from "@/pages/Promotions";
import InAppMessages from "@/pages/InAppMessages";
import InboundMail from "@/pages/InboundMail";
import Settings from "@/pages/Settings";
import Agents from "@/pages/Agents";
import AgentRelease from "@/pages/AgentRelease";
import Executions from "@/pages/Executions";
import ChannelStats from "@/pages/ChannelStats";
import SignalSources from "@/pages/SignalSources";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function AdminPathGuard({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.role);
  const location = useLocation();
  if (!canAccessAdminPath(role, location.pathname)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <PrivateRoute>
            <MainLayout>
              <AdminPathGuard>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/users" element={<Users />} />
                  <Route path="/users/analytics" element={<UsersAnalytics />} />
                  <Route path="/users/:userId" element={<UserDetail />} />
                  <Route path="/payments" element={<Payments />} />
                  <Route path="/membership-plans" element={<MembershipPlans />} />
                  <Route path="/promotions" element={<Promotions />} />
                  <Route path="/in-app-messages" element={<InAppMessages />} />
                  <Route path="/inbound-mail" element={<InboundMail />} />
                  <Route path="/agents" element={<Agents />} />
                  <Route path="/agents/release" element={<AgentRelease />} />
                  <Route path="/executions" element={<Executions />} />
                  <Route path="/channel-stats" element={<ChannelStats />} />
                  <Route path="/signal-sources" element={<SignalSources />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </AdminPathGuard>
            </MainLayout>
          </PrivateRoute>
        }
      />
    </Routes>
  );
}
