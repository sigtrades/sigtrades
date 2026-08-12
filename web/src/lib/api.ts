import axios from "axios";
import { useAuth } from "../store/auth";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const { accessToken } = useAuth.getState();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const originalRequest = err.config;
    const status = err.response?.status;
    const url = String(originalRequest?.url ?? "");

    const skipRefresh =
      url.includes("/auth/login") ||
      url.includes("/auth/register") ||
      url.includes("/auth/google") ||
      url.includes("/auth/refresh") ||
      url.includes("/auth/verify-email") ||
      url.includes("/auth/resend-verification");

    if (status === 401 && originalRequest && !originalRequest._retry && !skipRefresh) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) {
        useAuth.getState().logout();
        return Promise.reject(err);
      }
      originalRequest._retry = true;

      try {
        await useAuth.getState().refreshTokens();
        const { accessToken } = useAuth.getState();
        if (!accessToken) {
          useAuth.getState().logout();
          return Promise.reject(err);
        }
        originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        return api(originalRequest);
      } catch {
        useAuth.getState().logout();
        return Promise.reject(err);
      }
    }

    return Promise.reject(err);
  }
);

export default api;
