import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AuthBootstrap from "./components/AuthBootstrap";
import GuestRoute from "./components/GuestRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Pricing from "./pages/Pricing";
import VerifyEmail from "./pages/VerifyEmail";
import VerifyPending from "./pages/VerifyPending";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import MembershipSuccess from "./pages/MembershipSuccess";
import AgentConnect from "./pages/AgentConnect";
import AgentReleases from "./pages/AgentReleases";
import ConfirmTrade from "./pages/ConfirmTrade";
import SchwabCallback from "./pages/SchwabCallback";
import Legal from "./pages/Legal";
import RedeemCode from "./pages/RedeemCode";
import { DEFAULT_APP_PATH } from "./lib/appRoutes";

export default function App() {
  return (
    <AuthBootstrap>
      <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/legal/:doc" element={<Legal />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/verify-pending" element={<VerifyPending />} />
        <Route path="/confirm-trade" element={<ConfirmTrade />} />
        <Route path="/redeem" element={<RedeemCode />} />
        <Route element={<GuestRoute />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
        </Route>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/membership/success" element={<MembershipSuccess />} />
        <Route path="/agent/connect" element={<AgentConnect />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/schwab/callback" element={<SchwabCallback />} />
          <Route path="/agent/releases" element={<AgentReleases />} />
          <Route path="/app" element={<Navigate to={DEFAULT_APP_PATH} replace />} />
          <Route path="/app/:section" element={<Dashboard />} />
        </Route>
      </Routes>
      </BrowserRouter>
    </AuthBootstrap>
  );
}
