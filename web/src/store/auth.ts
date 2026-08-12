import { create } from "zustand";
import i18n from "../i18n";
import api from "../lib/api";

type User = {
  id: string;
  email: string;
  display_name?: string | null;
  plan_code?: string;
  /** gift | trial | subscription */
  billing_cycle?: string | null;
  language?: string;
  kill_switch?: boolean;
  sound_notifications?: boolean;
  email_verified?: boolean;
  auth_provider?: string;
  risk_disclosure_accepted?: boolean;
  risk_disclosure_version?: string | null;
};

type AuthState = {
  accessToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isHydrating: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
  ) => Promise<{ email_verified?: boolean; verify_email_sent?: boolean }>;
  googleLogin: (credential: string) => Promise<{ is_new?: boolean }>;
  fetchMe: () => Promise<void>;
  refreshTokens: () => Promise<void>;
  hydrate: () => Promise<void>;
  logout: () => void;
};

const readToken = () => localStorage.getItem("access_token");
const readRefresh = () => localStorage.getItem("refresh_token");

const persistTokens = (access: string, refresh: string) => {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
};

export const useAuth = create<AuthState>((set, get) => ({
  accessToken: readToken(),
  user: null,
  isAuthenticated: false,
  isHydrating: true,

  login: async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    persistTokens(data.access_token, data.refresh_token);
    set({ accessToken: data.access_token, isAuthenticated: true });
    await get().fetchMe();
  },

  register: async (email, password) => {
    const { data } = await api.post("/auth/register", {
      email,
      password,
      language: localStorage.getItem("lang") || "zh",
    });
    persistTokens(data.access_token, data.refresh_token);
    set({ accessToken: data.access_token, isAuthenticated: true });
    await get().fetchMe();
    return {
      email_verified: data.email_verified,
      verify_email_sent: data.verify_email_sent,
    };
  },

  googleLogin: async (credential) => {
    const lang = localStorage.getItem("lang") || "zh";
    const { data } = await api.post("/auth/google", { credential, language: lang });
    persistTokens(data.access_token, data.refresh_token);
    set({ accessToken: data.access_token, isAuthenticated: true });
    await get().fetchMe();
    return { is_new: Boolean(data.is_new_user ?? data.is_new) };
  },

  fetchMe: async () => {
    try {
      const { data } = await api.get("/me");
      if (data.language) {
        i18n.changeLanguage(data.language);
        localStorage.setItem("lang", data.language);
      }
      set({ user: data, isAuthenticated: true });
    } catch {
      get().logout();
      throw new Error("FETCH_ME_FAILED");
    }
  },

  refreshTokens: async () => {
    const refreshToken = readRefresh();
    if (!refreshToken) {
      get().logout();
      throw new Error("NO_REFRESH_TOKEN");
    }
    try {
      const { data } = await api.post("/auth/refresh", { refresh_token: refreshToken });
      persistTokens(data.access_token, data.refresh_token);
      set({ accessToken: data.access_token });
    } catch {
      get().logout();
      throw new Error("REFRESH_FAILED");
    }
  },

  hydrate: async () => {
    const token = readToken();
    if (!token) {
      set({ isHydrating: false, isAuthenticated: false, accessToken: null, user: null });
      return;
    }
    set({ accessToken: token, isHydrating: true });
    try {
      await get().fetchMe();
    } catch {
      // fetchMe already logs out on failure
    } finally {
      set({ isHydrating: false });
    }
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    set({ accessToken: null, user: null, isAuthenticated: false });
  },
}));
