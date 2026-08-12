import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AdminRole } from "@/lib/adminPermissions";

interface AuthState {
  token: string | null;
  role: AdminRole | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (token: string, role: AdminRole, username: string) => void;
  setProfile: (role: AdminRole, username: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      username: null,
      isAuthenticated: false,
      login: (token, role, username) => set({ token, role, username, isAuthenticated: true }),
      setProfile: (role, username) => set({ role, username }),
      logout: () => set({ token: null, role: null, username: null, isAuthenticated: false }),
    }),
    { name: "sigtrades-admin-auth" },
  ),
);
