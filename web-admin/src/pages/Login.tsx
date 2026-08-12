import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { authApi } from "@/api";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await authApi.login(username, password);
      login(response.token, response.role, response.username);
      navigate("/");
    } catch (err: unknown) {
      const anyErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      const detail = anyErr?.response?.data?.detail;
      const status = anyErr?.response?.status;
      if (detail) setError(detail);
      else if (status === 401) setError("用户名或密码错误");
      else if (!status) setError("无法连接到服务器，请确认 API 服务正在运行");
      else setError(anyErr?.message || `登录失败（HTTP ${status}）`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-600 to-brand-800">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-slate-900">SigTrades</h1>
          <p className="mt-1 text-slate-500">管理后台登录</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-6">
          {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input w-full"
              placeholder="admin"
              required
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input w-full"
              required
            />
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? "登录中…" : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
